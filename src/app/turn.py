"""One tutor turn, exactly as the app runs it: input guardrail -> traced model call -> output guardrail.

Shared by the Chainlit app (src/app/main.py) and the traffic replay (scripts/replay_traffic.py), so the
monitored path and the demo path are the same code.
"""

from src.app.tracing import new_trace, traced_reply
from src.guardrail import SAFE_REPLY as SAFE_INPUT_REPLY
from src.guardrail import check_input
from src.output_guardrail import SAFE_REPLY as SAFE_OUTPUT_REPLY
from src.output_guardrail import check_reply


def answer_turn(langfuse, endpoint, history: list, model_info: dict, region: str, tags: list | None = None) -> dict:
    """history ends with the student's new message. Returns {"reply", "outcome"}; raises on endpoint errors."""
    message = history[-1]["content"]
    guard = check_input(message)
    if guard["blocked"]:  # the model is not called
        if langfuse:
            with langfuse.start_as_current_span(name="guardrail-block", input=message, output=SAFE_INPUT_REPLY,
                                                metadata=guard, trace_context=new_trace(langfuse)):
                if tags:
                    langfuse.update_current_trace(tags=tags)
        return {"reply": SAFE_INPUT_REPLY, "outcome": "input_blocked"}
    if langfuse:
        reply = traced_reply(langfuse, endpoint, history, message, model_info, region, tags=tags)
    else:
        reply = endpoint.reply(history)["response"]
    verdict = check_reply(reply, history)
    if verdict["blocked"]:
        if langfuse:
            with langfuse.start_as_current_span(name="output-guardrail-block", input=reply, output=SAFE_OUTPUT_REPLY,
                                                metadata=verdict, trace_context=new_trace(langfuse)):
                if tags:
                    langfuse.update_current_trace(tags=tags)
        return {"reply": SAFE_OUTPUT_REPLY, "outcome": "output_blocked"}
    return {"reply": reply, "outcome": "answered"}
