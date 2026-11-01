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
def list_memories(
    status: str | None = Query(default=None, pattern="^(approved|pending)$"),
    category: str | None = Query(default=None, min_length=1, max_length=64),
) -> dict:
    return {"memories": _store().list_memories(status, category)}


@router.get("/memory/stats")
def memory_stats() -> dict:
    return _store().memory_stats()


@router.get("/memory/search")
def search_memories(q: str = Query(min_length=1, max_length=500), limit: int = Query(default=10, ge=1, le=50)) -> dict:
    return {"query": q, "memories": _store().retrieve(q, limit=limit)}


class MemoryPin(BaseModel):
    pinned: bool


class ConversationTitle(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class ConversationPin(BaseModel):
    pinned: bool


@router.patch("/memory/{memory_id}/pin")
def pin_memory(memory_id: str, request: MemoryPin) -> dict:
    if not _store().pin_memory(memory_id, request.pinned):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"id": memory_id, "pinned": request.pinned}


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


@router.get("/conversations/search")
def search_conversations(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return {"query": q, "conversations": _store().search_conversations(q, limit)}


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, request: ConversationTitle) -> dict:
    try:
        updated = _store().rename_conversation(conversation_id, request.title)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": conversation_id, "title": " ".join(request.title.split())[:100]}


@router.patch("/conversations/{conversation_id}/pin")
def pin_conversation(conversation_id: str, request: ConversationPin) -> dict:
    if not _store().pin_conversation(conversation_id, request.pinned):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": conversation_id, "pinned": request.pinned}


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
