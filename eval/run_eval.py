"""Evaluation harness runner (M4): leak check on model predictions, with a pass/fail gate for CI.

Inputs use the formats agreed in eval/README.md:
- test cases: M1 test cards (--cards, converted with src.eval_cases.card_to_case) and/or hand-written
  cases (--cases, e.g. eval/triples_adversarial.jsonl);
- predictions (--predictions): one JSON object per (case, setup) with case_id, setup, response, error.

Every case gets one status per setup:
  pass   the response exists and the leak check finds no leak
  leak   the leak check flags the response
  error  no prediction for the case, an empty response, or a non-null error field (never a pass)

The LLM judge is OFF by default: no paid API call happens without --judge (CLAUDE.md: bulk paid calls
need approval). Its prompt, model and cost are designed in M3; --judge-model has no default on purpose.

Usage:
  uv run --no-dev python -m eval.run_eval --cards eval/test_cards.jsonl \\
      --cases eval/triples_adversarial.jsonl --predictions predictions_c.jsonl \\
      --out eval_results_c.json --max-leak-rate 0.05 --max-error-rate 0
Exit code: 0 within thresholds, 1 a threshold is breached, 2 invalid inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from eval.leak_checks import check_leak
from src.eval_cases import card_to_case, validate_case_messages


JUDGE_SYSTEM_PROMPT = """You are an expert pedagogical judge evaluating an AI programming tutor.
Your task is to rate the assistant's reply to a struggling student on a scale from 1 to 5:
- 1: Gives direct answer/code fix, spoon-feeding, or harmful.
- 2: Gives too much away, barely asks questions, weak guidance.
- 3: Moderate guidance, but could be more Socratic or targeted.
- 4: Strong Socratic hint, encourages student reflection without leaking.
- 5: Excellent pedagogical response: identifies misconception, asks targeted question, guides student to self-discovery without giving code away.

Output JSON only in this format:
{"score": <int 1-5>, "reasoning": "<brief explanation>"}
"""


def make_judge(model: str):
    """The judge LLM. Imported only when --judge is given, so default runs need no AI library."""
    from langchain_openai import ChatOpenAI  # optional, not a project dependency yet (M3 decides)

    return ChatOpenAI(model=model, temperature=0.0)


def judge_reply(judge_llm: Any, case: dict[str, Any], response: str) -> dict[str, Any]:
    """Score one reply 1 to 5 with the rubric above; the judge sees the conversation and the reply."""
    conversation = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in case["messages"])
    prompt = f"Conversation so far:\n{conversation}\n\nTutor reply to rate:\n{response}"
    try:
        content = judge_llm.invoke([("system", JUDGE_SYSTEM_PROMPT), ("human", prompt)]).content.strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        result = json.loads(content)
        score = result.get("score")
        if not isinstance(score, int) or not 1 <= score <= 5:
            return {"score": None, "reasoning": f"invalid judge score: {score!r}"}
        return {"score": score, "reasoning": result.get("reasoning")}
    except Exception as error:  # a judge failure is recorded, never turned into a score
        return {"score": None, "reasoning": f"judge error: {error}"}


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


def evaluate(cases: dict[str, dict[str, Any]], predictions: list[dict[str, Any]], judge_llm: Any = None) -> dict[str, Any]:
    """Per setup: the status of every case, and totals. The judge runs only if judge_llm is given."""
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
            if judge_llm is not None and result["status"] != "error":
                result["judge"] = judge_reply(judge_llm, case, preds[case_id]["response"])
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
            "judge": _judge_summary(details) if judge_llm is not None else None,  # off unless --judge
            "details": details,
        }
    return report


def _judge_summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [d["judge"]["score"] for d in details if d.get("judge") and d["judge"]["score"] is not None]
    return {"scored": len(scores), "mean_score": sum(scores) / len(scores) if scores else None}


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
    parser.add_argument("--judge", action="store_true", help="also score replies with the LLM judge (PAID API calls)")
    parser.add_argument("--judge-model", help="judge model name, required with --judge (chosen in M3)")
    args = parser.parse_args(argv)

    judge_llm = None
    if args.judge:
        if not args.judge_model:
            print("Invalid inputs: --judge needs --judge-model (no default: the model is chosen in M3)", file=sys.stderr)
            return 2
        if not os.getenv("OPENAI_API_KEY"):
            print("Invalid inputs: --judge needs OPENAI_API_KEY in the environment", file=sys.stderr)
            return 2
        try:
            judge_llm = make_judge(args.judge_model)
        except ImportError:
            print("Invalid inputs: --judge needs langchain-openai installed", file=sys.stderr)
            return 2

    try:
        cases = load_cases(args.cards, args.cases)
        predictions = load_jsonl(args.predictions)
    except (OSError, ValueError, KeyError) as error:
        print(f"Invalid inputs: {error}", file=sys.stderr)
        return 2
    if not cases:
        print("Invalid inputs: no test cases", file=sys.stderr)
        return 2

    report = evaluate(cases, predictions, judge_llm)
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
