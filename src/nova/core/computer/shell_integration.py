"""Windows shell integration helpers for NOVA."""
from __future__ import annotations

import os
import sys
from pathlib import Path


class ShellIntegrationError(RuntimeError):
    pass


def _startup_command() -> str:
    return f'"{sys.executable}" -m nova.desktop'


def startup_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _ = winreg.QueryValueEx(key, "NOVA")
            return bool(value)
    except FileNotFoundError:
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
