"""Send the 106 eval cases (80 test + 26 adversarial) through the app's own traced turn, against the live endpoint.

Same code path as a Chainlit message (src/app/turn.py): input guardrail -> traced model call -> output guardrail.
Each case becomes one Langfuse trace tagged "traffic-replay" and its category, so the dashboard has real traffic.
Writes per-case rows to docs/results/m7_traffic_replay.csv and a summary to docs/results/m7_traffic_replay.md.

Usage: uv run --no-dev python -m scripts.replay_traffic [--limit N]
"""

import argparse
import csv
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.run_eval import load_cases
from src.app.endpoint_client import TutorEndpoint
from src.app.tracing import tracing_enabled
from src.app.turn import answer_turn
from src.constants import REGION

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "docs/results/m7_traffic_replay.csv"
OUT_MD = ROOT / "docs/results/m7_traffic_replay.md"


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (no interpolation): the smallest value with at least q% of values at or below it."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))  # ceil
    return ordered[int(rank) - 1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not tracing_enabled():
        raise SystemExit("Langfuse keys missing: this replay exists to populate monitoring")
    from langfuse import Langfuse

    langfuse = Langfuse(blocked_instrumentation_scopes=["chainlit", "fastapi"])
    cases = load_cases([ROOT / "eval/test_cards.jsonl"], [ROOT / "eval/triples_adversarial.jsonl"])
    items = list(cases.values())[: args.limit]
    endpoint = TutorEndpoint()
    model_info = endpoint.deployed_model_info()
    started = datetime.now(timezone.utc)
    rows = []
    for i, case in enumerate(items, 1):
        t0 = time.perf_counter()
        try:
            result = answer_turn(langfuse, endpoint, list(case["messages"]), model_info, REGION,
                                 tags=["traffic-replay", case["category"]])
            outcome, error = result["outcome"], ""
        except Exception as exc:  # counted as an error, the replay continues
            outcome, error = "error", f"{type(exc).__name__}: {exc}"[:200]
        seconds = time.perf_counter() - t0
        rows.append({"id": case["id"], "category": case["category"], "outcome": outcome,
                     "end_to_end_seconds": round(seconds, 3), "error": error})
        print(f"{i}/{len(items)} {case['id']} {outcome} {seconds:.2f}s", flush=True)
    langfuse.flush()
    ended = datetime.now(timezone.utc)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def stats(sel):
        lat = [r["end_to_end_seconds"] for r in sel]
        return (f"{len(sel)} | {percentile(lat, 50):.2f} | {percentile(lat, 95):.2f} | {percentile(lat, 99):.2f} | "
                f"{max(lat):.2f} | {statistics.mean(lat):.2f}") if lat else f"0 | - | - | - | - | -"

    ok = [r for r in rows if r["outcome"] != "error"]
    model_called = [r for r in ok if r["outcome"] != "input_blocked"]
    outcomes = {o: sum(r["outcome"] == o for r in rows) for o in ("answered", "input_blocked", "output_blocked", "error")}
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], {}).setdefault(r["outcome"], 0)
        by_cat[r["category"]][r["outcome"]] += 1
    lines = [
        "# M7 traffic replay: eval cases through the app's traced path",
        "",
        f"Run {started:%Y-%m-%d %H:%M:%S} to {ended:%H:%M:%S} UTC, endpoint {endpoint.endpoint.name} ({REGION}), "
        f"one request at a time, from Dhia's Mac. Script: `scripts/replay_traffic.py`. Rows: `m7_traffic_replay.csv`.",
        "",
        "End-to-end = wall clock of one turn on the client: input guardrail, endpoint call over the internet, "
        "output guardrail, Langfuse span creation (export is asynchronous). Percentiles are nearest-rank.",
        "",
        f"Cases: {len(rows)}. Errors: {outcomes['error']} ({outcomes['error'] / len(rows):.1%}).",
        "",
        "| Outcome | Count |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in outcomes.items()],
        "",
        "| Slice | n | P50 s | P95 s | P99 s | max s | mean s |", "|---|---|---|---|---|---|---|",
        f"| All successful turns | {stats(ok)} |",
        f"| Turns that called the model | {stats(model_called)} |",
        f"| Input-blocked turns (no model call) | {stats([r for r in ok if r['outcome'] == 'input_blocked'])} |",
        "",
        "| Category | Outcomes |", "|---|---|",
        *[f"| {c} | {', '.join(f'{k} {v}' for k, v in sorted(o.items()))} |" for c, o in sorted(by_cat.items())],
        "",
        "With about 100 values, P99 is the largest or second-largest value: read it as an indication, not a stable estimate.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
