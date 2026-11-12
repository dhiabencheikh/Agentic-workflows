"""The app's client never sends a system prompt and surfaces endpoint errors (no cloud calls)."""

import pytest

from src.app.endpoint_client import build_request, parse_prediction


def test_request_carries_the_conversation_without_system_prompt():
    history = [{"role": "user", "content": "My code fails"}, {"role": "assistant", "content": "What does line 1 do?"},
               {"role": "user", "content": "It subtracts"}]
    request = build_request(history)
    assert request == {"instances": [{"messages": history}]}
    assert "parameters" not in request  # decoding is fixed server-side


def test_a_system_message_in_the_history_is_refused():
    with pytest.raises(ValueError, match="must not send a system message"):
        build_request([{"role": "system", "content": "x"}, {"role": "user", "content": "hi"}])


def test_endpoint_errors_are_raised_not_shown_as_replies():
    with pytest.raises(RuntimeError, match="endpoint error"):
        parse_prediction([{"response": None, "error": "CUDA out of memory"}])
    assert parse_prediction([{"response": "Which line?", "error": None}])["response"] == "Which line?"
