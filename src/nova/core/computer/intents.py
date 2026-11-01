"""Natural-language parsing for safe, explicit application launch requests."""

from __future__ import annotations

import re
from typing import Iterable

_COMMAND = re.compile(
    r"^(?:(?:hey|okay)\s+nova[, ]+)?"
    r"(?:(?:can|could|would)\s+you\s+|"
    r"please\s+|"
    r"i\s+(?:want|need)\s+you\s+to\s+|"
    r"i(?:'d|\s+would)\s+like\s+you\s+to\s+)?"
    r"(?:please\s+)?(?:open|launch|start)\s+(?:up\s+)?(?:the\s+)?"
    r"(.+?)"
    r"(?:\s+for\s+me)?(?:\s+please)?[.!?]*$",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def requested_application_name(message: str) -> str | None:
    """Extract an app target only from a standalone open/launch/start request."""
    match = _COMMAND.fullmatch(message.strip())
    return _normalize(match.group(1)) if match else None


def match_open_application_command(
    message: str,
    applications: Iterable[dict[str, str]],
) -> dict[str, str] | None:
    """Match a unique app using exact, prefix, then contained-name matching."""
    requested = requested_application_name(message)
    if not requested:
        return None
    catalogue = list(applications)

    def matches(predicate):
        return [
            app for app in catalogue
            if predicate(_normalize(str(app.get("name", ""))))
        ]

    exact = matches(lambda name: name == requested)
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None

    prefix = matches(lambda name: name.startswith(requested + " "))
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        return None

    contained = matches(lambda name: requested in name.split(" "))
    if len(contained) == 1:
        return contained[0]

    if requested in {"settings", "windows settings"}:
        settings = [app for app in catalogue if app.get("app_id") == "windows-settings"]
        if len(settings) == 1:
            return settings[0]
    return None
