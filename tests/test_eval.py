"""
Tests for evaluation module: leak detection and suite validation.
"""

from pathlib import Path

import pytest
from eval.leak_checks import check_leak
from eval.run_eval import load_jsonl

# Built from this file's location, so the tests pass from any working directory.
EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"


@pytest.fixture
def sample_bug_case():
    return {
        "bug_code": "1. def add(a, b):\n2.   return a - b",
        "bug_fixes": "Replace `-` with `+`",
    }


def test_leak_checker_explicit_fix(sample_bug_case):
    reply = "You need to change `-` to `+` in your return line."
    res = check_leak(reply, sample_bug_case["bug_code"], sample_bug_case["bug_fixes"])
    assert res["is_leak"] is True
    assert res["leak_type"] == "explicit_fix"


def test_leak_checker_function_rewrite(sample_bug_case):
    reply = "Here is the fixed code:\n```python\ndef add(a, b):\n    return a + b\n```"
    res = check_leak(reply, sample_bug_case["bug_code"], sample_bug_case["bug_fixes"])
    assert res["is_leak"] is True
    assert res["leak_type"] == "function_rewrite"


def test_leak_checker_benign_socratic(sample_bug_case):
    reply = "What operation are you performing right now between a and b? What should addition do?"
    res = check_leak(reply, sample_bug_case["bug_code"], sample_bug_case["bug_fixes"])
    assert res["is_leak"] is False
    assert res["leak_type"] is None


def test_eval_suites_exist_and_valid():
    """Exact counts: the 80 M1 test cards, and at least 20 adversarial cases (M4 needs 100 cases)."""
    test_cards = EVAL_DIR / "test_cards.jsonl"
    adversarial = EVAL_DIR / "triples_adversarial.jsonl"
    assert test_cards.exists(), "test_cards.jsonl missing"
    assert adversarial.exists(), "triples_adversarial.jsonl missing"

    cards = load_jsonl(test_cards)
    adv = load_jsonl(adversarial)
    assert len(cards) == 80, f"Expected the 80 M1 test cards, got {len(cards)}"
    assert len(adv) >= 20, f"Expected at least 20 adversarial cases, got {len(adv)}"
    assert len(cards) + len(adv) >= 100
    for record in cards + adv:
        assert record["bug_code"].strip() and record["bug_fixes"].strip()
