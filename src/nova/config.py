"""Application settings and per-user configuration paths."""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def user_data_dir() -> Path:
    """Return NOVA's per-user writable data directory."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        path = base / "NOVA"
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nova"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_memory_path() -> str:
    """Place persistent memory outside the installation directory."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return str(base / "NOVA" / "nova_memory.sqlite3")
    return str(Path.home() / ".nova" / "nova_memory.sqlite3")


def environment_file() -> Path:
    """Prefer the per-user settings file; retain project-local .env for development."""
    profile_env = user_data_dir() / ".env"
    return profile_env if profile_env.exists() else Path.cwd() / ".env"


class Settings(BaseSettings):
    app_name: str = "NOVA"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    distributed_enabled: bool = True
    nats_url: str = "nats://127.0.0.1:4222"
    node_id: str = "nova-windows-host"

    ai_provider: str = "echo"
    ai_model: str = "local-model"
    ai_base_url: str = "http://127.0.0.1:1234/v1"
    ai_api_key: str = ""
    ai_timeout_seconds: float = 60.0

    ai_max_tokens: int = Field(default=512, ge=64, le=8192)
    ai_context_messages: int = Field(default=8, ge=0, le=20)
    ai_top_p: float = Field(default=0.8, gt=0.0, le=1.0)
    ai_qwen_no_think: bool = True

    memory_db_path: str = Field(default_factory=user_memory_path)
    vosk_model_path: str = ""
    computer_allowed_roots: str = ""

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="NOVA_",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached settings instance for the application."""
    return Settings(_env_file=environment_file())


def get_vosk_model_path() -> str:
    """Resolve an explicitly configured or bundled local Vosk model directory."""
    configured = get_settings().vosk_model_path.strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = user_data_dir() / path
        return str(path)

    model_name = "vosk-model-small-en-us-0.15"
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parents[2]
    candidate = base / model_name
    if candidate.is_dir():
        return str(candidate)
    return str(base / "models" / model_name)
