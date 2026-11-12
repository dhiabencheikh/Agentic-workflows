"""Calibrate the leak check: false alarms on human tutor replies, catch rate on known leaks.

Tuning uses TRAIN and VALIDATION only (human replies + eval/fixtures/leaks_trainval.jsonl).
The test split (80 cards, 207 human replies, 36 hand-written leaks in eval/fixtures/leaks_test.jsonl)
is measured only with --final-test, once the rules are frozen, and only totals are printed.

Run:
  uv run --no-dev python -m scripts.calibrate_leak_check                 # tuning view (train, validation)
  uv run --no-dev python -m scripts.calibrate_leak_check --final-test --out docs/results/m4_leak_calibration_figures.md
"""

import argparse
import json
from pathlib import Path

import fsspec

from eval import leak_checks
from eval.leak_checks import check_leak
from src.constants import BUCKET_NAME

ROOT = Path(__file__).resolve().parents[1]
M1_ARTIFACTS = (
    f"gs://{BUCKET_NAME}/vertexai-pipeline-root/123905721265/model-training-pipeline-20261112142518/"
    "data-transformation-component_5095698870994731008"
)
CATEGORIES = {"A": "full corrected function", "B": "fix stated outright", "C": "line rewritten"}


def load_jsonl(path) -> list:
    with fsspec.open(str(path), "r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def measure(split: str, show_examples: bool) -> dict:
    cards = load_jsonl(f"{M1_ARTIFACTS}/{split}_dataset")
    keys = {(c["problem_id"], c["bug_id"]): (c["bug_code"], c["bug_fixes"]) for c in cards}
    replies = [(c, r) for c in cards for r in [c["messages"][-1]["content"], *c["reference_alternatives"]]]
    alarms = [(c["example_id"], r, res) for c, r in replies if (res := check_leak(r, c["bug_code"], c["bug_fixes"]))["is_leak"]]
    fixture = ROOT / "eval" / "fixtures" / ("leaks_test.jsonl" if split == "test" else "leaks_trainval.jsonl")
    leaks = [x for x in load_jsonl(fixture) if x["split"] == split]
    caught, missed = {k: [0, 0] for k in CATEGORIES}, []
    for x in leaks:
        hit = check_leak(x["reply"], *keys[(x["problem_id"], x["bug_id"])])["is_leak"]
        caught[x["category"]][0] += hit
        caught[x["category"]][1] += 1
        if not hit:
            missed.append(x)
    result = {"split": split, "replies": len(replies), "alarms": len(alarms), "caught": caught,
              "leaks": len(leaks), "hits": sum(v[0] for v in caught.values())}
    if show_examples:
        result["alarm_examples"] = alarms
        result["missed_examples"] = missed
    return result


def table(results: list) -> list:
    lines = [
        "| Split | False alarms on human replies | Leaks caught: A full function | B fix stated | C line rewritten | All known leaks |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        cat = lambda k: f"{r['caught'][k][0]}/{r['caught'][k][1]}"
        lines.append(
            f"| {r['split']} | {r['alarms']}/{r['replies']} ({r['alarms'] / r['replies']:.1%}) | {cat('A')} | {cat('B')} | "
            f"{cat('C')} | {r['hits']}/{r['leaks']} ({r['hits'] / r['leaks']:.0%}) |"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--final-test", action="store_true", help="also measure test (rules must be frozen)")
    parser.add_argument("--out", help="markdown file for the figures")
    args = parser.parse_args()
    results = [measure("train", True), measure("validation", True)]
    if args.final_test:
        results.append(measure("test", False))
    settings = f"REWRITE_SIMILARITY={leak_checks.REWRITE_SIMILARITY}, MIN_LINE_TOKENS={leak_checks.MIN_LINE_TOKENS}"
    lines = [f"Leak check settings: {settings}", "", *table(results)]
    print("\n".join(lines))
    for r in results[:2]:
        print(f"\n[{r['split']}] false alarms ({r['alarms']}):")
        for example_id, reply, res in r["alarm_examples"]:
            print(f"  {example_id}: {reply[:120]!r} -> {res['leak_type']}: {res['reason'][:100]}")
        print(f"[{r['split']}] missed leaks ({len(r['missed_examples'])}):")
        for x in r["missed_examples"]:
            print(f"  {x['problem_id']}_{x['bug_id']} {x['category']}: {x['reply'][:120]!r}")
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
