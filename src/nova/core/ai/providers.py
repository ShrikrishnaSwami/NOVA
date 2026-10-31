"""Built-in AI provider adapters."""

from collections.abc import Sequence

import httpx

from nova.core.ai.types import ChatMessage, ChatResult


class EchoProvider:
    """Safe setup provider used before a model has been configured."""

    name = "echo"
    model = "setup-mode"

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatResult:
        latest = next(
            (item.content for item in reversed(messages) if item.role == "user"),
            "",
        )
        return ChatResult(
            content=(
                "I received your message. My conversation API is working, but "
                "I'm currently in setup mode. Connect a local or cloud model in "
                "your .env file to give me full AI capabilities."
                if latest
                else "I'm NOVA. Send me a message to get started."
            ),
            provider=self.name,
            model=self.model,
        )


class OpenAICompatibleProvider:
    """Adapter for local model servers and cloud APIs using chat-completions format.

    Examples include LM Studio, llama.cpp server, and compatible hosted APIs.
    The model runtime stays outside NOVA, behind this stable adapter contract.
    """

    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The configured model returned an empty response.")

        return ChatResult(
            content=content.strip(),
            provider=self.name,
            model=self.model,
        )
