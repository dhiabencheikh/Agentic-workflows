"""What the app logs to Langfuse: span = raw message -> reply; nested generation = model input -> raw output."""

from contextlib import contextmanager

import pytest

from src.app.tracing import MODEL_NAME, generation_input, traced_reply
from src.prompts import TUTOR_PROMPT_VERSION, load_tutor_prompt
from src.serving_contract import GENERATION_PARAMETERS


class Observation:
    def __init__(self, kind, **kwargs):
        self.kind, self.fields = kind, dict(kwargs)

    def update(self, **kwargs):
        self.fields.update(kwargs)


class FakeLangfuse:
    def __init__(self):
        self.observations = []

    @contextmanager
    def start_as_current_span(self, **kwargs):
        obs = Observation("span", **kwargs); self.observations.append(obs); yield obs

    @contextmanager
    def start_as_current_generation(self, **kwargs):
        obs = Observation("generation", **kwargs); self.observations.append(obs); yield obs


class FakeEndpoint:
    def __init__(self, error=None):
        self.error = error

    def reply(self, history):
        if self.error:
            raise self.error
        return {"response": "What does line 6 multiply?", "prompt_version": "1.0.0", "input_tokens": 200,
                "output_tokens": 9, "latency_seconds": 1.4, "round_trip_seconds": 1.5, "error": None}


HISTORY = [{"role": "user", "content": "My factorial returns 0."}]
MODEL_INFO = {"endpoint_id": "123", "model_version_id": "1"}


def test_span_has_raw_message_in_and_reply_out():
    lf = FakeLangfuse()
    reply = traced_reply(lf, FakeEndpoint(), HISTORY, "My factorial returns 0.", MODEL_INFO, "europe-west2")
    span = next(o for o in lf.observations if o.kind == "span")
    assert span.fields["input"] == "My factorial returns 0." and span.fields["output"] == reply == "What does line 6 multiply?"


def test_generation_logs_model_input_parameters_output_usage_and_versions():
    lf = FakeLangfuse()
    traced_reply(lf, FakeEndpoint(), HISTORY, "My factorial returns 0.", MODEL_INFO, "europe-west2")
    gen = next(o for o in lf.observations if o.kind == "generation").fields
    assert gen["input"] == generation_input(HISTORY)
    assert [m["role"] for m in gen["input"]].count("system") == 1 and gen["input"][0]["content"] == load_tutor_prompt()
    assert gen["model"] == MODEL_NAME and gen["version"] == TUTOR_PROMPT_VERSION
    assert set(gen["model_parameters"]) == set(GENERATION_PARAMETERS)
    assert gen["output"]["response"] == "What does line 6 multiply?"
    assert gen["usage_details"] == {"input": 200, "output": 9}
    meta = gen["metadata"]
    assert meta["prompt_version"] == "1.0.0" and meta["model_version_id"] == "1" and meta["round_trip_seconds"] == 1.5


def test_an_endpoint_error_is_logged_at_level_error_and_raised():
    lf = FakeLangfuse()
    with pytest.raises(RuntimeError):
        traced_reply(lf, FakeEndpoint(RuntimeError("503 unavailable")), HISTORY, "hi", MODEL_INFO, "europe-west2")
    gen = next(o for o in lf.observations if o.kind == "generation").fields
    assert gen["level"] == "ERROR" and "503 unavailable" in gen["status_message"]
