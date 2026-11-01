"""Deterministic, conservative parsing for simple computer commands."""

from __future__ import annotations

import re

_OPEN_APP_PATTERN = re.compile(
    r"^(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?"
    r"(calculator|calc|notepad|paint|file\s+explorer|explorer)"
    r"(?:\s+please)?[.!?]*$",
    re.IGNORECASE,
)

_APP_ALIASES = {
    "windows settings": "windows settings",
    "settings": "windows settings",
    "calc": "calculator",
    "calculator": "calculator",
    "notepad": "notepad",
    "paint": "paint",
    "file explorer": "file explorer",
    "explorer": "file explorer",
}


def match_open_application_command(message: str) -> str | None:
    """Return an allowlisted app for an unambiguous open/launch/start command."""
    match = _OPEN_APP_PATTERN.fullmatch(message.strip())
    if not match:
        return None
    return _APP_ALIASES[re.sub(r"\s+", " ", match.group(1).lower())]
