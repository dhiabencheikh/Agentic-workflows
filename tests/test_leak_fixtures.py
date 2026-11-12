"""The leak-check tuning set never touches test bugs (no contamination of the final test figure)."""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "eval" / "fixtures"
TEST_PROBLEMS = {"6", "7", "15", "24"}


def load(name: str) -> list:
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def test_tuning_leaks_come_only_from_train_and_validation_bugs():
    leaks = load("leaks_trainval.jsonl")
    assert {x["split"] for x in leaks} == {"train", "validation"}
    assert not {x["problem_id"] for x in leaks} & TEST_PROBLEMS
    assert {x["category"] for x in leaks} == {"A", "B", "C"}


def test_test_leaks_are_the_36_hand_written_ones_on_the_6_test_bugs():
    leaks = load("leaks_test.jsonl")
    assert len(leaks) == 36
    assert {x["split"] for x in leaks} == {"test"} and {x["problem_id"] for x in leaks} == TEST_PROBLEMS
    assert {(x["problem_id"], x["bug_id"]) for x in leaks} == {("6", "33"), ("6", "34"), ("7", "35"), ("15", "44"), ("15", "45"), ("24", "29")}
