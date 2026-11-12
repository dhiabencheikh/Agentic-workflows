"""Output guardrail: check the model's reply before it is shown (defence in depth with src/guardrail.py).

The live app has no answer key, only the student's own code (pasted in their first message). So this
runs the deterministic leak check of eval/leak_checks.py with the student's code and an EMPTY answer
key: it catches a corrected function or a rewritten student line (definition (a)), not a fix stated
only in words. If the reply leaks, the student gets a safe redirection instead.
Measured in docs/results/m6_output_guardrail.md.
"""

import re

from eval.leak_checks import check_leak

SAFE_REPLY = (
    "Let's not jump to the corrected code: you will learn more by finding it yourself. "
    "Which line of your code do you think behaves differently from what you expect, and why?"
)


def student_code(history: list) -> str:
    """The code block of the student's first message (the buggy code they pasted), or ''."""
    first = next((m["content"] for m in history if m["role"] == "user"), "")
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", first, re.DOTALL)
    return blocks[-1] if blocks else ""


def check_reply(reply: str, history: list) -> dict:
    """{"blocked": bool, "leak_type": ..., "reason": ...} for a model reply in this conversation."""
    code = student_code(history)
    if not code:
        return {"blocked": False, "leak_type": None, "reason": "no student code to compare with"}
    result = check_leak(reply, code, "")
    return {"blocked": result["is_leak"], "leak_type": result["leak_type"], "reason": result["reason"]}
