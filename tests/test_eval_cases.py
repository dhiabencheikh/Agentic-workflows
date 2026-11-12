"""The system prompt reaches the model exactly once in setups b and c, and never in setup a."""

import pytest

from src.eval_cases import build_messages, card_to_case
from src.prompts import load_tutor_prompt

PROMPT = load_tutor_prompt()


def m1_card() -> dict:
    """Shape of an M1 test card: system first, tutor target last."""
    return {
        "example_id": "15_44_x#turn3",
        "problem_id": "15",
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": "Problem statement: ...\nMy code:\n1. def f(): ..."},
            {"role": "assistant", "content": "What does line 1 do?"},
            {"role": "user", "content": "It defines f."},
            {"role": "assistant", "content": "Good. What should f return?"},
        ],
        "reference_alternatives": ["Which value do you expect?"],
        "bug_code": "1. def f(): ...",
        "bug_fixes": "Return 1 on line 1.",
    }


def system_messages(messages: list) -> list:
    return [m for m in messages if m["role"] == "system"]


def test_card_to_case_strips_the_system_prompt_and_moves_the_target_to_reference():
    case = card_to_case(m1_card())
    assert system_messages(case["messages"]) == []
    assert case["messages"][-1] == {"role": "user", "content": "It defines f."}
    assert case["reference"] == "Good. What should f return?"
    assert case["bug_fixes"] == "Return 1 on line 1."
    assert case["reference_alternatives"] == ["Which value do you expect?"]


def test_setup_a_is_truly_prompt_free():
    case = card_to_case(m1_card())
    model_input = build_messages(case["messages"], "a", PROMPT)
    assert system_messages(model_input) == []
    assert all(PROMPT not in m["content"] for m in model_input)


@pytest.mark.parametrize("setup", ["b", "c"])
def test_setups_b_and_c_get_the_prompt_exactly_once(setup):
    case = card_to_case(m1_card())
    model_input = build_messages(case["messages"], setup, PROMPT)
    assert system_messages(model_input) == [{"role": "system", "content": PROMPT}]
    assert model_input[0]["role"] == "system"
    assert sum(PROMPT in m["content"] for m in model_input) == 1


def test_messages_that_still_contain_a_system_prompt_are_refused():
    """Passing raw M1 messages would send the prompt twice in b and c: refused."""
    raw = m1_card()["messages"][:-1]
    with pytest.raises(ValueError, match="must not contain a system message"):
        build_messages(raw, "b", PROMPT)
    with pytest.raises(ValueError, match="must not contain a system message"):
        build_messages(raw, "a", PROMPT)


def test_case_must_end_with_the_student_turn():
    case = card_to_case(m1_card())
    with pytest.raises(ValueError, match="start and end with a user turn"):
        build_messages(case["messages"] + [{"role": "assistant", "content": "x"}], "b", PROMPT)


def test_unknown_setup_and_missing_prompt_are_refused():
    case = card_to_case(m1_card())
    with pytest.raises(ValueError, match="unknown setup"):
        build_messages(case["messages"], "d", PROMPT)
    with pytest.raises(ValueError, match="needs a system prompt"):
        build_messages(case["messages"], "c", None)
