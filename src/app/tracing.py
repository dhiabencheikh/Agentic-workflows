"""Langfuse tracing of the live tutor (Session 5 practice).

One trace per student message:
- span "tutor-turn": input = the raw student message, output = the reply shown to the student
- nested generation "endpoint-generation": input = the chat messages sent to the model, i.e. the
  server-side system prompt + the conversation (the Phi-3 chat template is applied inside the
  endpoint), model parameters = GENERATION_PARAMETERS, output = the raw prediction; metadata: model,
  deployed model version, prompt version, endpoint, latencies; token usage; level ERROR on failure.
Tracing is optional: without LANGFUSE_* keys in .env the app runs untraced.
"""

import os
from typing import Any

from src.prompts import TUTOR_PROMPT_VERSION, load_tutor_prompt
from src.serving_contract import GENERATION_PARAMETERS

MODEL_NAME = "phi-3-mini-4k-instruct + LoRA (benjosh-socratic-tutor)"


def tracing_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def generation_input(history: list) -> list:
    """What the model receives before templating: the server-side prompt once, then the conversation."""
    return [{"role": "system", "content": load_tutor_prompt(TUTOR_PROMPT_VERSION)}, *history]


def generation_metadata(prediction: dict | None, model_info: dict, region: str) -> dict[str, Any]:
    meta = {"prompt_version": TUTOR_PROMPT_VERSION, "region": region, **model_info}
    if prediction:
        meta.update({
            "server_latency_seconds": prediction.get("latency_seconds"),
            "round_trip_seconds": prediction.get("round_trip_seconds"),
            "served_prompt_version": prediction.get("prompt_version"),
            "served_model": prediction.get("model"),
        })
    return meta


def usage(prediction: dict) -> dict[str, int]:
    return {"input": int(prediction.get("input_tokens") or 0), "output": int(prediction.get("output_tokens") or 0)}


def traced_reply(langfuse, endpoint, history: list, user_message: str, model_info: dict, region: str) -> str:
    """Call the endpoint inside a span with a nested generation; returns the reply shown to the student."""
    with langfuse.start_as_current_span(name="tutor-turn", input=user_message) as span:
        with langfuse.start_as_current_generation(
            name="endpoint-generation",
            model=MODEL_NAME,
            model_parameters={k: str(v) for k, v in GENERATION_PARAMETERS.items()},
            input=generation_input(history),
            metadata=generation_metadata(None, model_info, region),
            version=TUTOR_PROMPT_VERSION,
        ) as generation:
            try:
                prediction = endpoint.reply(history)
            except Exception as error:
                generation.update(level="ERROR", status_message=f"{type(error).__name__}: {error}")
                span.update(level="ERROR", status_message=str(error), output=None)
                raise
            generation.update(
                output=prediction,
                usage_details=usage(prediction),
                metadata=generation_metadata(prediction, model_info, region),
            )
        reply = prediction["response"]
        span.update(output=reply)
    return reply
