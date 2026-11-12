"""Evaluation harness runner (M4): leak check on model predictions, with a pass/fail gate for CI.

Inputs use the formats agreed in eval/README.md:
- test cases: M1 test cards (--cards, converted with src.eval_cases.card_to_case) and/or hand-written
  cases (--cases, e.g. eval/triples_adversarial.jsonl);
- predictions (--predictions): one JSON object per (case, setup) with case_id, setup, response, error.

Every case gets one status per setup:
  pass   the response exists and the leak check finds no leak
  leak   the leak check flags the response
  error  no prediction for the case, an empty response, or a non-null error field (never a pass)

Usage:
  uv run --no-dev python -m eval.run_eval --cards eval/test_cards.jsonl \\
      --cases eval/triples_adversarial.jsonl --predictions predictions_c.jsonl \\
      --out eval_results_c.json --max-leak-rate 0.05 --max-error-rate 0
Exit code: 0 within thresholds, 1 a threshold is breached, 2 invalid inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from eval.leak_checks import check_leak
from src.eval_cases import card_to_case, validate_case_messages


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_cases(card_paths: list[Path], case_paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Test cases by id: M1 cards go through card_to_case; hand-written cases are validated."""
    cases: dict[str, dict[str, Any]] = {}
    records = [card_to_case(card) for path in card_paths for card in load_jsonl(path)]
    for path in case_paths:
        for case in load_jsonl(path):
            validate_case_messages(case["messages"])
            records.append(case)
    for case in records:
        if case["id"] in cases:
            raise ValueError(f"duplicate case id {case['id']}")
        cases[case["id"]] = case
    return cases


def case_status(case: dict[str, Any], prediction: dict[str, Any] | None) -> dict[str, Any]:
    """Status of one case for one setup; a missing or failed prediction is an error, never a pass."""
    if prediction is None:
        return {"status": "error", "reason": "no prediction for this case"}
    if prediction.get("error") is not None:
        return {"status": "error", "reason": f"generation error: {prediction['error']}"}
    response = prediction.get("response")
    if not isinstance(response, str) or not response.strip():
        return {"status": "error", "reason": "empty or missing response"}
    leak = check_leak(response, case["bug_code"], case["bug_fixes"])
    if leak["is_leak"]:
        return {"status": "leak", "leak_type": leak["leak_type"], "reason": leak["reason"]}
    return {"status": "pass", "reason": None}


def evaluate(cases: dict[str, dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """Per setup: the status of every case, and totals."""
    by_setup: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    unknown = []
    for prediction in predictions:
        if prediction["case_id"] not in cases:
            unknown.append(prediction["case_id"])
            continue
        by_setup[prediction["setup"]][prediction["case_id"]] = prediction
    report: dict[str, Any] = {"cases": len(cases), "unknown_case_ids": unknown, "setups": {}}
    for setup, preds in sorted(by_setup.items()):
        details = []
        for case_id, case in cases.items():
            result = case_status(case, preds.get(case_id))
            details.append({"case_id": case_id, "category": case.get("category"), **result})
        counts = {s: sum(d["status"] == s for d in details) for s in ("pass", "leak", "error")}
        per_category: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "leak": 0, "error": 0})
        for d in details:
            per_category[d["category"]][d["status"]] += 1
        report["setups"][setup] = {
            **counts,
            "leak_rate": counts["leak"] / len(details),
            "error_rate": counts["error"] / len(details),
            "per_category": dict(per_category),
            "judge": None,  # LLM judge: designed in M3, off unless --judge
            "details": details,
        }
    return report


def breaches(report: dict[str, Any], max_leak_rate: float | None, max_error_rate: float | None) -> list[str]:
    """Threshold breaches, per setup. Unknown case ids in the predictions are a breach too."""
    found = []
    if report["unknown_case_ids"]:
        found.append(f"predictions for unknown case ids: {report['unknown_case_ids'][:5]}")
    if not report["setups"]:
        found.append("no predictions")
    for setup, r in report["setups"].items():
        if max_leak_rate is not None and r["leak_rate"] > max_leak_rate:
            found.append(f"setup {setup}: leak rate {r['leak_rate']:.1%} > {max_leak_rate:.1%}")
        if max_error_rate is not None and r["error_rate"] > max_error_rate:
            found.append(f"setup {setup}: error rate {r['error_rate']:.1%} > {max_error_rate:.1%}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards", type=Path, nargs="*", default=[], help="M1 test cards (JSONL)")
    parser.add_argument("--cases", type=Path, nargs="*", default=[], help="hand-written cases (JSONL)")
    parser.add_argument("--predictions", type=Path, required=True, help="predictions (JSONL, eval/README.md format)")
    parser.add_argument("--out", type=Path, required=True, help="where to write the JSON results")
    parser.add_argument("--max-leak-rate", type=float, default=None, help="fail if a setup's leak rate is higher")
    parser.add_argument("--max-error-rate", type=float, default=None, help="fail if a setup's error rate is higher")
    args = parser.parse_args(argv)

    try:
        cases = load_cases(args.cards, args.cases)
        predictions = load_jsonl(args.predictions)
    except (OSError, ValueError, KeyError) as error:
        print(f"Invalid inputs: {error}", file=sys.stderr)
        return 2
    if not cases:
        print("Invalid inputs: no test cases", file=sys.stderr)
        return 2

    report = evaluate(cases, predictions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for setup, r in report["setups"].items():
        print(f"setup {setup}: {r['pass']} pass, {r['leak']} leak ({r['leak_rate']:.1%}), "
              f"{r['error']} error ({r['error_rate']:.1%}) out of {report['cases']} cases")
    found = breaches(report, args.max_leak_rate, args.max_error_rate)
    for b in found:
        print(f"THRESHOLD BREACHED: {b}", file=sys.stderr)
    print(f"Results written to {args.out}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
