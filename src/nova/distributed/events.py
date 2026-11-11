"""Versioned event envelopes shared by NOVA's local services."""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def build_event_envelope(
    event_type: str,
    payload: dict[str, Any],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe, versioned event with traceable identity and origin."""
    normalized_type = event_type.strip()
    if not normalized_type.startswith("nova.events."):
        raise ValueError("NOVA event types must start with 'nova.events.'.")
    if len(normalized_type) > 180 or any(part in {"", ".", ".."} for part in normalized_type.split(".")):
        raise ValueError("The event type is invalid.")
    if not isinstance(payload, dict):
        raise ValueError("Event payload must be an object.")

    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "event_type": normalized_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": source or socket.gethostname(),
        "payload": payload,
    }
