from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from nova.api import tasks as tasks_api
from nova.main import app


class TaskSettings:
    def __init__(self, database_path: str) -> None:
        self.memory_db_path = database_path


def test_task_api_requires_approval_and_supports_pause_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_api, "get_settings", lambda: TaskSettings(str(tmp_path / "tasks.sqlite3")))
    client = TestClient(app)
    capabilities = client.get("/tasks/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["approval_required"] is True

    payload = {
        "title": "Daily system snapshot",
        "action_id": "system.snapshot",
        "schedule_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "recurrence": "daily",
    }
    created = client.post("/tasks", json=payload)
    assert created.status_code == 200
    task_id = created.json()["task"]["id"]
    assert created.json()["task"]["status"] == "pending_approval"

    approved = client.post(f"/tasks/{task_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["task"]["status"] == "scheduled"

    paused = client.post(f"/tasks/{task_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["task"]["status"] == "paused"

    cancelled = client.post(f"/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["task"]["status"] == "cancelled"


def test_task_api_rejects_naive_or_past_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_api, "get_settings", lambda: TaskSettings(str(tmp_path / "tasks.sqlite3")))
    client = TestClient(app)
    base = {"title": "Storage report", "action_id": "storage.report", "recurrence": "once"}
    assert client.post("/tasks", json={**base, "schedule_at": "2030-01-01T10:00:00"}).status_code == 422
    assert client.post("/tasks", json={**base, "schedule_at": "2000-01-01T10:00:00+00:00"}).status_code == 422
