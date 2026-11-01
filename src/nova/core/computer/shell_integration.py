"""Windows shell integration helpers for NOVA."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from nova.config import user_data_dir


class ShellIntegrationError(RuntimeError):
    pass


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    return f'"{sys.executable}" -m nova.desktop --background'


def startup_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _ = winreg.QueryValueEx(key, "NOVA")
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def set_startup_enabled(enabled: bool) -> bool:
    if os.name != "nt":
        raise ShellIntegrationError("Windows startup integration is available only on Windows.")
    import winreg
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "NOVA", 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, "NOVA")
                except FileNotFoundError:
                    pass
    except OSError as exc:
        raise ShellIntegrationError(f"Could not update the current-user startup setting: {exc}") from exc
    return startup_enabled()


def show_windows_toast(title: str, message: str) -> bool:
    if os.name != "nt":
        return False
    try:
        from winotify import Notification
        toast = Notification(app_id="NOVA", title=str(title)[:100], msg=str(message)[:400])
        toast.show()
        return True
    except ImportError as exc:
        raise ShellIntegrationError("Install NOVA's Windows extra to enable native notifications: pip install -e '.[windows]'") from exc
    except Exception as exc:
        raise ShellIntegrationError(f"Windows notification could not be displayed: {exc}") from exc


def notifications_enabled() -> bool:
    """Return the user's explicit NOVA toast-notification preference."""
    path = user_data_dir() / "preferences.json"
    try:
        preferences = json.loads(path.read_text(encoding="utf-8"))
        return preferences.get("notifications_enabled") is True
    except (OSError, ValueError, AttributeError):
        return False


def set_notifications_enabled(enabled: bool) -> bool:
    """Persist the user's local opt-in for NOVA-generated toast notifications."""
    directory = user_data_dir()
    path = directory / "preferences.json"
    temporary = directory / "preferences.json.tmp"
    try:
        try:
            preferences = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(preferences, dict):
                preferences = {}
        except (OSError, ValueError):
            preferences = {}
        preferences["notifications_enabled"] = bool(enabled)
        temporary.write_text(json.dumps(preferences, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise ShellIntegrationError(f"Could not save NOVA notification preferences: {exc}") from exc
    return notifications_enabled()



def wake_word_enabled() -> bool:
    """Return the user's explicit local wake-word microphone preference."""
    path = user_data_dir() / "preferences.json"
    try:
        preferences = json.loads(path.read_text(encoding="utf-8"))
        return preferences.get("wake_word_enabled") is True
    except (OSError, ValueError, AttributeError):
        return False


def set_wake_word_enabled(enabled: bool) -> bool:
    """Persist wake-word opt-in locally; disabled by default."""
    directory = user_data_dir()
    path = directory / "preferences.json"
    temporary = directory / "preferences.json.tmp"
    try:
        try:
            preferences = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(preferences, dict):
                preferences = {}
        except (OSError, ValueError):
            preferences = {}
        preferences["wake_word_enabled"] = bool(enabled)
        temporary.write_text(json.dumps(preferences, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise ShellIntegrationError(f"Could not save NOVA wake-word preference: {exc}") from exc
    return wake_word_enabled()
