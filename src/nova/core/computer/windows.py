"""Read-only operating-system introspection for NOVA.

This module reports information exposed to the current user session. It never
elevates privileges, reads process command lines, or changes OS state.
"""
from __future__ import annotations

import os
import platform
import getpass
from typing import Any


def system_overview() -> dict[str, Any]:
    """Return a compact snapshot of the current OS and Python process environment."""
    result: dict[str, Any] = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "user": getpass.getuser(),
        "home": os.path.expanduser("~"),
        "working_directory": os.getcwd(),
        "is_windows": os.name == "nt",
        "capabilities": {
            "process_inventory": False,
            "window_inventory": False,
            "foreground_window": False,
        },
    }
    if os.name == "nt":
        result["capabilities"].update({
            "window_inventory": True,
            "foreground_window": True,
        })
    try:
        import psutil
        result["cpu_count_logical"] = psutil.cpu_count(logical=True)
        result["cpu_count_physical"] = psutil.cpu_count(logical=False)
        result["memory_total_bytes"] = psutil.virtual_memory().total
        result["memory_available_bytes"] = psutil.virtual_memory().available
        result["cpu_percent"] = psutil.cpu_percent(interval=0.0)
        result["capabilities"]["process_inventory"] = True
    except ImportError:
        result["system_metrics_note"] = "Install NOVA's declared dependencies for process and resource metrics."
    except (OSError, RuntimeError):
        result["system_metrics_note"] = "Some system metrics are unavailable in this session."
    return result


def list_processes(limit: int = 100) -> list[dict[str, Any]]:
    """List visible process metadata without command lines, environment, or user secrets."""
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Process inventory requires NOVA's declared psutil dependency. Reinstall NOVA with: pip install -e .") from exc
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "status", "memory_info"]):
        try:
            info = process.info
            memory = info.get("memory_info")
            processes.append({
                "pid": int(info["pid"]),
                "name": str(info.get("name") or "Unknown"),
                "status": str(info.get("status") or "unknown"),
                "memory_bytes": int(memory.rss) if memory else 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            continue
        if len(processes) >= max(1, min(limit, 300)):
            break
    return sorted(processes, key=lambda item: item["name"].casefold())


def list_windows(limit: int = 100) -> list[dict[str, Any]]:
    """Enumerate visible top-level Windows windows with title and owning PID."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    results: list[dict[str, Any]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(min(length + 1, 2048))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        title = buffer.value.strip()
        if not title:
            return True
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        results.append({
            "handle": int(hwnd),
            "title": title[:500],
            "pid": int(process_id.value),
        })
        return len(results) < max(1, min(limit, 300))

    user32.EnumWindows(callback_type(visit), 0)
    return results


def foreground_window() -> dict[str, Any] | None:
    """Return the title and PID of the currently foreground window."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(min(max(length + 1, 1), 2048))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return {"handle": int(hwnd), "title": buffer.value[:500], "pid": int(process_id.value)}
