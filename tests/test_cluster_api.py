from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nova.api import cluster


class FakeBus:
    connected = True

    def status(self) -> dict:
        return {"enabled": True, "connected": True, "transport": "nats-jetstream"}

    async def publish(self, event_type: str, payload: dict) -> dict:
        return {"event_id": "test-event-id", "event_type": event_type, "payload": payload}


def make_client(bus=None) -> TestClient:
    app = FastAPI()
    app.state.event_bus = bus
    app.include_router(cluster.router)
    return TestClient(app)


def test_cluster_status_reports_standalone_mode(monkeypatch) -> None:
    monkeypatch.setattr(cluster, "get_settings", lambda: SimpleNamespace(distributed_enabled=False))
    response = make_client().get("/cluster/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["connected"] is False
    assert response.json()["reason"] == "disabled"


def test_cluster_status_reports_connected_bus() -> None:
    response = make_client(FakeBus()).get("/cluster/status")

    assert response.status_code == 200
    assert response.json()["connected"] is True


def test_diagnostic_event_is_published_through_bus() -> None:
    response = make_client(FakeBus()).post(
        "/cluster/diagnostics/publish",
        json={"message": "test event"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "published": True,
        "event_id": "test-event-id",
        "event_type": "nova.events.diagnostic",
    }


def test_diagnostic_event_returns_503_without_connected_bus() -> None:
    response = make_client().post(
        "/cluster/diagnostics/publish",
        json={"message": "test event"},
    )

    assert response.status_code == 503


def test_diagnostic_event_rejects_oversized_message() -> None:
    response = make_client(FakeBus()).post(
        "/cluster/diagnostics/publish",
        json={"message": "x" * 257},
    )

    assert response.status_code == 422