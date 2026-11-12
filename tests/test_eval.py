"""
Tests for evaluation module: leak detection and suite validation.
"""

from pathlib import Path
import pytest
from eval.leak_checks import check_leak
from eval.run_eval import load_jsonl


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
    eval_dir = Path("eval")
    test_cards = eval_dir / "test_cards.jsonl"
    adversarial = eval_dir / "triples_adversarial.jsonl"

    assert test_cards.exists(), "test_cards.jsonl missing"
    assert adversarial.exists(), "triples_adversarial.jsonl missing"

    cards = load_jsonl(test_cards)
    adv = load_jsonl(adversarial)

    assert len(cards) >= 50, f"Expected at least 50 test cards, got {len(cards)}"
    assert len(adv) >= 10, f"Expected at least 10 adversarial cards, got {len(adv)}"

    # Validate first entry has required fields
    required_keys = {"bug_code", "bug_fixes"}
    assert required_keys.issubset(set(cards[0].keys()))