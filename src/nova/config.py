"""Application settings loaded from environment variables and .env."""

from functools import lru_cache

from pydantic import Field
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

    # Generation defaults tuned for responsive local chat. All are configurable.
    ai_max_tokens: int = Field(default=512, ge=64, le=8192)
    ai_context_messages: int = Field(default=8, ge=0, le=20)
    ai_top_p: float = Field(default=0.8, gt=0.0, le=1.0)
    ai_qwen_no_think: bool = True

    # SQLite database; the path is expanded and created automatically.
    memory_db_path: str = "~/.nova/nova_memory.sqlite3"

    # Optional local Vosk model directory for desktop push-to-talk input.
    vosk_model_path: str = ""

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
