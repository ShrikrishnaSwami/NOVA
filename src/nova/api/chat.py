"""Conversation endpoints, including server-sent event streaming."""
import json
import time
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from nova.config import get_settings
from nova.core.ai import ChatMessage, get_provider

router = APIRouter(tags=["conversation"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str


def _messages(request: ChatRequest) -> list[ChatMessage]:
    messages = [ChatMessage(role=m.role, content=m.content) for m in request.history]
    messages.append(ChatMessage(role="user", content=request.message))
    return messages


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await get_provider().complete(_messages(request))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="NOVA could not get a response from the configured AI provider.") from exc
    return ChatResponse(reply=result.content, provider=result.provider, model=result.model)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Emit text tokens immediately, then TTFT and total-generation timing."""
    provider = get_provider()
    started = time.perf_counter()

    async def events():
        first_token = None
        try:
            async for token in provider.stream(_messages(request)):
                if first_token is None:
                    first_token = time.perf_counter()
                yield "data: " + json.dumps({"type": "token", "content": token}) + "\n\n"
            ended = time.perf_counter()
            yield "data: " + json.dumps({
                "type": "done", "provider": provider.name, "model": provider.model,
                "ttft_ms": round(((first_token or ended) - started) * 1000),
                "total_ms": round((ended - started) * 1000),
            }) + "\n\n"
        except Exception:
            yield "data: " + json.dumps({"type": "error", "message": "NOVA could not get a response from the configured AI provider."}) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/system/ai", tags=["system"])
async def ai_status() -> dict[str, str | bool]:
    """Report provider configuration without exposing credentials."""
    settings = get_settings()
    provider = settings.ai_provider.strip().lower()
    configured = provider == "echo" or (
        provider == "openai_compatible"
        and bool(settings.ai_base_url.strip())
        and bool(settings.ai_model.strip())
    )
    return {
        "provider": provider,
        "model": settings.ai_model if provider == "openai_compatible" else "setup-mode",
        "configured": configured,
        "mode": "setup" if provider == "echo" else "model-backed",
    }
