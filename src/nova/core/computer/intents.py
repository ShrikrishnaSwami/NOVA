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


def application_candidates(
    message: str,
    applications: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    """Return best name matches for a launch request, retaining ambiguity for user choice."""
    requested = requested_application_name(message)
    if not requested:
        return []
    catalogue = list(applications)
    scored: list[tuple[int, dict[str, str]]] = []
    requested_words = set(requested.split())
    for app in catalogue:
        name = _normalize(str(app.get("name", "")))
        if not name:
            continue
        words = set(name.split())
        if name == requested:
            score = 0
        elif name.startswith(requested + " "):
            score = 1
        elif requested in words:
            score = 2
        elif requested_words and requested_words.issubset(words):
            score = 3
        else:
            continue
        scored.append((score, app))
    if not scored and requested in {"settings", "windows settings"}:
        scored = [
            (0, app) for app in catalogue
            if app.get("app_id") == "windows-settings"
        ]
    if not scored:
        return []
    best = min(score for score, _ in scored)
    seen: set[str] = set()
    results = []
    for score, app in sorted(scored, key=lambda pair: _normalize(pair[1].get("name", ""))):
        app_id = app.get("app_id", "")
        if score == best and app_id not in seen:
            results.append(app)
            seen.add(app_id)
    return results


def plan_computer_intent(message: str) -> dict[str, object] | None:
    """Recognize narrow, read-only discovery requests and explicit local file actions.

    This planner never executes anything. Its output is only a proposed typed action;
    the desktop must obtain user approval before calling the computer API.
    """
    text = message.strip()
    if not text:
        return None

    # Explicit content search: "search inside my files for ..." / "find text in files ..."
    match = re.fullmatch(
        r"(?:hey[, ]+nova[, ]+)?(?:please\s+)?(?:search|find)\s+"
        r"(?:inside|within)\s+(?:my\s+)?files\s+for\s+(.+?)[.!?]*",
        text, re.IGNORECASE,
    )
    if match:
        query = match.group(1).strip().strip('"')
        if query:
            return {"action": "search_file_contents", "parameters": {"query": query},
                    "description": f"search accessible files for the text '{query}'"}

    # Filename search: "find my resume", "look for physics assignment".
    match = re.fullmatch(
        r"(?:hey[, ]+nova[, ]+)?(?:please\s+)?"
        r"(?:find|locate|look\s+for|search\s+for)\s+"
        r"(?:my\s+)?(.+?)[.!?]*",
        text, re.IGNORECASE,
    )
    if match:
        query = match.group(1).strip().strip('"')
        query = re.sub(r"\s+(?:file|files|document|documents)$", "", query, flags=re.IGNORECASE).strip()
        if query and len(query) <= 120:
            return {"action": "search_files", "parameters": {"query": query},
                    "description": f"search all accessible drives for files or folders matching '{query}'"}

    # An explicit full path is required for opening or reading a specific item.
    match = re.fullmatch(r"(?:please\s+)?(?:open|show)\s+([A-Za-z]:\\[^\r\n]+)", text, re.IGNORECASE)
    if match:
        path = match.group(1).strip().strip('"')
        return {"action": "open_path", "parameters": {"path": path},
                "description": f"open the local item {path}"}

    match = re.fullmatch(r"(?:please\s+)?read\s+([A-Za-z]:\\[^\r\n]+)", text, re.IGNORECASE)
    if match:
        path = match.group(1).strip().strip('"')
        return {"action": "read_text_file", "parameters": {"path": path},
                "description": f"read the local document {path} and display it only inside NOVA"}

    match = re.fullmatch(r"(?:please\s+)?(?:list|show)\s+(?:the\s+)?(?:files|contents)\s+in\s+([A-Za-z]:\\[^\r\n]+)", text, re.IGNORECASE)
    if match:
        path = match.group(1).strip().strip('"')
        return {"action": "list_directory", "parameters": {"path": path},
                "description": f"list the contents of {path}"}

    return None


def plan_os_query(message: str) -> dict[str, str] | None:
    """Map plain-language, read-only questions to a small OS-awareness endpoint."""
    normalized = re.sub(r"[^a-z0-9 ]+", " ", message.casefold())
    normalized = " ".join(normalized.split())
    if re.search(r"\b(what|which).{0,30}\b(apps|programs).{0,20}\b(running|open)\b|\b(running|open)\s+(apps|programs|processes)\b", normalized):
        return {"endpoint": "/computer/processes?limit=100", "kind": "processes"}
    if re.search(r"\b(open|visible|active)\s+windows\b|\bwhat\s+windows\s+(are\s+)?open\b", normalized):
        return {"endpoint": "/computer/windows?limit=100", "kind": "windows"}
    if re.search(r"\b(what|which).{0,30}\b(window|app).{0,20}\b(active|foreground|focused)\b|\bwhat\s+am\s+i\s+looking\s+at\b|\bwhat\s+is\s+on\s+my\s+screen\b", normalized):
        return {"endpoint": "/computer/windows?limit=20", "kind": "windows"}
    if re.search(r"\b(system info|system information|computer specs|pc specs|about this computer|system overview)\b", normalized):
        return {"endpoint": "/computer/system", "kind": "system"}
    return None



def plan_window_intent(message: str) -> dict[str, str] | None:
    """Recognize narrow conversational requests to arrange an existing window."""
    text = message.strip()
    match = re.fullmatch(
        r"(?:hey[, ]+nova[, ]+)?(?:please\s+)?"
        r"(?:switch\s+to|focus\s+on|bring\s+up|minimize|maximize|restore)\s+"
        r"(?:the\s+)?(.+?)(?:\s+window)?[.!?]*",
        text, re.IGNORECASE,
    )
    if not match:
        return None
    verb = re.match(r"(?:hey[, ]+nova[, ]+)?(?:please\s+)?(switch\s+to|focus\s+on|bring\s+up|minimize|maximize|restore)\b", text, re.IGNORECASE)
    if not verb:
        return None
    target = match.group(1).strip().strip('"')
    if not target or len(target) > 100:
        return None
    action = "focus" if verb.group(1).casefold() in {"switch to", "focus on", "bring up"} else verb.group(1).casefold()
    return {"target": target, "action": action}



def plan_system_intent(message: str) -> dict[str, object] | None:
    """Recognize a few bounded Windows system actions; execution still needs approval."""
    text = message.strip()
    match = re.fullmatch(
        r"(?:hey[, ]+nova[, ]+)?(?:please\s+)?(?:set|change)\s+(?:the\s+)?"
        r"(volume|brightness)\s+(?:to\s+)?(\d{1,3})\s*%?[.!?]*",
        text, re.IGNORECASE,
    )
    if match:
        control = match.group(1).casefold()
        percent = int(match.group(2))
        if percent > 100:
            return None
        return {
            "kind": control,
            "endpoint": f"/computer/system/{control}",
            "payload": {"percent": percent, "approved": True},
            "description": f"set Windows {control} to {percent} percent",
        }
    match = re.fullmatch(
        r"(?:hey[, ]+nova[, ]+)?(?:please\s+)?"
        r"(?:search\s+windows\s+for|use\s+windows\s+search\s+for)\s+(.+?)[.!?]*",
        text, re.IGNORECASE,
    )
    if match:
        query = match.group(1).strip().strip('"')
        if query and len(query) <= 200:
            return {
                "kind": "search",
                "endpoint": "/computer/windows/search",
                "payload": {"query": query, "approved": True},
                "description": f"open Windows Search for '{query}'",
            }
    return None



def plan_multi_step_intent(message: str) -> list[dict[str, object]] | None:
    """Plan up to five explicitly chained, supported system/window actions."""
    parts = re.split(r"\s+then\s+", message.strip(), flags=re.IGNORECASE)
    if len(parts) < 2 or len(parts) > 5:
        return None
    steps: list[dict[str, object]] = []
    for part in parts:
        system = plan_system_intent(part)
        if system:
            steps.append({"kind": "system", **system})
            continue
        window = plan_window_intent(part)
        if window:
            steps.append({"kind": "window", **window})
            continue
        return None
    return steps if len(steps) == len(parts) else None
