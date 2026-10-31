"""Shared AI types."""

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatResult:
    content: str
    provider: str
    model: str


class AIProvider(Protocol):
    """Contract every NOVA model provider must implement."""

    name: str
    model: str

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatResult:
        """Generate one assistant response from a conversation."""
