"""Memory and conversation management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from nova.config import get_settings
from nova.core.memory import MemoryStore

router = APIRouter(tags=["memory"])


def _store() -> MemoryStore:
    return MemoryStore(get_settings().memory_db_path)


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=8, max_length=1000)


@router.get("/memory")
def list_memories(status: str | None = Query(default=None, pattern="^(approved|pending)$")) -> dict:
    return {"memories": _store().list_memories(status)}


@router.post("/memory/{memory_id}/approve")
def approve_memory(memory_id: str) -> dict:
    if not _store().approve_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"id": memory_id, "status": "approved"}


@router.patch("/memory/{memory_id}")
def update_memory(memory_id: str, request: MemoryUpdate) -> dict:
    try:
        updated = _store().update_memory(memory_id, request.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"id": memory_id, "content": request.content, "updated": True}


@router.delete("/memory/{memory_id}")
def delete_memory(memory_id: str) -> dict:
    if not _store().delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"id": memory_id, "deleted": True}


@router.get("/conversations")
def list_conversations(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"conversations": _store().list_conversations(limit)}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    messages = _store().get_messages(conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": conversation_id, "messages": messages}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    if not _store().delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": conversation_id, "deleted": True}
