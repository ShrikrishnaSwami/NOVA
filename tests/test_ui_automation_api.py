from fastapi.testclient import TestClient

from nova.main import app


def test_ui_automation_activation_requires_explicit_approval() -> None:
    client = TestClient(app)
    response = client.post(
        "/computer/windows/controls/actions",
        json={"handle": 123, "name": "Save", "control_type": "Button"},
    )
    assert response.status_code == 403


def test_text_entry_api_requires_explicit_approval() -> None:
    client = TestClient(app)
    response = client.post(
        "/computer/windows/controls/text",
        json={"handle": 123, "name": "Search", "text": "hello"},
    )
    assert response.status_code == 403
