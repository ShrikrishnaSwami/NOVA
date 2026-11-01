from __future__ import annotations

import pytest

from nova.core.computer import system_controls


def test_system_controls_are_windows_only(monkeypatch) -> None:
    monkeypatch.setattr(system_controls.os, "name", "posix")
    with pytest.raises(system_controls.WindowsControlError, match="only on Windows"):
        system_controls.set_master_volume(30)
    with pytest.raises(system_controls.WindowsControlError, match="only on Windows"):
        system_controls.set_display_brightness(50)
    with pytest.raises(system_controls.WindowsControlError, match="only on Windows"):
        system_controls.open_windows_search("report")


@pytest.mark.parametrize("percent", [-1, 101])
def test_system_controls_reject_out_of_range_values_before_access(monkeypatch, percent) -> None:
    monkeypatch.setattr(system_controls.os, "name", "nt")
    with pytest.raises(system_controls.WindowsControlError, match="between 0 and 100"):
        system_controls.set_master_volume(percent)
    with pytest.raises(system_controls.WindowsControlError, match="between 0 and 100"):
        system_controls.set_display_brightness(percent)


def test_windows_search_rejects_empty_and_oversized_query(monkeypatch) -> None:
    monkeypatch.setattr(system_controls.os, "name", "nt")
    with pytest.raises(system_controls.WindowsControlError):
        system_controls.open_windows_search("  ")
    with pytest.raises(system_controls.WindowsControlError):
        system_controls.open_windows_search("x" * 201)
