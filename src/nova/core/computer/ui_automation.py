"""Permission-scoped Windows UI Automation for named controls only."""
from __future__ import annotations

import os
from typing import Any

_ALLOWED_TYPES = {"Button", "TabItem", "MenuItem", "Hyperlink", "CheckBox", "RadioButton"}


class UIAutomationError(ValueError):
    """Raised when a requested UI Automation target is unsafe or unavailable."""


def _window(handle: int):
    if os.name != "nt":
        raise UIAutomationError("Application UI Automation is available only on Windows.")
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=int(handle), timeout=3)
        window = app.window(handle=int(handle))
        if not window.is_visible():
            raise UIAutomationError("The selected window is no longer visible.")
        return window
    except ImportError as exc:
        raise UIAutomationError("Install NOVA's Windows automation extra: pip install -e '.[windows]'") from exc
    except UIAutomationError:
        raise
    except Exception as exc:
        raise UIAutomationError(f"Could not attach to the selected application window: {exc}") from exc


def list_interactive_controls(handle: int, limit: int = 100) -> list[dict[str, Any]]:
    window = _window(handle)
    results = []
    try:
        for control in window.descendants():
            try:
                info = control.element_info
                control_type = str(info.control_type or "")
                name = str(info.name or "").strip()
                if control_type not in _ALLOWED_TYPES or not name or not control.is_visible() or not control.is_enabled():
                    continue
                results.append({
                    "name": name[:200],
                    "control_type": control_type,
                    "automation_id": str(info.automation_id or "")[:100],
                    "handle": int(handle),
                })
                if len(results) >= max(1, min(int(limit), 200)):
                    break
            except Exception:
                continue
    except Exception as exc:
        raise UIAutomationError(f"Could not inspect application controls: {exc}") from exc
    return results


def click_named_control(handle: int, name: str, control_type: str) -> dict[str, str]:
    if control_type not in _ALLOWED_TYPES:
        raise UIAutomationError("Only buttons, tabs, menu items, hyperlinks, checkboxes, and radio buttons can be activated.")
    normalized = " ".join(str(name).split())
    if not normalized or len(normalized) > 200:
        raise UIAutomationError("A control's exact accessible name is required.")
    window = _window(handle)
    matches = []
    try:
        for control in window.descendants():
            try:
                info = control.element_info
                if (
                    str(info.control_type or "") == control_type
                    and " ".join(str(info.name or "").split()) == normalized
                    and control.is_visible()
                    and control.is_enabled()
                ):
                    matches.append(control)
            except Exception:
                continue
    except Exception as exc:
        raise UIAutomationError(f"Could not locate the requested control: {exc}") from exc
    if len(matches) != 1:
        raise UIAutomationError("The control name must identify exactly one enabled visible control. Refresh the control list and choose an unambiguous item.")
    try:
        matches[0].click_input()
    except Exception as exc:
        raise UIAutomationError(f"Windows could not activate that control: {exc}") from exc
    return {"name": normalized, "control_type": control_type, "message": f"Activated {normalized}."}
