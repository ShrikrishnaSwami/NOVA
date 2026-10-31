"""Conversation endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException
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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to NOVA and receive an assistant response."""
    settings = get_settings()
    try:
        provider = get_provider()
        messages = [
            ChatMessage(role=item.role, content=item.content)
            for item in request.history
        ]
        messages.append(ChatMessage(role="user", content=request.message))
        result = await provider.complete(messages)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid returning upstream response bodies, credentials, or internals.
        raise HTTPException(
            status_code=502,
            detail="NOVA could not get a response from the configured AI provider.",
        ) from exc

    return ChatResponse(
        reply=result.content,
        provider=result.provider,
        model=result.model,
    )


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
