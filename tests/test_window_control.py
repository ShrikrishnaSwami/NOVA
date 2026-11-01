from __future__ import annotations

import pytest

from nova.core.computer import window_control


def test_window_controls_are_windows_only(monkeypatch) -> None:
    monkeypatch.setattr(window_control.os, "name", "posix")
    with pytest.raises(window_control.WindowControlError, match="only on Windows"):
        window_control.control_window(123, "focus")


def test_window_control_rejects_unknown_action_before_os_access(monkeypatch) -> None:
    monkeypatch.setattr(window_control.os, "name", "nt")
    with pytest.raises(window_control.WindowControlError, match="Supported actions"):
        window_control.control_window(123, "shutdown")



def test_close_is_a_supported_window_action(monkeypatch) -> None:
    monkeypatch.setattr(window_control.os, "name", "posix")
    with pytest.raises(window_control.WindowControlError, match="only on Windows"):
        window_control.control_window(123, "close")
