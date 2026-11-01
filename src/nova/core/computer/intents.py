"""Deterministic parsing for explicit launches from NOVA's discovered app catalogue."""

from __future__ import annotations

import re
from typing import Iterable

_OPEN_PREFIX = re.compile(
    r"^(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+please)?[.!?]*$",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def requested_application_name(message: str) -> str | None:
    """Return the target for a standalone open/launch/start request."""
    match = _OPEN_PREFIX.fullmatch(message.strip())
    return _normalize(match.group(1)) if match else None


def match_open_application_command(
    message: str,
    applications: Iterable[dict[str, str]],
) -> dict[str, str] | None:
    """Match a unique discovered app by exact name or unique name prefix."""
    requested = requested_application_name(message)
    if not requested:
        return None
    catalogue = list(applications)
    exact = [
        app for app in catalogue
        if _normalize(str(app.get("name", ""))) == requested
    ]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    # Allows "open Outlook" to match a single catalogue entry such as "Outlook (new)".
    prefix = [
        app for app in catalogue
        if _normalize(str(app.get("name", ""))).startswith(requested + " ")
    ]
    if len(prefix) == 1:
        return prefix[0]
    # Friendly alias for the built-in Windows Settings URI.
    if requested == "settings":
        candidates = [app for app in catalogue if app.get("app_id") == "windows-settings"]
        if len(candidates) == 1:
            return candidates[0]
    return None
