"""Prompt templates for the LLM call.

The system prompt lives at ``src/app/prompts/templates/system_prompt.txt`` so
it can be edited without touching Python code (and reviewed as plain prose in
PRs). The file is loaded once at import time; if it's missing we fail loudly
at startup rather than at request time.

The user prompt stays inline because it's a one-line template, not content.
"""

from pathlib import Path

# Anchor to the `app` package root so this works regardless of whether the
# loader lives in `infrastructure/` or anywhere else under `src/app/`.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "prompts" / "templates"

SYSTEM_PROMPT: str = (_TEMPLATES_DIR / "system_prompt.txt").read_text(encoding="utf-8").strip()


def user_prompt(role: str) -> str:
    """Format the per-request user message sent to the LLM.

    Args:
        role: The normalised job-role string.

    Returns:
        A short user-message body of the form ``"Job title: <role>"`` —
        kept tight so the structured-output instructions in the system
        prompt dominate the model's behaviour.
    """
    return f"Job title: {role}"
