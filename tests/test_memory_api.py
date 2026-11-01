from fastapi.testclient import TestClient

from nova.api import memory as memory_api
from nova.core.memory import MemoryStore
from nova.main import app


class TestSettings:
    def __init__(self, database_path: str) -> None:
        self.memory_db_path = database_path


def test_memory_endpoints_support_approval_edit_and_delete(tmp_path, monkeypatch) -> None:
    database = tmp_path / "api-memory.sqlite3"
    monkeypatch.setattr(memory_api, "get_settings", lambda: TestSettings(str(database)))
    store = MemoryStore(database)
    memory = store.capture_from_text("My phone number is 555-0100.")
    assert memory is not None

    client = TestClient(app)
    pending = client.get("/memory?status=pending")
    assert pending.status_code == 200
    assert pending.json()["memories"][0]["id"] == memory["id"]

    approved = client.post(f"/memory/{memory['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    edited = client.patch(f"/memory/{memory['id']}", json={"content": "My contact number is saved with approval."})
    assert edited.status_code == 200

    deleted = client.delete(f"/memory/{memory['id']}")
    assert deleted.status_code == 200
    assert client.get("/memory").json()["memories"] == []


def test_conversation_endpoints_list_read_and_delete(tmp_path, monkeypatch) -> None:
    database = tmp_path / "api-conversations.sqlite3"
    monkeypatch.setattr(memory_api, "get_settings", lambda: TestSettings(str(database)))
    store = MemoryStore(database)
    store.record_turn("api-conversation", "Hello NOVA", "Hello there.")

    client = TestClient(app)
    listing = client.get("/conversations")
    assert listing.status_code == 200
    assert listing.json()["conversations"][0]["id"] == "api-conversation"

    detail = client.get("/conversations/api-conversation")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2

    deleted = client.delete("/conversations/api-conversation")
    assert deleted.status_code == 200
    assert client.get("/conversations/api-conversation").status_code == 404


def test_memory_endpoints_support_pinning_and_stats(tmp_path, monkeypatch) -> None:
    database = tmp_path / "api-memory-pinning.sqlite3"
    monkeypatch.setattr(memory_api, "get_settings", lambda: TestSettings(str(database)))
    store = MemoryStore(database)
    memory = store.capture_from_text("I prefer dark mode in desktop apps.")
    assert memory is not None

    client = TestClient(app)
    stats = client.get("/memory/stats")
    assert stats.status_code == 200
    assert stats.json()["total"] == 1

    pinned = client.patch(f"/memory/{memory['id']}/pin", json={"pinned": True})
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True
    assert client.get("/memory").json()["memories"][0]["pinned"] is True

    unpinned = client.patch(f"/memory/{memory['id']}/pin", json={"pinned": False})
    assert unpinned.status_code == 200
    assert unpinned.json()["pinned"] is False
