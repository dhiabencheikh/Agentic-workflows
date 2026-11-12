"""ROUGE-L and best-match, on examples computed by hand."""

import pytest

from eval.similarity import best_match_rouge_l, lcs_length, rouge_l, tokenize


def test_tokenize_lowercases_and_keeps_letters_and_digits():
    assert tokenize("What does `line_3` RETURN?") == ["what", "does", "line", "3", "return"]


def test_lcs_counts_same_order_not_necessarily_adjacent():
    assert lcs_length(list("abcde"), list("ace")) == 3
    assert lcs_length(["a", "b"], ["b", "a"]) == 1
    assert lcs_length([], ["a"]) == 0


def test_rouge_l_by_hand():
    # candidate 7 tokens, reference 5 tokens, common subsequence "what does line 3 return" = 5
    score = rouge_l("What value does line 3 return here?", "What does line 3 return?")
    assert score["precision"] == pytest.approx(5 / 7)
    assert score["recall"] == pytest.approx(5 / 5)
    assert score["f1"] == pytest.approx(2 * (5 / 7) * 1 / (5 / 7 + 1))


def test_identical_and_disjoint_texts():
    assert rouge_l("Can you print i?", "can you print i")["f1"] == pytest.approx(1.0)
    assert rouge_l("Hello there", "What is x?")["f1"] == 0.0
    assert rouge_l("", "What is x?")["f1"] == 0.0


def test_best_match_picks_the_closest_reference():
    result = best_match_rouge_l(
        "How many times does the loop run?",
        reference="What does line 3 return?",
        alternatives=["Can you print i?", "How many times does the for loop run?"],
    )
    assert result["matched"] == "alternative_1"
    assert result["f1"] > rouge_l("How many times does the loop run?", "What does line 3 return?")["f1"]


def test_best_match_without_alternatives_uses_the_reference():
    result = best_match_rouge_l("What does line 3 return?", "What does line 3 return?", [])
    assert result == {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matched": "reference"}
