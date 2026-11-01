import os
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from nova.api import computer as computer_api
from nova.main import app


class ComputerTestSettings:
    def __init__(self, database_path: str, roots: str) -> None:
        self.memory_db_path = database_path
        self.computer_allowed_roots = roots


def test_computer_tools_require_explicit_approval(tmp_path, monkeypatch) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    (root / "notes.txt").write_text("NOVA local file test", encoding="utf-8")
    monkeypatch.setattr(
        computer_api,
        "get_settings",
        lambda: ComputerTestSettings(str(tmp_path / "nova.sqlite3"), str(root)),
    )
    client = TestClient(app)

    denied = client.post(
        "/computer/actions",
        json={"action": "read_text_file", "parameters": {"path": str(root / "notes.txt")}},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/computer/actions",
        json={
            "action": "read_text_file",
            "parameters": {"path": str(root / "notes.txt")},
            "approved": True,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["result"]["content"] == "NOVA local file test"

    audit = client.get("/computer/audit")
    assert audit.status_code == 200
    assert len(audit.json()["entries"]) == 1
    assert audit.json()["entries"][0]["action"] == "read_text_file"


def test_computer_tools_reject_paths_outside_approved_roots(tmp_path, monkeypatch) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    secret = outside_root / "secret.txt"
    secret.write_text("not for NOVA", encoding="utf-8")
    monkeypatch.setattr(
        computer_api,
        "get_settings",
        lambda: ComputerTestSettings(str(tmp_path / "nova.sqlite3"), str(allowed_root)),
    )
    client = TestClient(app)

    response = client.post(
        "/computer/actions",
        json={
            "action": "read_text_file",
            "parameters": {"path": str(secret)},
            "approved": True,
        },
    )
    assert response.status_code == 422
    assert "outside" in response.json()["detail"].lower()


def test_computer_tools_reject_unlisted_applications(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        computer_api,
        "get_settings",
        lambda: ComputerTestSettings(str(tmp_path / "nova.sqlite3"), ""),
    )
    client = TestClient(app)

    response = client.post(
        "/computer/actions",
        json={
            "action": "open_application",
            "parameters": {"app": "powershell"},
            "approved": True,
        },
    )
    assert response.status_code == 422
    assert "catalogue" in response.json()["detail"].lower()


def test_windows_settings_launch_uses_native_shell_open(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    calls = []
    monkeypatch.setattr(computer_registry.os, "startfile", lambda target: calls.append(target), raising=False)
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    monkeypatch.setattr(
        registry,
        "discover_applications",
        lambda: [{"name": "Windows Settings", "app_id": "windows-settings"}],
    )
    result = registry.execute("open_application", {"app_id": "windows-settings"})

    assert result["message"] == "Opened Windows Settings."
    assert calls == ["ms-settings:"]

def test_discover_apps_from_start_menu_shortcuts(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    root = tmp_path / "Programs"
    nested = root / "Productivity"
    nested.mkdir(parents=True)
    shortcut = nested / "Example Editor.lnk"
    shortcut.write_bytes(b"fake shortcut for catalogue test")
    monkeypatch.setattr(computer_registry, "_start_menu_roots", lambda: [root])

    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    apps = registry.discover_applications()

    assert {"name": "Example Editor", "app_id": str(shortcut.resolve())} in apps
    assert {"name": "Windows Settings", "app_id": "windows-settings"} in apps


def test_launch_only_accepts_currently_discovered_shortcuts(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    root = tmp_path / "Programs"
    root.mkdir()
    shortcut = root / "Trusted App.lnk"
    shortcut.write_bytes(b"fake shortcut")
    launches = []
    monkeypatch.setattr(computer_registry, "_start_menu_roots", lambda: [root])
    monkeypatch.setattr(computer_registry, "_start_shortcut", lambda path: launches.append(path))

    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    registry.execute("open_application", {"app_id": str(shortcut.resolve())})
    assert launches == [str(shortcut.resolve())]

    with pytest.raises(computer_registry.ComputerToolError):
        registry.execute("open_application", {"app_id": str(root / "not-discovered.exe")})



def test_discover_apps_includes_classic_registry_installations(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    monkeypatch.setattr(computer_registry, "_start_menu_roots", lambda: [])
    monkeypatch.setattr(computer_registry, "_registered_start_apps", lambda: [])
    monkeypatch.setattr(
        computer_registry,
        "_installed_registry_apps",
        lambda: [{"name": "Notion", "app_id": r"exe:C:\Program Files\Notion\Notion.exe"}],
    )

    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    apps = registry.discover_applications()

    assert {"name": "Notion", "app_id": r"exe:C:\Program Files\Notion\Notion.exe"} in apps


def test_registered_executable_launch_requires_discovery_and_uses_native_shell(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    executable = tmp_path / "Notion.exe"
    executable.write_bytes(b"test executable")
    app_id = "exe:" + str(executable.resolve())
    calls = []
    monkeypatch.setattr(computer_registry.os, "startfile", lambda target: calls.append(target), raising=False)

    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    monkeypatch.setattr(
        registry,
        "discover_applications",
        lambda: [{"name": "Notion", "app_id": app_id}],
    )
    result = registry.execute("open_application", {"app_id": app_id})

    assert result["message"] == "Opened Notion."
    assert calls == [str(executable.resolve())]

def test_empty_folder_configuration_discovers_accessible_roots(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    monkeypatch.setattr(computer_registry, "_accessible_computer_roots", lambda: [tmp_path.resolve()])
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    assert registry.access_scope == "accessible_drives"
    assert registry.allowed_roots == [tmp_path.resolve()]


def test_search_file_contents_scans_accessible_roots(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    (tmp_path / "notes.txt").write_text("The NOVA project uses local intelligence.", encoding="utf-8")
    monkeypatch.setattr(computer_registry, "_accessible_computer_roots", lambda: [tmp_path.resolve()])
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    result = registry.execute("search_file_contents", {"query": "local intelligence"})
    assert len(result["matches"]) == 1
    assert result["matches"][0]["path"].endswith("notes.txt")


@pytest.mark.skipif(os.name != "nt", reason="Windows Explorer integration is Windows-only")
def test_open_path_requires_existing_path_within_accessible_root(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry, ComputerToolError

    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(computer_registry, "_accessible_computer_roots", lambda: [tmp_path.resolve()])
    monkeypatch.setattr(computer_registry.os, "startfile", lambda path: None, raising=False)
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    result = registry.execute("open_path", {"path": str(target)})
    assert result["path"] == str(target.resolve())
    with pytest.raises(ComputerToolError):
        registry.execute("open_path", {"path": str(tmp_path.parent / "outside.txt")})


def test_read_document_uses_local_extractor(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    root = tmp_path / "documents"
    root.mkdir()
    document = root / "notes.pdf"
    document.write_bytes(b"mock pdf bytes")
    monkeypatch.setattr(computer_registry, "_extract_document_text", lambda path: "Physics assignment due Friday.")
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3", str(root))

    result = registry.execute("read_text_file", {"path": str(document)})

    assert result["content"] == "Physics assignment due Friday."


def test_search_file_contents_includes_office_and_pdf_documents(tmp_path, monkeypatch) -> None:
    from nova.core.computer import registry as computer_registry
    from nova.core.computer.registry import ComputerToolRegistry

    root = tmp_path / "documents"
    root.mkdir()
    (root / "assignment.pdf").write_bytes(b"pdf")
    (root / "budget.xlsx").write_bytes(b"xlsx")
    monkeypatch.setattr(computer_registry, "_extract_document_text", lambda path: "coursework deadline")
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3", str(root))

    result = registry.execute("search_file_contents", {"query": "deadline"})

    assert {Path(item["path"]).name for item in result["matches"]} == {"assignment.pdf", "budget.xlsx"}
