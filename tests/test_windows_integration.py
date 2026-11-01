"""Tests for read-only OS introspection."""
from nova.core.computer import windows


def test_system_overview_has_portable_fields() -> None:
    result = windows.system_overview()
    assert result["system"]
    assert result["release"]
    assert result["python"]
    assert "capabilities" in result
    assert isinstance(result["capabilities"]["process_inventory"], bool)


def test_window_inventory_is_empty_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(windows.os, "name", "posix")
    assert windows.list_windows() == []
    assert windows.foreground_window() is None


def test_process_inventory_has_bounded_limit() -> None:
    try:
        result = windows.list_processes(1)
    except RuntimeError as exc:
        assert "windows extra" in str(exc)
    else:
        assert len(result) <= 1
        for process in result:
            assert set(process) == {"pid", "name", "status", "memory_bytes"}
