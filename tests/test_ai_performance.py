from types import SimpleNamespace

from nova.api import chat as chat_api
from nova.config import Settings
from nova.core.ai.providers import OpenAICompatibleProvider
from nova.core.ai.types import ChatMessage


def test_qwen3_requests_use_non_thinking_mode_and_bounded_output() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1235/v1",
        model="qwen3-1.7b",
        max_tokens=384,
        top_p=0.8,
        qwen_no_think=True,
    )

    _headers, payload = provider._parts(
        [ChatMessage(role="user", content="Explain briefly.")]
    )

    assert payload["max_tokens"] == 384
    assert payload["top_p"] == 0.8
    assert payload["messages"][-1]["content"].endswith("/no_think")


def test_qwen3_explicit_think_request_is_preserved() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1235/v1",
        model="qwen3-1.7b",
        qwen_no_think=True,
    )

    _headers, payload = provider._parts(
        [ChatMessage(role="user", content="Solve this carefully. /think")]
    )

    assert payload["messages"][-1]["content"] == "Solve this carefully. /think"


def test_non_qwen_models_do_not_receive_qwen_prompt_switch() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1235/v1",
        model="some-other-model",
        qwen_no_think=True,
    )

    _headers, payload = provider._parts(
        [ChatMessage(role="user", content="Hello.")]
    )

    assert payload["messages"][-1]["content"] == "Hello."


def test_chat_context_uses_only_configured_recent_history(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_api,
        "get_settings",
        lambda: SimpleNamespace(ai_context_messages=2),
    )

    class EmptyMemory:
        def retrieve(self, _query: str, limit: int = 4) -> list:
            return []

    monkeypatch.setattr(chat_api, "_store", lambda: EmptyMemory())
    request = chat_api.ChatRequest(
        message="Current question",
        history=[
            {"role": "user", "content": "Old question"},
            {"role": "assistant", "content": "Old answer"},
            {"role": "user", "content": "Recent question"},
            {"role": "assistant", "content": "Recent answer"},
        ],
    )

    messages = chat_api._messages(request)

    # System instructions are deliberately retained, but do not count toward
    # the configured conversational-history window.
    assert any(message.role == "system" for message in messages)
    conversation_messages = [
        message for message in messages if message.role != "system"
    ]
    assert [message.content for message in conversation_messages] == [
        "Recent question",
        "Recent answer",
        "Current question",
    ]


def test_generation_settings_have_responsive_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_max_tokens == 512
    assert settings.ai_context_messages == 8
    assert settings.ai_qwen_no_think is True
    assert settings.ai_top_p == 0.8
