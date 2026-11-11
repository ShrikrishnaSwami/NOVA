"""Optional NATS JetStream event publisher for the NOVA host process."""

from __future__ import annotations

import json
import logging
from typing import Any

from nova.distributed.events import build_event_envelope

logger = logging.getLogger(__name__)

STREAM_NAME = "NOVA_EVENTS"
EVENT_SUBJECT = "nova.events.>"


class NatsEventBus:
    """Small async publisher; messaging failures never silently execute work."""

    def __init__(self, url: str, node_id: str = "nova-windows-host") -> None:
        self.url = url
        self.node_id = node_id
        self._connection = None
        self._jetstream = None

    @property
    def connected(self) -> bool:
        return bool(self._connection is not None and self._connection.is_connected)

    async def connect(self) -> None:
        """Connect and ensure the persistent event stream exists."""
        import nats
        from nats.js.api import RetentionPolicy, StorageType, StreamConfig

        self._connection = await nats.connect(
            servers=[self.url],
            name=self.node_id,
            connect_timeout=2,
            max_reconnect_attempts=0,
        )
        self._jetstream = self._connection.jetstream()
        try:
            await self._jetstream.stream_info(STREAM_NAME)
        except Exception:
            try:
                await self._jetstream.add_stream(
                    config=StreamConfig(
                        name=STREAM_NAME,
                        subjects=[EVENT_SUBJECT],
                        retention=RetentionPolicy.LIMITS,
                        storage=StorageType.FILE,
                        max_age=7 * 24 * 60 * 60,
                    )
                )
            except Exception:
                # Another local service may have created it concurrently.
                await self._jetstream.stream_info(STREAM_NAME)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist an event in JetStream and return its event identity."""
        if not self.connected or self._jetstream is None:
            raise RuntimeError("NOVA's local event broker is not connected.")
        envelope = build_event_envelope(event_type, payload, source=self.node_id)
        await self._jetstream.publish(
            envelope["event_type"],
            json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        )
        return envelope

    async def close(self) -> None:
        """Drain the connection cleanly during API shutdown."""
        if self._connection is not None:
            try:
                await self._connection.drain()
            finally:
                self._connection = None
                self._jetstream = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "connected": self.connected,
            "node_id": self.node_id,
            "transport": "nats-jetstream",
            "stream": STREAM_NAME,
        }
