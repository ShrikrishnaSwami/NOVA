from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nova.core.tasks import TaskScheduler, TaskStore


def _task(store: TaskStore, recurrence: str = "once") -> dict:
    return store.create("Test task", "test.read", {}, datetime.now(timezone.utc) + timedelta(minutes=1), recurrence)


def test_new_task_requires_approval_and_is_not_due(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _task(store)
    assert task["status"] == "pending_approval"
    assert store.due(now=datetime.now(timezone.utc) + timedelta(days=1)) == []


def test_approved_task_executes_only_registered_handler(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _task(store)
    assert store.approve(task["id"])
    calls = []
    scheduler = TaskScheduler(store, handlers={"test.read": lambda params: calls.append(params) or {"ok": True}})
    count = scheduler.run_due(now=datetime.now(timezone.utc) + timedelta(days=1))
    assert count == 1
    assert calls == [{}]
    assert store.get(task["id"])["status"] == "completed"
    assert store.history(task["id"])[0]["outcome"] == "success"


def test_recurring_task_is_rescheduled_after_success(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _task(store, "daily")
    store.approve(task["id"])
    scheduler = TaskScheduler(store, handlers={"test.read": lambda _: {"ok": True}})
    scheduler.run_due(now=datetime.now(timezone.utc) + timedelta(days=1))
    updated = store.get(task["id"])
    assert updated["status"] == "scheduled"
    assert datetime.fromisoformat(updated["schedule_at"]) > datetime.now(timezone.utc)


def test_scheduler_emits_result_events_for_approved_tasks(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _task(store)
    store.approve(task["id"])
    events = []
    scheduler = TaskScheduler(
        store,
        handlers={"test.read": lambda _: {"status": "ready"}},
        on_event=events.append,
    )
    scheduler.run_due(now=datetime.now(timezone.utc) + timedelta(days=1))
    assert events[0]["type"] == "task.completed"
    assert events[0]["status"] == "success"
    assert events[0]["result"] == {"status": "ready"}


def test_paused_task_does_not_execute(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _task(store)
    store.approve(task["id"])
    assert store.set_status(task["id"], "paused")
    scheduler = TaskScheduler(store, handlers={"test.read": lambda _: {"ok": True}})
    assert scheduler.run_due(now=datetime.now(timezone.utc) + timedelta(days=1)) == 0
