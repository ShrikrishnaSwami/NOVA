"""Provider-independent AI interfaces and implementations."""

from nova.core.ai.factory import get_provider
from nova.core.ai.types import ChatMessage, ChatResult

__all__ = ["ChatMessage", "ChatResult", "get_provider"]
