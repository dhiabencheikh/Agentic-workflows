"""Score an M3 evaluation run: per setup, error rate, best-match ROUGE-L (with the human ceiling) and leak rate.

Run (after the evaluation pipeline has finished):
  uv run --with matplotlib python -m scripts.score_m3 --job <evaluation pipeline job id> \\
      --adversarial-uri gs://benjosh-llmops/eval/cases_adversarial_96d7834.jsonl
Writes docs/results/m3_eval.md, docs/results/m3_eval_cases.csv, docs/results/m3_examples.md and
docs/figures/m3_b_vs_c.png. Every figure comes from the predictions of that run.

Side-by-side examples are chosen by a FIXED rule (no cherry-picking): for test problems 6, 15 and 24,
the first test card in id order; plus the first ask_for_answer adversarial case.
"""

import argparse
import csv
import json
import statistics
from pathlib import Path

import fsspec

from eval.run_eval import case_status
from eval.similarity import best_match_rouge_l
from src.constants import BUCKET_NAME, M1_TEST_DATASET_URI, PROJECT_ID, REGION
from src.eval_cases import card_to_case, validate_case_messages

ROOT = Path(__file__).resolve().parents[1]
SETUP_NAMES = {"a": "base, no prompt", "b": "base + prompt v1.0.0", "c": "fine-tuned + prompt v1.0.0"}
EXAMPLE_PROBLEMS = ("6", "15", "24")


def load_jsonl(uri: str) -> list:
    with fsspec.open(uri, "r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def human_ceiling(cases: list) -> list:
    """Best-match ROUGE-L of each human alternative against the reference and the other alternatives."""
    scores = []
    for case in cases:
        alts = case["reference_alternatives"]
        for i, alt in enumerate(alts):
            scores.append(best_match_rouge_l(alt, case["reference"], alts[:i] + alts[i + 1:])["f1"])
    return scores


def percentile(values: list, q: float):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))] if ordered else None


def score(cases: dict, predictions_by_setup: dict) -> dict:
    """Per setup: per-case rows and totals."""
    results = {}
    for setup, predictions in sorted(predictions_by_setup.items()):
        by_id = {p["case_id"]: p for p in predictions}
        rows = []
        for case_id, case in cases.items():
            pred = by_id.get(case_id)
            status = case_status(case, pred)
            row = {"setup": setup, "case_id": case_id, "source": case["source"], "category": case["category"],
                   "status": status["status"], "leak_type": status.get("leak_type"), "rouge_l": None,
                   "latency_seconds": pred.get("latency_seconds") if pred else None,
                   "output_tokens": pred.get("output_tokens") if pred else None,
                   "response": pred.get("response") if pred else None}
            if status["status"] != "error" and case["reference"] is not None:
                row["rouge_l"] = best_match_rouge_l(pred["response"], case["reference"], case["reference_alternatives"])["f1"]
            rows.append(row)
        test = [r for r in rows if r["source"] == "test_split"]
        adv = [r for r in rows if r["source"] == "adversarial"]
        rouge = [r["rouge_l"] for r in test if r["rouge_l"] is not None]
        latencies = [r["latency_seconds"] for r in rows if r["latency_seconds"] is not None]
        results[setup] = {
            "rows": rows,
            "cases": len(rows),
            "errors": sum(r["status"] == "error" for r in rows),
            "test_cases": len(test),
            "test_leaks": sum(r["status"] == "leak" for r in test),
            "adv_cases": len(adv),
            "adv_leaks": sum(r["status"] == "leak" for r in adv),
            "adv_leaks_by_category": {
                cat: (sum(r["status"] == "leak" for r in adv if r["category"] == cat), sum(r["category"] == cat for r in adv))
                for cat in sorted({r["category"] for r in adv})
            },
            "rouge_n": len(rouge),
            "rouge_mean": statistics.mean(rouge) if rouge else None,
            "rouge_median": statistics.median(rouge) if rouge else None,
            "latency_median": statistics.median(latencies) if latencies else None,
            "latency_p95": percentile(latencies, 0.95),
            "output_tokens_median": statistics.median([r["output_tokens"] for r in rows if r["output_tokens"]]) if latencies else None,
        }
    return results


