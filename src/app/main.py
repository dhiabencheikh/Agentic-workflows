"""Chainlit tutor app (Session 4 practice): the student chats, the deployed fine-tuned model answers.

Run: uv run chainlit run src/app/main.py   (needs GCP_ENDPOINT_ID in .env and an active endpoint)
The conversation is sent WITHOUT a system prompt: the endpoint's handler adds it (docs/m5-serving-rules.md).
"""

import chainlit as cl

from src.app.endpoint_client import TutorEndpoint

WELCOME = (
    "Hi! Paste the problem statement and your buggy Python code, then tell me what goes wrong. "
    "I will help you find the bug with questions, not by giving you the fix."
)


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set("history", [])
    cl.user_session.set("endpoint", TutorEndpoint())
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    try:
        prediction = await cl.make_async(cl.user_session.get("endpoint").reply)(history)
    except Exception as error:  # show the failure, keep the conversation consistent
        history.pop()
        await cl.Message(content=f"Sorry, the tutor is unavailable right now ({type(error).__name__}).").send()
        return
    history.append({"role": "assistant", "content": prediction["response"]})
    await cl.Message(content=prediction["response"]).send()
