from fastapi.testclient import TestClient

from nova.main import app
from nova.core.computer import window_control


def test_window_control_api_requires_explicit_approval(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        window_control,
        "control_window",
        lambda handle, action: calls.append((handle, action)) or {"message": "ok"},
    )
    client = TestClient(app)

    denied = client.post(
        "/computer/windows/actions",
        json={"handle": 123, "action": "focus"},
    )
    assert denied.status_code == 403
    assert calls == []

    allowed = client.post(
        "/computer/windows/actions",
        json={"handle": 123, "action": "focus", "approved": True},
    )
    assert allowed.status_code == 200
    assert allowed.json()["message"] == "ok"
    assert calls == [(123, "focus")]
