"""Test cases and model inputs for evaluation (formats defined in eval/README.md).

Plain Python only (no AI libraries), so it runs on any laptop and in CI.
"""

SETUPS: dict = {
    "a": {"description": "base Phi-3, no system prompt", "adapter": False, "system_prompt": False},
    "b": {"description": "base Phi-3 + system prompt", "adapter": False, "system_prompt": True},
    "c": {"description": "fine-tuned Phi-3 (LoRA) + system prompt", "adapter": True, "system_prompt": True},
}

BACKGROUND_FIELDS = ("problem_id", "bug_code", "bug_fixes", "reference_alternatives")


def card_to_case(card: dict) -> dict:
    """Turn an M1 card into a test case.

    M1 cards are [system, user, ..., user, assistant(target)]. The system
    message is removed explicitly, the target becomes the reference.
    """
    messages = card["messages"]
    if messages[0]["role"] != "system":
        raise ValueError(f"{card['example_id']}: expected a system message first")
    if messages[-1]["role"] != "assistant":
        raise ValueError(f"{card['example_id']}: expected the tutor reply last")
    case = {
        "id": card["example_id"],
        "source": "test_split",
        "category": "socratic_turn",
        "messages": messages[1:-1],
        "reference": messages[-1]["content"],
        "expected_behaviour": "asks a guiding question or gives a small hint; gives no fix and no corrected code",
        "metrics": ["leak", "similarity", "judge"],
    }
    case.update({field: card[field] for field in BACKGROUND_FIELDS})
    validate_case_messages(case["messages"])
    return case


def validate_case_messages(messages: list) -> None:
    """Enforce the rules of eval/README.md section 1 on a case's messages."""
    if not messages:
        raise ValueError("a case needs at least one message")
    roles = [m["role"] for m in messages]
    if "system" in roles:
        raise ValueError("case messages must not contain a system message: inference adds it per setup")
    if roles[0] != "user" or roles[-1] != "user":
        raise ValueError(f"case messages must start and end with a user turn, got {roles[0]}...{roles[-1]}")
    if any(a == b for a, b in zip(roles, roles[1:])):
        raise ValueError(f"roles must alternate, got {roles}")


def build_messages(case_messages: list, setup: str, system_prompt: str | None) -> list:
    """Model input for one setup: setup a gets no system prompt, b and c exactly one."""
    if setup not in SETUPS:
        raise ValueError(f"unknown setup {setup!r}, expected one of {sorted(SETUPS)}")
    validate_case_messages(case_messages)
    if not SETUPS[setup]["system_prompt"]:
        return list(case_messages)
    if not system_prompt:
        raise ValueError(f"setup {setup} needs a system prompt")
    return [{"role": "system", "content": system_prompt}, *case_messages]
