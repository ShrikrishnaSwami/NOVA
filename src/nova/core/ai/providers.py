"""AI provider adapters with reusable connections and streaming."""
from collections.abc import AsyncIterator, Sequence
import json
import httpx
from nova.core.ai.types import ChatMessage, ChatResult


class EchoProvider:
    name = "echo"
    model = "setup-mode"

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatResult:
        latest = next((m.content for m in reversed(messages) if m.role == "user"), "")
        content = ("I received your message. NOVA is currently in setup mode. Connect a local or cloud model in your .env file to enable full AI capabilities." if latest else "I'm NOVA. Send me a message to get started.")
        return ChatResult(content=content, provider=self.name, model=self.model)

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        yield (await self.complete(messages)).content


class OpenAICompatibleProvider:
    """OpenAI-compatible adapter with a persistent HTTP connection pool."""
    name = "openai_compatible"

    def __init__(self, *, base_url: str, model: str, api_key: str = "", timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=90.0),
        )

    def _parts(self, messages: Sequence[ChatMessage]) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": [{"role": m.role, "content": m.content} for m in messages], "temperature": 0.7}
        return headers, payload

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatResult:
        headers, payload = self._parts(messages)
        response = await self._client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The configured model returned an empty response.")
        return ChatResult(content=content.strip(), provider=self.name, model=self.model)

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        headers, payload = self._parts(messages)
        payload["stream"] = True
        async with self._client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
            response.raise_for_status()
            # Some compatible servers ignore stream=true and return one JSON response.
            if "text/event-stream" not in response.headers.get("content-type", "").lower():
                data = await response.aread()
                body = json.loads(data)
                content = body["choices"][0]["message"]["content"]
                if isinstance(content, str) and content:
                    yield content
                return
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                token = delta.get("content")
                if isinstance(token, str) and token:
                    yield token

    async def aclose(self) -> None:
        await self._client.aclose()
