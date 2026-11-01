"""Explicitly approved controls for visible Windows application windows.

Only operates on a currently existing, visible top-level window. It does not
send keystrokes, inspect window contents, or close applications.
"""
from __future__ import annotations

import os
from typing import Any


class WindowControlError(ValueError):
    """Raised when a requested window action is unavailable or invalid."""


def control_window(handle: int, action: str) -> dict[str, Any]:
    if os.name != "nt":
        raise WindowControlError("Window controls are available only on Windows.")
    if action not in {"focus", "minimize", "restore", "maximize"}:
        raise WindowControlError("Supported actions are focus, minimize, restore, and maximize.")

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = wintypes.HWND(int(handle))
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        raise WindowControlError("That window no longer exists or is not visible.")

    title_length = user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(min(max(title_length + 1, 1), 2048))
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    title = title_buffer.value[:500]
    if action in {"focus", "restore"}:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if not user32.SetForegroundWindow(hwnd):
            raise WindowControlError("Windows did not allow NOVA to bring that window to the foreground.")
    elif action == "minimize":
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    elif action == "maximize":
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE

    return {"handle": int(handle), "title": title, "action": action,
            "message": f"{action.capitalize()} requested for {title or 'selected window'}."}
