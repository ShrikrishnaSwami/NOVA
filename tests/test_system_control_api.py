from fastapi.testclient import TestClient

from nova.api import computer as computer_api
from nova.main import app


def test_system_and_search_mutations_require_approval(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(computer_api, "_registry", lambda: type(
        "Audit", (), {"_audit": lambda self, *args: calls.append(args)}
    )())
    client = TestClient(app)

    volume = client.post("/computer/system/volume", json={"percent": 40})
    brightness = client.post("/computer/system/brightness", json={"percent": 60})
    search = client.post("/computer/windows/search", json={"query": "tax documents"})

    assert volume.status_code == 403
    assert brightness.status_code == 403
    assert search.status_code == 403
    assert calls == []
