"""Application settings loaded from environment variables and .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NOVA"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # "echo" keeps a fresh installation testable without credentials.
    # "openai_compatible" works with local runtimes and compatible cloud APIs.
    ai_provider: str = "echo"
    ai_model: str = "local-model"
    ai_base_url: str = "http://127.0.0.1:1234/v1"
    ai_api_key: str = ""
    ai_timeout_seconds: float = 60.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="NOVA_",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached settings instance for the application."""
    return Settings()
