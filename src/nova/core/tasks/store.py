"""SQLite persistence for NOVA's scheduled tasks and execution history."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Scheduled times must include a timezone.")
    return value.astimezone(timezone.utc).isoformat()


class TaskStore:
    """Small SQLite task repository; each operation owns its connection."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        return db

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    schedule_at TEXT NOT NULL,
                    recurrence TEXT NOT NULL CHECK(recurrence IN ('once','daily','weekly')),
                    status TEXT NOT NULL CHECK(status IN ('pending_approval','scheduled','paused','completed','cancelled','failed')),
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_result TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_due
                    ON scheduled_tasks(status, schedule_at);
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    result TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_task_runs_task
                    ON task_runs(task_id, started_at DESC);
            """)

    def create(self, title: str, action_id: str, parameters: dict[str, Any], schedule_at: datetime, recurrence: str) -> dict[str, Any]:
        if recurrence not in {"once", "daily", "weekly"}:
            raise ValueError("Recurrence must be once, daily, or weekly.")
        now = _iso(_utcnow())
        task_id = str(uuid4())
        with self._connect() as db:
            db.execute("""INSERT INTO scheduled_tasks
                (id,title,action_id,parameters,schedule_at,recurrence,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'pending_approval',?,?)""",
                (task_id, title.strip()[:120], action_id, json.dumps(parameters), _iso(schedule_at), recurrence, now, now))
        return self.get(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)).fetchone()
        return self._decode(row) if row else None

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["parameters"] = json.loads(item["parameters"])
        if item.get("last_result"):
            item["last_result"] = json.loads(item["last_result"])
        return item

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            if status:
                rows = db.execute("SELECT * FROM scheduled_tasks WHERE status=? ORDER BY schedule_at LIMIT ?", (status, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode(row) for row in rows]

    def approve(self, task_id: str) -> bool:
        now = _iso(_utcnow())
        with self._connect() as db:
            cur = db.execute("""UPDATE scheduled_tasks SET status='scheduled',approved_at=?,updated_at=?
                WHERE id=? AND status='pending_approval'""", (now, now, task_id))
        return cur.rowcount == 1

    def set_status(self, task_id: str, status: str) -> bool:
        if status not in {"paused", "cancelled"}:
            raise ValueError("Unsupported task status.")
        now = _iso(_utcnow())
        with self._connect() as db:
            cur = db.execute("""UPDATE scheduled_tasks SET status=?,updated_at=?
                WHERE id=? AND status IN ('scheduled','paused','pending_approval')""", (status, now, task_id))
        return cur.rowcount == 1

    def due(self, now: datetime | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM scheduled_tasks WHERE status='scheduled' AND schedule_at<=?
                ORDER BY schedule_at LIMIT ?""", (_iso(now or _utcnow()), limit)).fetchall()
        return [self._decode(row) for row in rows]

    def record_run(self, task: dict[str, Any], outcome: str, result: dict[str, Any], finished: datetime | None = None) -> None:
        started = _utcnow()
        finished = finished or _utcnow()
        run_id = str(uuid4())
        next_status = "completed" if task["recurrence"] == "once" else "scheduled"
        next_schedule = task["schedule_at"]
        if task["recurrence"] in {"daily", "weekly"}:
            from datetime import timedelta
            next_time = datetime.fromisoformat(task["schedule_at"])
            increment = timedelta(days=1 if task["recurrence"] == "daily" else 7)
            while next_time <= finished:
                next_time += increment
            next_schedule = _iso(next_time)
        if outcome != "success":
            next_status = "failed"
        encoded = json.dumps(result, default=str)
        with self._connect() as db:
            db.execute("INSERT INTO task_runs(id,task_id,started_at,finished_at,outcome,result) VALUES(?,?,?,?,?,?)",
                       (run_id, task["id"], _iso(started), _iso(finished), outcome, encoded))
            db.execute("""UPDATE scheduled_tasks SET status=?,schedule_at=?,last_run_at=?,last_result=?,updated_at=? WHERE id=?""",
                       (next_status, next_schedule, _iso(finished), encoded, _iso(finished), task["id"]))

    def history(self, task_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM task_runs WHERE task_id=? ORDER BY started_at DESC LIMIT ?", (task_id, limit)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item["result"])
            result.append(item)
        return result
