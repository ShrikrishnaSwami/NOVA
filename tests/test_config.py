from __future__ import annotations

import os
from pathlib import Path

from nova.config import Settings, environment_file, user_memory_path


def test_settings_reads_selected_env_file(tmp_path: Path, monkeypatch) -> None:
    # Real process environment variables intentionally outrank dotenv values.
    monkeypatch.delenv("NOVA_AI_MODEL", raising=False)
    monkeypatch.delenv("NOVA_PORT", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("NOVA_AI_MODEL=profile-qwen\nNOVA_PORT=8123\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.ai_model == "profile-qwen"
    assert settings.port == 8123


def test_environment_file_falls_back_to_project_env(tmp_path: Path, monkeypatch) -> None:
    project_env = tmp_path / ".env"
    project_env.write_text("NOVA_AI_MODEL=project-model\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("nova.config.user_data_dir", lambda: tmp_path / "profile")
    assert environment_file() == project_env


def test_memory_path_is_outside_project_directory(tmp_path: Path, monkeypatch) -> None:
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        expected = tmp_path / "NOVA" / "nova_memory.sqlite3"
    else:
        monkeypatch.setenv("HOME", str(tmp_path))
        expected = tmp_path / ".nova" / "nova_memory.sqlite3"
    assert user_memory_path() == str(expected)
