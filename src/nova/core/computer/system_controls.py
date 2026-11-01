"""Narrow Windows system controls and native Windows Search handoff.

No arbitrary commands are accepted. Every mutating operation is typed and
requires approval at the API boundary.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any
from urllib.parse import quote


class WindowsControlError(ValueError):
    """A requested Windows control is unsupported or unavailable."""


def set_master_volume(percent: int, muted: bool | None = None) -> dict[str, Any]:
    if os.name != "nt":
        raise WindowsControlError("Audio controls are available only on Windows.")
    if not 0 <= int(percent) <= 100:
        raise WindowsControlError("Volume must be between 0 and 100.")
    try:
        from pycaw.pycaw import AudioUtilities
        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        endpoint.SetMasterVolumeLevelScalar(int(percent) / 100.0, None)
        if muted is not None:
            endpoint.SetMute(bool(muted), None)
        return {
            "volume_percent": int(round(endpoint.GetMasterVolumeLevelScalar() * 100)),
            "muted": bool(endpoint.GetMute()),
            "message": "System volume updated.",
        }
    except ImportError as exc:
        raise WindowsControlError("Install NOVA's Windows audio extra: pip install -e '.[windows]'") from exc
    except Exception as exc:
        raise WindowsControlError(f"Windows audio control failed: {exc}") from exc


def set_display_brightness(percent: int) -> dict[str, Any]:
    if os.name != "nt":
        raise WindowsControlError("Display brightness controls are available only on Windows.")
    if not 0 <= int(percent) <= 100:
        raise WindowsControlError("Brightness must be between 0 and 100.")
    script = (
        "$monitors = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods; "
        f"foreach ($monitor in $monitors) {{ $monitor.WmiSetBrightness(1, {int(percent)}) | Out-Null }}; "
        "if (-not $monitors) { exit 3 }"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WindowsControlError(f"Could not access Windows display brightness controls: {exc}") from exc
    if completed.returncode != 0:
        raise WindowsControlError("Windows did not expose a controllable WMI brightness monitor. External monitors may not support this interface.")
    return {"brightness_percent": int(percent), "message": "Display brightness update requested."}


def open_windows_search(query: str) -> dict[str, str]:
    if os.name != "nt":
        raise WindowsControlError("Windows Search integration is available only on Windows.")
    normalized = " ".join(str(query).split())
    if not normalized or len(normalized) > 200:
        raise WindowsControlError("Search text must contain 1 to 200 characters.")
    target = "search-ms:query=" + quote(normalized, safe="")
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise WindowsControlError("Windows Shell search is unavailable in this environment.")
    try:
        startfile(target)
    except OSError as exc:
        raise WindowsControlError(f"Windows Search could not be opened: {exc}") from exc
    return {"query": normalized, "message": f"Opened Windows Search for: {normalized}"}
