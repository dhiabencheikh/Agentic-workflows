"""Single access point to the versioned tutor system prompt.

The text lives only in `prompts/tutor_system_v<version>.txt`. Every step that
builds a prompt gets it from here (locally) or as a pipeline parameter filled
from here (Vertex components), never from a copy pasted in the code.

Semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR: the promised behaviour changes. Rebuild data, retrain, re-evaluate.
- MINOR: an instruction is added, existing ones kept. Rebuild data, retrain, re-evaluate.
- PATCH: same meaning, different wording. Re-evaluate.
The prompt is inside every training example, and an evaluation score measures
model + prompt together, so scores are only compared within one prompt version.
A released file is never edited: a new version is a new file.
"""

from pathlib import Path

from src.constants import PROJECT_ROOT_PATH

PROMPTS_DIR: Path = PROJECT_ROOT_PATH / "prompts"
TUTOR_PROMPT_VERSION: str = "1.0.0"


def tutor_prompt_path(version: str = TUTOR_PROMPT_VERSION) -> Path:
    """Path of the prompt file for a version (used to copy it next to handler.py)."""
    return PROMPTS_DIR / f"tutor_system_v{version}.txt"


def load_tutor_prompt(version: str = TUTOR_PROMPT_VERSION) -> str:
    """Return the exact prompt text of a version, without the final newline."""
    return tutor_prompt_path(version).read_text(encoding="utf-8").rstrip("\n")
