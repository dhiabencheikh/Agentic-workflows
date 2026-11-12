"""
Evaluation runner for the Socratic Tutor pipeline.

Evaluates test cases against:
1. Deterministic Leak Checks (eval/leak_checks.py)
2. Pedagogical LLM Judge (Socratic effectiveness, guidance, tone)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from eval.leak_checks import check_leak

# Optional imports for LLM Judge
try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases = []
    if not path.exists():
        return cases
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


async def run_llm_judge(judge_llm: Any, student_input: str, tutor_reply: str, bug_code: str) -> dict[str, Any]:
    if not judge_llm:
        return {"score": None, "reasoning": "Judge LLM not configured"}

    prompt = f"""Student Buggy Code:
{bug_code}

Student Input:
{student_input}

Tutor Reply:
{tutor_reply}
"""
    try:
        messages = [
            SystemMessage(content=JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        resp = await judge_llm.ainvoke(messages)
        content = resp.content.strip()
        # strip markdown fence if present
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        return {"score": None, "reasoning": f"Judge error: {e}"}


async def evaluate_suite(
    suite_path: Path,
    mock: bool = False,
    judge_model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    cases = load_jsonl(suite_path)
    if not cases:
        print(f"No cases found in {suite_path}")
        return {"total": 0, "leak_count": 0, "leak_rate": 0.0, "cases": []}

    judge_llm = None
    if not mock and HAS_LANGCHAIN and os.getenv("OPENAI_API_KEY"):
        judge_llm = ChatOpenAI(model=judge_model, temperature=0.0)

    evaluated_cases = []
    leak_count = 0
    total_judge_score = 0.0
    scored_cases_count = 0

    print(f"\nEvaluating {len(cases)} cases from: {suite_path.name}")

    for idx, case in enumerate(cases, 1):
        bug_code = case.get("bug_code", "")
        bug_fixes = case.get("bug_fixes", "")
        student_query = case.get("student_query") or case.get("query", "")
        tutor_reply = case.get("assistant_reply") or case.get("target_reply") or ""

        # If running in live test mode without pre-baked target replies, mock a response
        if not tutor_reply and mock:
            tutor_reply = "What does the line with the operator do? Can you check what values are being compared?"

        # 1. Deterministic Leak Check
        leak_res = check_leak(tutor_reply, bug_code, bug_fixes)
        is_leak = leak_res["is_leak"]
        if is_leak:
            leak_count += 1

        # 2. LLM Judge
        judge_res = {"score": None, "reasoning": "Skipped"}
        if judge_llm and not mock:
            judge_res = await run_llm_judge(judge_llm, student_query, tutor_reply, bug_code)
            if judge_res.get("score") is not None:
                total_judge_score += judge_res["score"]
                scored_cases_count += 1

        result_entry = {
            "id": case.get("id", idx),
            "is_leak": is_leak,
            "leak_type": leak_res["leak_type"],
            "reason": leak_res["reason"],
            "judge_score": judge_res.get("score"),
            "judge_reason": judge_res.get("reasoning"),
        }
        evaluated_cases.append(result_entry)

    leak_rate = (leak_count / len(cases)) if cases else 0.0
    avg_score = (total_judge_score / scored_cases_count) if scored_cases_count else None

    return {
        "suite": suite_path.name,
        "total": len(cases),
        "leak_count": leak_count,
        "leak_rate": round(leak_rate, 4),
        "avg_pedagogy_score": round(avg_score, 2) if avg_score is not None else "N/A",
        "details": evaluated_cases,
    }


async def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--mock", action="store_true", help="Run with mock responses / skip live LLM calls")
    parser.add_argument("--judge-model", default="gpt-4o-mini", help="Model name for judge")
    args = parser.parse_args()

    eval_dir = Path(__file__).parent
    suites = [
        eval_dir / "test_cards.jsonl",
        eval_dir / "triples_adversarial.jsonl",
    ]

    summary = {}
    for suite in suites:
        if suite.exists():
            res = await evaluate_suite(suite, mock=args.mock, judge_model=args.judge_model)
            summary[suite.name] = res
            print(f"Results for {suite.name}:")
            print(f"  Total cases: {res['total']}")
            print(f"  Leaks detected: {res['leak_count']} ({res['leak_rate']*100:.1f}%)")
            print(f"  Avg pedagogy score: {res['avg_pedagogy_score']}")

    output_path = eval_dir / "results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nFull evaluation summary saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())