"""Input guardrail against prompt injection (Session 5: prompt injection, guardrails).

A fast, deterministic check of the student's LATEST message before the model is called. If the message
tries to override the tutor's rules, the app answers with a fixed Socratic redirection and the model is
not called. Plain Python, no model: it runs in the app and in CI.

The patterns are generic families of injection, not copies of our test cases. Measured block and
false-block rates: docs/results/m6_guardrail.md (the injection cases were read before writing the
patterns, so their block rate is optimistic).
"""

import re

# (family, pattern). Case-insensitive.
INJECTION_PATTERNS = [
    ("override_rules", r"\b(ignore|disregard|forget|bypass|override)\b[^.\n]{0,40}\b(rules?|instructions?|guidelines?|constraints?|role|prompt|previous|above)\b"),
    ("rules_suspended", r"\b(rules?|constraints?|role|guidelines?)\b[^.\n]{0,25}\b(suspended|disabled|lifted|off|no longer apply)\b"),
    ("fake_system", r"(^|\n)\s*(```\s*)?(system|admin|developer)\s*[:\]]|\[\s*(admin|system|developer)[^\]]*\]"),
    ("mode_switch", r"\b(dan|developer|admin|god|jailbreak|debugging)\s+mode\b|\byou are now (a|an|the)\b"),
    ("fake_assistant_turn", r"(^|\n)\s*assistant\s*:"),
    ("exfiltrate_secrets", r"\b(hidden|system)\s+(instructions?|prompt)\b|\banswer key\b|\bbug_fixes\b"),
    ("authority_claim", r"\bi am (the|your) (professor|teacher|developer|admin|instructor)\b"),
]
COMPILED = [(family, re.compile(pattern, re.IGNORECASE)) for family, pattern in INJECTION_PATTERNS]

SAFE_REPLY = (
    "I can't change how I help you, but I'm happy to keep debugging with you. "
    "Let's go back to your code: what does it return for the first example case, and what did you expect?"
)


def check_input(message: str) -> dict:
    """{"blocked": bool, "family": str | None} for the student's latest message."""
    for family, pattern in COMPILED:
        if pattern.search(message):
            return {"blocked": True, "family": family}
    return {"blocked": False, "family": None}
