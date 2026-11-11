"""Local distributed runtime primitives for NOVA."""

from nova.distributed.bus import NatsEventBus
from nova.distributed.events import build_event_envelope

__all__ = ["NatsEventBus", "build_event_envelope"]
