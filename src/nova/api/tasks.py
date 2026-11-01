"""API for creating, approving, scheduling, and reviewing NOVA tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from nova.config import get_settings
from nova.core.tasks import TaskScheduler, TaskStore

router = APIRouter(prefix="/tasks", tags=["task automation"])
_ALLOWED_ACTIONS = {"system.snapshot", "storage.report"}


def _store() -> TaskStore:
    return TaskStore(get_settings().memory_db_path)


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    action_id: Literal["system.snapshot", "storage.report"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    schedule_at: datetime
    recurrence: Literal["once", "daily", "weekly"] = "once"

    @field_validator("schedule_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("schedule_at must include a timezone offset.")
        if value <= datetime.now(timezone.utc):
            raise ValueError("schedule_at must be in the future.")
        return value


@router.get("/capabilities")
def task_capabilities() -> dict[str, Any]:
    return {"actions": TaskScheduler.capabilities(), "recurrences": ["once", "daily", "weekly"],
            "approval_required": True, "execution_scope": "registered read-only tasks only"}


@router.post("")
def create_task(request: CreateTaskRequest) -> dict[str, Any]:
    if request.action_id not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail="That task action is not available.")
    try:
        task = _store().create(request.title, request.action_id, request.parameters, request.schedule_at, request.recurrence)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"task": task, "message": "Task created and awaiting your approval. It will not run until approved."}


@router.get("")
def list_tasks(status: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=300)) -> dict[str, Any]:
    if status and status not in {"pending_approval", "scheduled", "paused", "completed", "cancelled", "failed"}:
        raise HTTPException(status_code=422, detail="Unsupported task status.")
    return {"tasks": _store().list(status, limit)}


@router.post("/{task_id}/approve")
def approve_task(task_id: str) -> dict[str, Any]:
    store = _store()
    if not store.approve(task_id):
        raise HTTPException(status_code=409, detail="Task does not exist or is not awaiting approval.")
    return {"task": store.get(task_id), "message": "Task approved. Only its registered read-only action will run on schedule."}


@router.post("/{task_id}/pause")
def pause_task(task_id: str) -> dict[str, Any]:
    store = _store()
    if not store.set_status(task_id, "paused"):
        raise HTTPException(status_code=409, detail="Task cannot be paused in its current state.")
    return {"task": store.get(task_id)}


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    store = _store()
    if not store.set_status(task_id, "cancelled"):
        raise HTTPException(status_code=409, detail="Task cannot be cancelled in its current state.")
    return {"task": store.get(task_id)}


@router.get("/{task_id}/history")
def task_history(task_id: str, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    store = _store()
    if not store.get(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"runs": store.history(task_id, limit)}
