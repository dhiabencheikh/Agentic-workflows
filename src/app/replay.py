"""Replay mode (demo plan B): shows REAL recorded M3 replies, never live generation.

Kept separate from the live client: no endpoint, no network. Data: src/app/replay_data.json,
built by scripts/build_replay_data.py from run benjosh-socratic-eval-20261112215631.
"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "replay_data.json"


def load_replay(path: Path = DATA) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def banner(data: dict) -> str:
    return (
        "**REPLAY MODE: these are recorded outputs, not live generation.** "
        f"Replies were produced by the models during evaluation run `{data['source_run']}` "
        f"and are shown verbatim. Scenarios: {data['selection_rule']}."
    )


def menu(data: dict) -> str:
    lines = ["Type a number to replay a conversation:"]
    for i, s in enumerate(data["scenarios"], start=1):
        lines.append(f"{i}. `{s['case_id']}` ({s['category'].replace('_', ' ')})")
    return "\n".join(lines)


def render(data: dict, choice: str) -> str:
    """The conversation, then the recorded reply of setup c and, for comparison, setup b."""
    if not choice.strip().isdigit() or not 1 <= int(choice) <= len(data["scenarios"]):
        return f"Please type a number between 1 and {len(data['scenarios'])}.\n\n" + menu(data)
    s = data["scenarios"][int(choice) - 1]
    parts = [f"### Replay {choice}: `{s['case_id']}` (recorded, not live)"]
    for m in s["messages"]:
        who = "Student" if m["role"] == "user" else "Tutor (earlier turn)"
        parts.append(f"**{who}:**\n\n{m['content']}")
    for setup in ("c", "b"):
        reply = s["replies"][setup]
        parts.append(f"**Recorded reply, setup {setup} ({data['setups'][setup]}), leak check: {reply['status']}:**\n\n> "
                     + (reply["response"] or "(no response)").replace("\n", "\n> "))
    if s.get("reference"):
        parts.append(f"**Human tutor (reference):** {s['reference']}")
    return "\n\n".join(parts)
