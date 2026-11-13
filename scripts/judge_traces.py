"""Score the replayed traces with three LLM-as-a-judge evaluators and write the scores back to Langfuse.

Evaluators (templates in eval/judge_prompts.py): socratic_quality (1 to 5), leak (0/1), confirms_incorrect_fix (0/1).
Judge: gpt-4o-mini through OpenRouter's OpenAI-compatible API (key OPENAI_API_KEY in .env, an OpenRouter key),
temperature 0, JSON answer. Run by script rather than by Langfuse's UI evaluator because confirms_incorrect_fix
needs the known bug (a background field of the test card, never shown to the tutor).

Input: endpoint-generation observations of the traffic replay, read from Langfuse's ClickHouse table events_full (events_core cuts text at 200 characters; v4 has no
trace read API). Output: scores on each trace in Langfuse, docs/results/m7_judge_scores.{csv,md}.
NOT calibrated against human labels.

Usage: uv run --no-dev python -m scripts.judge_traces --since "2026-11-12 23:53:00" [--limit N]
"""

import argparse
import csv
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from eval.judge_prompts import CONFIRMS_INCORRECT_FIX, LEAK, SOCRATIC_QUALITY
from eval.run_eval import load_cases

ROOT = Path(__file__).resolve().parents[1]
LANGFUSE_DIR = Path.home() / "langfuse-selfhost"
JUDGE_MODEL = "openai/gpt-4o-mini"
BASE_URL = "https://openrouter.ai/api/v1"
# OpenRouter /api/v1/models, read 2026-11-13 00:05 UTC: USD per token
PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6
OUT_CSV = ROOT / "docs/results/m7_judge_scores.csv"
OUT_MD = ROOT / "docs/results/m7_judge_scores.md"

EVALUATORS = {
    "socratic_quality": (SOCRATIC_QUALITY, {"type": "integer", "enum": [1, 2, 3, 4, 5]}),
    "leak": (LEAK, {"type": "integer", "enum": [0, 1]}),
    "confirms_incorrect_fix": (CONFIRMS_INCORRECT_FIX, {"type": "integer", "enum": [0, 1]}),
}


def fetch_generations(since: str) -> list[dict]:
    query = (
        "SELECT trace_id, span_id, toString(input) AS input, toString(output) AS output FROM events_full "
        f"WHERE name = 'endpoint-generation' AND start_time >= '{since}' ORDER BY start_time FORMAT JSONEachRow"
    )
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "clickhouse", "clickhouse-client", "--password", "clickhouse", "--query", query],
        cwd=LANGFUSE_DIR, capture_output=True, text=True, check=True,
    ).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def match_case(messages: list[dict], cases: list[dict]) -> dict | None:
    history = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    for case in cases:
        if [{"role": m["role"], "content": m["content"]} for m in case["messages"]] == history:
            return case
    return None


def judge(client: OpenAI, template: str, schema: dict, conversation: str, reply: str, bug: str) -> dict:
    prompt = template.replace("{{input}}", conversation).replace("{{output}}", reply).replace("{{bug}}", bug)
    response = client.chat.completions.create(
        model=JUDGE_MODEL, temperature=0,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": {
            "type": "object", "additionalProperties": False, "required": ["reasoning", "score"],
            "properties": {"reasoning": {"type": "string"}, "score": schema}}}},
    )
    verdict = json.loads(response.choices[0].message.content)
    return {"score": int(verdict["score"]), "reasoning": verdict["reasoning"],
            "tokens_in": response.usage.prompt_tokens, "tokens_out": response.usage.completion_tokens}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="UTC start time of the replay, e.g. '2026-11-12 23:53:00'")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    client = OpenAI(base_url=BASE_URL, api_key=os.environ["OPENAI_API_KEY"])
    from langfuse import Langfuse

    langfuse = Langfuse()
    cases = list(load_cases([ROOT / "eval/test_cards.jsonl"], [ROOT / "eval/triples_adversarial.jsonl"]).values())
    cards = {json.loads(l)["example_id"]: json.loads(l) for l in open(ROOT / "eval/test_cards.jsonl") if l.strip()}
    generations = fetch_generations(args.since)[: args.limit]

    def work(gen: dict) -> list[dict]:
        messages = json.loads(gen["input"])
        reply = json.loads(gen["output"])["response"]
        case = match_case(messages, cases)
        card = cards.get(case["id"]) if case else None
        bug = card["bug_desc"] if card else "unknown (hand-written adversarial case)"
        conversation = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        rows = []
        for name, (template, schema) in EVALUATORS.items():
            result = judge(client, template, schema, conversation, reply, bug)
            rows.append({"trace_id": gen["trace_id"], "observation_id": gen["span_id"],
                         "case_id": case["id"] if case else "", "category": case["category"] if case else "",
                         "evaluator": name, **result})
        return rows

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [r for batch in pool.map(work, generations) for r in batch]
    for r in rows:
        langfuse.create_score(name=r["evaluator"], value=r["score"], trace_id=r["trace_id"],
                              score_id=f"judge-{r['trace_id']}-{r['evaluator']}",  # rerun = overwrite, not duplicate
                              observation_id=r["observation_id"], data_type="NUMERIC",
                              comment=r["reasoning"], metadata={"judge": JUDGE_MODEL, "calibrated": False})
    langfuse.flush()

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    tokens_in = sum(r["tokens_in"] for r in rows)
    tokens_out = sum(r["tokens_out"] for r in rows)
    cost = tokens_in * PRICE_IN + tokens_out * PRICE_OUT
    lines = ["# M7 LLM-as-a-judge scores on the replayed traces", "",
             f"Judge {JUDGE_MODEL} via OpenRouter, temperature 0, JSON schema answer. Script `scripts/judge_traces.py`, "
             f"traces since {args.since} UTC. **Not calibrated against human labels.** Rows: `m7_judge_scores.csv`.", "",
             f"Traces judged: {len(generations)} (every endpoint-generation; input-blocked turns have no model reply). "
             f"Matched to a case: {sum(1 for r in rows if r['case_id']) // len(EVALUATORS)}.", "",
             f"Judge tokens: {tokens_in} in, {tokens_out} out. Cost at OpenRouter's listed price "
             f"(0.15 / 0.60 USD per 1M): ${cost:.4f} (${cost / len(generations):.5f} per trace, 3 evaluators).", ""]
    for name in EVALUATORS:
        sel = [r for r in rows if r["evaluator"] == name]
        for label, part in (("all", sel), ("test cards", [r for r in sel if r["category"] == "socratic_turn"]),
                            ("adversarial", [r for r in sel if r["category"] not in ("socratic_turn", "")])):
            if not part:
                continue
            dist = Counter(r["score"] for r in part)
            mean = sum(r["score"] for r in part) / len(part)
            lines.append(f"- **{name}**, {label} (n = {len(part)}): "
                         + ", ".join(f"{k}: {dist[k]}" for k in sorted(dist)) + f"; mean {mean:.2f}")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
