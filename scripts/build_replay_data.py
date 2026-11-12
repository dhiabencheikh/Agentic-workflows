"""Build src/app/replay_data.json: recorded M3 replies for the demo's replay mode (plan B).

Scenarios follow the fixed selection rule of scripts/score_m3.py (no cherry-picking): the first test
card of problems 6, 15 and 24 in id order, and the first ask_for_answer adversarial case. For each:
the conversation as the tutor saw it (no system message), the recorded replies of setups c and b,
the human reference when there is one, and the leak-check status.

Run: uv run --no-dev python -m scripts.build_replay_data
"""

import csv
import json
from pathlib import Path

from src.eval_cases import card_to_case

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "benjosh-socratic-eval-20261112215631"
EXAMPLE_PROBLEMS = ("6", "15", "24")


def load_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    cases = {c["id"]: c for c in (card_to_case(card) for card in load_jsonl(ROOT / "eval" / "test_cards.jsonl"))}
    cases.update({c["id"]: c for c in load_jsonl(ROOT / "eval" / "triples_adversarial.jsonl")})
    rows = {(r["setup"], r["case_id"]): r for r in csv.DictReader(open(ROOT / "docs" / "results" / "m3_eval_cases.csv", encoding="utf-8"))}
    test_ids = sorted(cid for cid, c in cases.items() if c["source"] == "test_split")
    chosen = [next(cid for cid in test_ids if cases[cid]["problem_id"] == pid) for pid in EXAMPLE_PROBLEMS]
    chosen.append(sorted(cid for cid, c in cases.items() if c.get("category") == "ask_for_answer")[0])
    scenarios = []
    for cid in chosen:
        case = cases[cid]
        scenarios.append({
            "case_id": cid,
            "category": case["category"],
            "messages": case["messages"],
            "reference": case.get("reference"),
            "replies": {s: {"response": rows[(s, cid)]["response"], "status": rows[(s, cid)]["status"]} for s in ("c", "b")},
        })
    out = {"source_run": RUN_ID, "selection_rule": "first test card of problems 6, 15, 24; first ask_for_answer case",
           "setups": {"c": "fine-tuned + prompt v1.0.0", "b": "base + prompt v1.0.0"}, "scenarios": scenarios}
    target = ROOT / "src" / "app" / "replay_data.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(scenarios)} scenarios from run {RUN_ID} -> {target}")


if __name__ == "__main__":
    main()
