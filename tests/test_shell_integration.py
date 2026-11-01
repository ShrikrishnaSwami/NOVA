from __future__ import annotations

import pytest

from nova.core.computer import shell_integration


def test_windows_shell_features_are_disabled_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(shell_integration.os, "name", "posix")
    assert shell_integration.startup_enabled() is False
    with pytest.raises(shell_integration.ShellIntegrationError, match="only on Windows"):
        shell_integration.set_startup_enabled(True)
    assert shell_integration.show_windows_toast("NOVA", "Test") is False


def test_notification_preference_is_explicit_and_persistent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(shell_integration, "user_data_dir", lambda: tmp_path)
    assert shell_integration.notifications_enabled() is False
    assert shell_integration.set_notifications_enabled(True) is True
    assert shell_integration.notifications_enabled() is True
    assert shell_integration.set_notifications_enabled(False) is False
