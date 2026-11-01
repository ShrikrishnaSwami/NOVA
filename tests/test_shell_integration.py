from __future__ import annotations

import pytest

from nova.core.computer import shell_integration


def test_windows_shell_features_are_disabled_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(shell_integration.os, "name", "posix")
    assert shell_integration.startup_enabled() is False
    with pytest.raises(shell_integration.ShellIntegrationError, match="only on Windows"):
        shell_integration.set_startup_enabled(True)
    assert shell_integration.show_windows_toast("NOVA", "Test") is False
