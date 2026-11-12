"""Guards for the single source of truth of the tutor system prompt."""

from pathlib import Path

from src.constants import PROJECT_ROOT_PATH
from src.prompts import TUTOR_PROMPT_VERSION, load_tutor_prompt, tutor_prompt_path


def test_current_version_file_exists_and_loads():
    assert tutor_prompt_path().exists()
    prompt = load_tutor_prompt()
    assert prompt.startswith("You are a Socratic tutor")
    assert not prompt.endswith("\n")


def test_version_is_semver():
    parts = TUTOR_PROMPT_VERSION.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def test_prompt_text_is_not_copied_into_code():
    """The prompt must only live in prompts/*.txt: no copy in any Python file."""
    first_line = load_tutor_prompt().splitlines()[0]
    offenders = [
        str(path.relative_to(PROJECT_ROOT_PATH))
        for folder in ("src", "scripts", "notebooks", "tests")
        for path in (PROJECT_ROOT_PATH / folder).rglob("*.py")
        if first_line in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
