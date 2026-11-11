from __future__ import annotations

import pytest

from nova.distributed.events import build_event_envelope


def test_event_envelope_contains_version_identity_source_and_payload() -> None:
    event = build_event_envelope(
        "nova.events.diagnostic",
        {"message": "pipeline test"},
        source="test-node",
    )

    assert event["schema_version"] == 1
    assert event["event_type"] == "nova.events.diagnostic"
    assert event["source"] == "test-node"
    assert event["payload"] == {"message": "pipeline test"}
    assert event["event_id"]
    assert event["occurred_at"]


@pytest.mark.parametrize("event_type", ["diagnostic", "nova.events.", "nova..events.test"])
def test_event_envelope_rejects_invalid_subjects(event_type: str) -> None:
    with pytest.raises(ValueError):
        build_event_envelope(event_type, {})


def test_event_envelope_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        build_event_envelope("nova.events.diagnostic", ["not", "an", "object"])  # type: ignore[arg-type]
