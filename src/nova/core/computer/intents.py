"""Deterministic parsing for explicit launches from NOVA's discovered app catalogue."""

from __future__ import annotations

import re
from typing import Iterable

_OPEN_PREFIX = re.compile(r"^(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+please)?[.!?]*$", re.IGNORECASE)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def match_open_application_command(
    message: str,
    applications: Iterable[dict[str, str]],
) -> dict[str, str] | None:
    """Match an exact discovered app name; ambiguous names are deliberately ignored."""
    match = _OPEN_PREFIX.fullmatch(message.strip())
    if not match:
        return None
    requested = _normalize(match.group(1))
    if not requested:
        return None
    candidates = [
        app for app in applications
        if _normalize(str(app.get("name", ""))) == requested
    ]
    if len(candidates) == 1:
        return candidates[0]
    # Friendly, deterministic alias for the built-in Settings URI.
    if requested == "settings":
        candidates = [
            app for app in applications
            if app.get("app_id") == "windows-settings"
        ]
        if len(candidates) == 1:
            return candidates[0]
    return None