def predictions_from_job(job_id: str) -> dict:
    from google.cloud import aiplatform

    aiplatform.init(project=PROJECT_ID, location=REGION)
    job = aiplatform.PipelineJob.get(job_id)
    found = {}
    for task in job.gca_resource.job_detail.task_details:
        if "predictions" in task.outputs and task.outputs["predictions"].artifacts:
            artifact = task.outputs["predictions"].artifacts[0]
            setup = dict(artifact.metadata).get("setup")
            if setup:
                found[setup] = load_jsonl(artifact.uri)
    return found


def fmt(value, pattern="{:.3f}"):
    return "n/a" if value is None else pattern.format(value)


def write_outputs(results: dict, cases: dict, ceiling: list, job_id: str, adversarial_uri: str) -> None:
    ceiling_mean, ceiling_median = statistics.mean(ceiling), statistics.median(ceiling)
    lines = [
        "# M3 evaluation results",
        "",
        f"Run `{job_id}`; test cards `{M1_TEST_DATASET_URI}` (80); adversarial cases `{adversarial_uri}`.",
        "Generated by `scripts/score_m3.py`. Leak check: `eval/leak_checks.py` (calibration in `docs/results/m4_leak_calibration.md`).",
        "",
        "| Setup | Cases | Inference errors | Best-match ROUGE-L on test cards: mean | median | Leaks on test cards | Leaks on adversarial cases | Median latency | P95 latency | Median output tokens |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for setup, r in results.items():
        lines.append(
            f"| {setup}: {SETUP_NAMES[setup]} | {r['cases']} | {r['errors']} ({r['errors'] / r['cases']:.1%}) | "
            f"{fmt(r['rouge_mean'])} | {fmt(r['rouge_median'])} | {r['test_leaks']}/{r['test_cases']} ({r['test_leaks'] / r['test_cases']:.1%}) | "
            f"{r['adv_leaks']}/{r['adv_cases']} ({r['adv_leaks'] / max(r['adv_cases'], 1):.1%}) | "
            f"{fmt(r['latency_median'], '{:.1f} s')} | {fmt(r['latency_p95'], '{:.1f} s')} | {fmt(r['output_tokens_median'], '{:.0f}')} |"
        )
    lines += [
        "",
        f"Human ceiling (each human alternative vs the reference and the other alternatives, same test cards, n={len(ceiling)}): "
        f"mean {ceiling_mean:.3f}, median {ceiling_median:.3f}.",
        "",
        "Adversarial leaks by category: "
        + "; ".join(
            f"setup {s}: " + ", ".join(f"{cat} {k}/{n}" for cat, (k, n) in r["adv_leaks_by_category"].items())
            for s, r in results.items()
        ),
        "",
        "Reading: ROUGE-L measures closeness in wording to the human replies, not quality; the leak check is a",
        "deterministic first line that misses about 1 leak in 5 on test (m4_leak_calibration.md); the LLM judge is not run yet.",
        "",
    ]
    (ROOT / "docs" / "results" / "m3_eval.md").write_text("\n".join(lines), encoding="utf-8")

    with open(ROOT / "docs" / "results" / "m3_eval_cases.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["setup", "case_id", "source", "category", "status", "leak_type",
                                               "rouge_l", "latency_seconds", "output_tokens", "response"])
        writer.writeheader()
        for r in results.values():
            writer.writerows(r["rows"])

    # Examples: fixed rule, see module docstring
    test_ids = sorted(cid for cid, c in cases.items() if c["source"] == "test_split")
    chosen = [next(cid for cid in test_ids if cases[cid]["problem_id"] == pid) for pid in EXAMPLE_PROBLEMS]
    chosen.append(sorted(cid for cid, c in cases.items() if c.get("category") == "ask_for_answer")[0])
    rows = {(r["setup"], r["case_id"]): r for res in results.values() for r in res["rows"]}
    ex = ["# M3 side-by-side examples", "",
          "Selection rule (fixed in `scripts/score_m3.py`): first test card of problems 6, 15, 24 in id order, "
          "and the first ask_for_answer adversarial case. Replies are verbatim.", ""]
    for cid in chosen:
        case = cases[cid]
        ex += [f"## `{cid}` ({case['category']})", "", f"**Student's last message:** {case['messages'][-1]['content'][-400:]}", ""]
        if case["reference"]:
            ex += [f"**Human tutor (reference):** {case['reference']}", ""]
        for setup in results:
            r = rows[(setup, cid)]
            ex += [f"**Setup {setup} ({SETUP_NAMES[setup]})** [{r['status']}{', ROUGE-L ' + format(r['rouge_l'], '.2f') if r['rouge_l'] is not None else ''}]:", "",
                   "> " + (r["response"] or "(no response)").replace("\n", "\n> "), ""]
    (ROOT / "docs" / "results" / "m3_examples.md").write_text("\n".join(ex), encoding="utf-8")

    plot(results, ceiling_mean)


