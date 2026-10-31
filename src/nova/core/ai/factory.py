"""Create the configured AI provider."""

from nova.config import get_settings
from nova.core.ai.providers import EchoProvider, OpenAICompatibleProvider


def get_provider():
    settings = get_settings()
    provider_name = settings.ai_provider.strip().lower()

    if provider_name == "echo":
        return EchoProvider()

    if provider_name == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            api_key=settings.ai_api_key,
            timeout_seconds=settings.ai_timeout_seconds,
        )

    raise ValueError(
        "Unsupported NOVA_AI_PROVIDER. Use 'echo' or 'openai_compatible'."
    )
