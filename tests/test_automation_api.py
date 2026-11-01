from fastapi.testclient import TestClient

from nova.main import app


def test_automation_capabilities_are_registered_and_bounded() -> None:
    response = TestClient(app).get("/computer/automation/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["max_steps"] == 5
    action_ids = {item["id"] for item in payload["actions"]}
    assert {"system.volume", "system.brightness", "windows.search", "window.focus", "window.minimize"} <= action_ids