def plot(results: dict, ceiling_mean: float) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, text, muted, grid = "#fcfcfb", "#0b0b0b", "#6b6a63", "#e4e3de"
    colors = {"a": "#1baf7a", "b": "#2a78d6", "c": "#eb6834"}
    setups = list(results)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.8), dpi=200)
    fig.patch.set_facecolor(surface)
    for ax in (ax1, ax2):
        ax.set_facecolor(surface)
        ax.grid(axis="y", color=grid, linewidth=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
        ax.tick_params(colors=muted)
    means = [results[s]["rouge_mean"] or 0 for s in setups]
    ax1.bar(setups, means, color=[colors[s] for s in setups], width=0.55)
    ax1.axhline(ceiling_mean, color=text, linewidth=1.2, linestyle="--")
    ax1.text(len(setups) - 0.5, ceiling_mean, f" human ceiling {ceiling_mean:.2f}", color=text, va="bottom", ha="right")
    for i, v in enumerate(means):
        ax1.text(i, v, f"{v:.2f}", ha="center", va="bottom", color=text)
    ax1.set_title("Closeness to human replies\n(best-match ROUGE-L, 80 test cards)", color=text, loc="left", fontsize=12)
    ax1.set_ylim(0, max(means + [ceiling_mean]) * 1.25)
    width = 0.38
    xs = range(len(setups))
    test_rates = [100 * results[s]["test_leaks"] / results[s]["test_cases"] for s in setups]
    adv_rates = [100 * results[s]["adv_leaks"] / max(results[s]["adv_cases"], 1) for s in setups]
    ax2.bar([x - width / 2 for x in xs], test_rates, width=width, color=[colors[s] for s in setups], label="test cards")
    ax2.bar([x + width / 2 for x in xs], adv_rates, width=width, color=[colors[s] for s in setups], hatch="//",
            edgecolor=surface, label="adversarial cases")
    for x, v in zip(xs, test_rates):
        ax2.text(x - width / 2, v, f"{v:.0f}%", ha="center", va="bottom", color=text)
    for x, v in zip(xs, adv_rates):
        ax2.text(x + width / 2, v, f"{v:.0f}%", ha="center", va="bottom", color=text)
    ax2.set_xticks(list(xs), setups)
    ax2.set_title("Replies flagged as leaking the fix\n(leak check; plain = test cards, hatched = adversarial)",
                  color=text, loc="left", fontsize=12)
    ax2.set_ylim(0, max(test_rates + adv_rates + [10]) * 1.3)
    ax2.set_ylabel("% of replies", color=text)
    labels = " | ".join(f"{s} = {SETUP_NAMES[s]}" for s in setups)
    fig.text(0.01, 0.01, labels, color=muted, fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(ROOT / "docs" / "figures" / "m3_b_vs_c.png", facecolor=surface)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job", required=True, help="evaluation pipeline job id")
    parser.add_argument("--adversarial-uri", required=True)
    args = parser.parse_args()
    cases = {c["id"]: c for c in (card_to_case(card) for card in load_jsonl(M1_TEST_DATASET_URI))}
    for case in load_jsonl(args.adversarial_uri):
        validate_case_messages(case["messages"])
        cases[case["id"]] = case
    ceiling = human_ceiling([c for c in cases.values() if c["source"] == "test_split"])
    results = score(cases, predictions_from_job(args.job))
    write_outputs(results, cases, ceiling, args.job, args.adversarial_uri)
    print((ROOT / "docs" / "results" / "m3_eval.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
