from nova.core.memory.store import MemoryStore


def test_conversations_are_persisted_and_deleted(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    store.record_turn("conversation-1", "Hello NOVA", "Hello. How can I help?")

    conversations = store.list_conversations()
    messages = store.get_messages("conversation-1")

    assert conversations[0]["id"] == "conversation-1"
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert store.delete_conversation("conversation-1") is True
    assert store.get_messages("conversation-1") == []


def test_safe_preferences_are_saved_and_retrieved_by_local_vector_search(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    memory = store.capture_from_text("I prefer dark mode for my desktop applications.")

    assert memory is not None
    assert memory["status"] == "approved"

    matches = store.retrieve("dark mode desktop")
    assert matches
    assert matches[0]["id"] == memory["id"]


def test_explicit_remember_request_is_saved(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    memory = store.capture_from_text("Please remember that my favourite colour is blue.")

    assert memory is not None
    assert memory["status"] == "approved"
    assert "favourite colour is blue" in memory["content"]


def test_high_impact_memory_waits_for_approval(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    memory = store.capture_from_text("My goal is to launch NOVA as an open-source assistant.")

    assert memory is not None
    assert memory["status"] == "pending"
    assert store.retrieve("launch NOVA") == []
    assert store.approve_memory(memory["id"]) is True
    assert store.retrieve("launch NOVA")


def test_sensitive_credentials_are_never_saved(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    memory = store.capture_from_text("Please remember that my password is hunter2.")

    assert memory is None
    assert store.list_memories() == []


def test_sensitive_personal_facts_wait_for_approval(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    memory = store.capture_from_text("My phone number is 555-0100.")

    assert memory is not None
    assert memory["status"] == "pending"
    assert memory["category"] == "sensitive"
    assert store.retrieve("phone number") == []


def test_memories_can_be_edited_and_deleted(tmp_path) -> None:
    store = MemoryStore(tmp_path / "nova.sqlite3")
    memory = store.capture_from_text("I like building desktop software.")

    assert memory is not None
    assert store.update_memory(memory["id"], "I like building local-first desktop software.")
    assert store.list_memories()[0]["content"] == "I like building local-first desktop software."
    assert store.delete_memory(memory["id"])
    assert store.list_memories() == []
