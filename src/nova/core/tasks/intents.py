"""Deterministic natural-language routing for NOVA's scheduled-task controls.

Only the two registered read-only report actions can be created from chat. This
module parses intent; the desktop remains responsible for confirmations and API calls.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def plan_task_intent(message: str, now: datetime | None = None) -> dict[str, Any] | None:
    text = " ".join(message.strip().split())
    if not text:
        return None
    normalized = text.casefold().strip(" .!?")

    if re.fullmatch(r"(?:please )?(?:open|show|manage) (?:my )?(?:scheduled tasks|task manager|schedule)", normalized):
        return {"kind": "open"}
    if re.fullmatch(r"(?:please )?(?:open|show) (?:the )?computer controls", normalized):
        return {"kind": "open_computer"}
    if re.fullmatch(r"(?:please )?(?:open|show|manage) (?:my )?(?:memories|memory manager)", normalized):
        return {"kind": "open_memory"}
    if re.fullmatch(r"(?:please )?(?:open|show) (?:my )?(?:conversation )?history", normalized):
        return {"kind": "open_history"}
    if re.fullmatch(r"(?:please )?(?:show|list|what are) (?:my )?(?:scheduled )?tasks", normalized) or normalized in {"what tasks do i have", "show my tasks"}:
        return {"kind": "list"}

    match = re.fullmatch(r"(?:please )?(pause|cancel) (?:my )?(?:scheduled )?(?:task )?(.+)", normalized)
    if match:
        target = match.group(2).strip(" .!?")
        if target:
            return {"kind": match.group(1), "target": target}

    if not re.match(r"^(?:please )?(?:schedule|create|set up)\b", normalized):
        return None

    action_id = None
    title = None
    if re.search(r"\b(storage|disk|drive)\b", normalized) and re.search(r"\b(report|space|usage)\b", normalized):
        action_id, title = "storage.report", "Storage usage report"
    elif re.search(r"\b(system|computer|pc)\b", normalized) and re.search(r"\b(check|status|snapshot|report)\b", normalized):
        action_id, title = "system.snapshot", "System status snapshot"
    if action_id is None:
        return {"kind": "unsupported", "message": "I can currently schedule a storage usage report or a system status snapshot."}

    local_now = (now or datetime.now().astimezone())
    date_match = re.search(r"\b(tomorrow|today)\b|\b(20\d{2}-\d{2}-\d{2})\b", normalized)
    if not date_match:
        return {"kind": "clarify", "message": "What date should I use? For example: tomorrow at 10 AM."}
    if date_match.group(1) == "tomorrow":
        target_date = (local_now + timedelta(days=1)).date()
    elif date_match.group(1) == "today":
        target_date = local_now.date()
    else:
        try:
            target_date = datetime.strptime(date_match.group(2), "%Y-%m-%d").date()
        except ValueError:
            return {"kind": "clarify", "message": "That date isn't valid. Please use today, tomorrow, or YYYY-MM-DD."}

    time_match = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", normalized)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "0")
        meridiem = time_match.group(3)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return {"kind": "clarify", "message": "That time isn't valid. Please give a time such as 10 AM or 2:30 PM."}
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    else:
        time_match = re.search(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", normalized)
        if not time_match:
            return {"kind": "clarify", "message": "What time should I use? For example: tomorrow at 10 AM."}
        hour, minute = int(time_match.group(1)), int(time_match.group(2))

    schedule_at = datetime(
        target_date.year, target_date.month, target_date.day,
        hour, minute, tzinfo=local_now.tzinfo,
    )
    if schedule_at <= local_now:
        return {"kind": "clarify", "message": "That time is in the past. Please choose a future date and time."}

    recurrence = "weekly" if re.search(r"\b(weekly|every week)\b", normalized) else (
        "daily" if re.search(r"\b(daily|every day)\b", normalized) else "once"
    )
    return {
        "kind": "schedule",
        "title": title,
        "action_id": action_id,
        "schedule_at": schedule_at.isoformat(timespec="minutes"),
        "recurrence": recurrence,
    }
