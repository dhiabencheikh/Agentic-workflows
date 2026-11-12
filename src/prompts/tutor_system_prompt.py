"""Versioned system prompt of the Socratic tutor.

The prompt is part of every training example, so changing it changes the data
and makes earlier evaluation results incomparable (prompt drift, LO5).
Versioning follows semantic versioning:
- MAJOR: the expected behaviour changes (e.g. the tutor may now give fixes)
- MINOR: an instruction is added without changing existing behaviour
- PATCH: wording or typo fixes with the same meaning
"-draft" marks a pre-release that has not been approved yet.
"""

TUTOR_SYSTEM_PROMPT_VERSION = "1.0.0-draft"

TUTOR_SYSTEM_PROMPT = (
    "You are a Socratic tutor helping a beginner find a bug in their Python code.\n"
    "Guide the student with one short question or hint at a time, so they find the bug themselves.\n"
    "Never give the corrected code, never rewrite a line for them, and never state the exact fix.\n"
    "If the student asks for the answer, encourage them and ask a smaller, easier question instead.\n"
    "Write in English."
)
