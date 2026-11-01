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
    assert "allowlist" in response.json()["detail"].lower()


def test_windows_settings_launch_uses_fixed_uri_without_shell(tmp_path, monkeypatch) -> None:
    from nova.core.computer.registry import ComputerToolRegistry

    calls = []
    monkeypatch.setattr(
        "nova.core.computer.registry.subprocess.Popen",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )
    registry = ComputerToolRegistry(tmp_path / "audit.sqlite3")
    result = registry.execute("open_application", {"app": "windows settings"})

    assert result["message"] == "Opened windows settings."
    assert calls == [
        (["explorer.exe", "ms-settings:"], {"shell": False, "close_fds": True})
    ]
