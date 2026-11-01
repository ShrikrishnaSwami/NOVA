from __future__ import annotations

import pytest

from nova.core.computer import ui_automation


def test_ui_automation_is_windows_only(monkeypatch) -> None:
    monkeypatch.setattr(ui_automation.os, "name", "posix")
    with pytest.raises(ui_automation.UIAutomationError, match="only on Windows"):
        ui_automation.list_interactive_controls(123)


def test_ui_automation_rejects_unsafe_control_types_before_access(monkeypatch) -> None:
    monkeypatch.setattr(ui_automation.os, "name", "nt")
    with pytest.raises(ui_automation.UIAutomationError, match="Only buttons"):
        ui_automation.click_named_control(123, "Save", "Edit")
