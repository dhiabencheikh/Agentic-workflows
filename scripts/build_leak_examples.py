"""Build known leaking tutor replies for the TRAIN and VALIDATION bugs (tuning set of the leak check).

For each bug, the corrected code is the student's last code block in the longest dialogue
(the dialogues end with the fixed code). Leaks generated:
  A  the full corrected function in a code block
  B  the answer key (bug_fixes) stated outright
  C  each line that changed between the buggy and corrected code, rewritten for the student
     (inline and in a code block)
Test bugs are excluded: their 36 hand-written leaks (eval/fixtures/leaks_test.jsonl) are only
used once, for the final measurement.

Run: uv run --no-dev python -m scripts.build_leak_examples
"""

import difflib
import json
import re
from pathlib import Path

import fsspec

from src.constants import BUCKET_NAME

M1_ARTIFACTS = (
    f"gs://{BUCKET_NAME}/vertexai-pipeline-root/123905721265/model-training-pipeline-20261112142518/"
    "data-transformation-component_5095698870994731008"
)
OUT = Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "leaks_trainval.jsonl"
FENCE = "```"


def strip_numbers(code: str) -> list[str]:
    return [re.sub(r"^\s*\d+\.\s?", "", line).rstrip() for line in code.splitlines() if line.strip()]


def final_code(cards: list[dict]) -> str | None:
    """Last code block written by the student in the longest dialogue of a bug."""
    longest = max(cards, key=lambda c: len(c["messages"]))
    blocks = [
        b for m in longest["messages"] if m["role"] == "user"
        for b in re.findall(r"```python\n(.*?)```", m["content"], re.DOTALL)
    ]
    return blocks[-1] if blocks else None


def leaks_for_bug(split: str, cards: list[dict]) -> list[dict]:
    card = cards[0]
    base = {"split": split, "problem_id": card["problem_id"], "bug_id": card["bug_id"]}
    leaks = [{**base, "category": "B", "reply": f"Here is what to change: {card['bug_fixes']}"}]
    fixed = final_code(cards)
    if fixed is None:
        return leaks
    buggy_lines, fixed_lines = strip_numbers(card["bug_code"]), strip_numbers(fixed)
    if [l.strip() for l in buggy_lines] == [l.strip() for l in fixed_lines]:
        return leaks
    leaks.append({**base, "category": "A",
                  "reply": f"Here is the corrected function:\n{FENCE}python\n" + "\n".join(fixed_lines) + f"\n{FENCE}"})
    matcher = difflib.SequenceMatcher(None, [l.strip() for l in buggy_lines], [l.strip() for l in fixed_lines])
    changed = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            changed += [(i1 + 1, fixed_lines[j].strip()) for j in range(j1, j2) if fixed_lines[j].strip()]
    for line_no, new_line in changed[:2]:
        leaks.append({**base, "category": "C", "reply": f"Line {line_no} should be `{new_line}`."})
        leaks.append({**base, "category": "C",
                      "reply": f"Rewrite line {line_no} as:\n{FENCE}python\n{new_line}\n{FENCE}"})
    return leaks


def main() -> None:
    records = []
    for split in ("train", "validation"):
        with fsspec.open(f"{M1_ARTIFACTS}/{split}_dataset", "r", encoding="utf-8") as file:
            cards = [json.loads(line) for line in file]
        bugs: dict = {}
        for card in cards:
            bugs.setdefault((card["problem_id"], card["bug_id"]), []).append(card)
        for key in sorted(bugs, key=lambda k: (int(k[0]), int(k[1]))):
            records += leaks_for_bug(split, bugs[key])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    by = {}
    for r in records:
        by[(r["split"], r["category"])] = by.get((r["split"], r["category"]), 0) + 1
    print(f"{len(records)} leaking replies written to {OUT}: {dict(sorted(by.items()))}")


if __name__ == "__main__":
    main()
