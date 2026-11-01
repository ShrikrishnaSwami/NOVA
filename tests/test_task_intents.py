from datetime import datetime
from zoneinfo import ZoneInfo

from nova.core.tasks.intents import plan_task_intent


def test_open_and_list_task_intents():
    assert plan_task_intent("open scheduled tasks") == {"kind": "open"}
    assert plan_task_intent("what tasks do I have") == {"kind": "list"}


def test_parse_storage_report_tomorrow_at_ten_am():
    now = datetime(2026, 11, 1, 9, 0, tzinfo=ZoneInfo("America/Toronto"))
    plan = plan_task_intent("schedule a storage report tomorrow at 10 AM", now)
    assert plan["kind"] == "schedule"
    assert plan["action_id"] == "storage.report"
    assert plan["schedule_at"] == "2026-11-02T10:00-05:00"
    assert plan["recurrence"] == "once"


def test_parse_recurring_system_check():
    now = datetime(2026, 11, 1, 9, 0, tzinfo=ZoneInfo("America/Toronto"))
    plan = plan_task_intent("schedule a daily system check tomorrow at 8:30 PM", now)
    assert plan["action_id"] == "system.snapshot"
    assert plan["recurrence"] == "daily"
    assert plan["schedule_at"] == "2026-11-02T20:30-05:00"


def test_ask_for_missing_date_or_time():
    now = datetime(2026, 11, 1, 9, 0, tzinfo=ZoneInfo("America/Toronto"))
    assert plan_task_intent("schedule a storage report", now)["kind"] == "clarify"
    assert plan_task_intent("schedule a storage report tomorrow", now)["kind"] == "clarify"


def test_reject_past_time():
    now = datetime(2026, 11, 1, 9, 0, tzinfo=ZoneInfo("America/Toronto"))
    assert plan_task_intent("schedule a system check today at 8 AM", now)["kind"] == "clarify"


def test_pause_cancel_task():
    assert plan_task_intent("pause task daily system snapshot") == {
        "kind": "pause", "target": "daily system snapshot"
    }
    assert plan_task_intent("cancel storage report") == {
        "kind": "cancel", "target": "storage report"
    }
