"""Chainlit tutor app (Session 4 practice): the student chats, the deployed fine-tuned model answers.

Run: uv run chainlit run src/app/main.py   (needs GCP_ENDPOINT_ID in .env and an active endpoint)
Replay mode (demo plan B, no endpoint): DEMO_MODE=replay uv run chainlit run src/app/main.py
The conversation is sent WITHOUT a system prompt: the endpoint's handler adds it (docs/m5-serving-rules.md).
"""

import os
import sys
from pathlib import Path

# Chainlit loads this file by its path: put the repo root on the import path so `src` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import chainlit as cl  # noqa: E402

REPLAY = os.getenv("DEMO_MODE") == "replay"
if REPLAY:
    from src.app.replay import banner, load_replay, menu, render
else:
    from src.app.endpoint_client import TutorEndpoint
    from src.app.tracing import tracing_enabled
    from src.app.turn import answer_turn
    from src.constants import REGION

    LANGFUSE = None
    if tracing_enabled():
        from langfuse import Langfuse

        # Chainlit and its FastAPI server emit their own OpenTelemetry spans (scopes "chainlit" and
        # "fastapi", seen in the stored spans): keep them out of Langfuse (Session 5 practice).
        LANGFUSE = Langfuse(blocked_instrumentation_scopes=["chainlit", "fastapi"])

WELCOME = (
    "Hi! Paste the problem statement and your buggy Python code, then tell me what goes wrong. "
    "I will help you find the bug with questions, not by giving you the fix."
)


@cl.on_chat_start
async def start() -> None:
    if REPLAY:
        data = load_replay()
        cl.user_session.set("replay", data)
        await cl.Message(content=banner(data) + "\n\n" + menu(data)).send()
        return
    cl.user_session.set("history", [])
    endpoint = TutorEndpoint()
    cl.user_session.set("endpoint", endpoint)
    cl.user_session.set("model_info", endpoint.deployed_model_info() if LANGFUSE else {})
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    if REPLAY:
        data = cl.user_session.get("replay")
        await cl.Message(content=render(data, message.content) + "\n\n---\n" + menu(data)).send()
        return
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    try:
        result = await cl.make_async(answer_turn)(
            LANGFUSE, cl.user_session.get("endpoint"), list(history), cl.user_session.get("model_info"), REGION
        )
    except Exception as error:  # show the failure, keep the conversation consistent
        history.pop()
        await cl.Message(content=f"Sorry, the tutor is unavailable right now ({type(error).__name__}).").send()
        return
    finally:
        if LANGFUSE:
            LANGFUSE.flush()
    if result["outcome"] == "input_blocked":
        history.pop()  # the blocked message is not part of the tutoring conversation
    else:
        history.append({"role": "assistant", "content": result["reply"]})
    await cl.Message(content=result["reply"]).send()
