"""Create and reuse the configured AI provider."""
from functools import lru_cache
from nova.config import get_settings
from nova.core.ai.providers import EchoProvider, OpenAICompatibleProvider


@lru_cache(maxsize=1)
def get_provider():
    """Reuse one provider instance and its connection pool."""
    settings = get_settings()
    name = settings.ai_provider.strip().lower()
    if name == "echo":
        return EchoProvider()
    if name == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.ai_base_url, model=settings.ai_model,
            api_key=settings.ai_api_key, timeout_seconds=settings.ai_timeout_seconds,
        )
    raise ValueError("Unsupported NOVA_AI_PROVIDER. Use 'echo' or 'openai_compatible'.")


async def close_provider() -> None:
    provider = get_provider()
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
    get_provider.cache_clear()
