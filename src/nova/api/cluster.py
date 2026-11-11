"""Local distributed-cluster diagnostics endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from nova.config import get_settings

router = APIRouter(prefix="/cluster", tags=["local cluster"])


class DiagnosticEventRequest(BaseModel):
    message: str = Field(min_length=1, max_length=256)


@router.get("/status")
async def cluster_status(request: Request) -> dict:
    """Report the host-to-broker connection without exposing credentials."""
    settings = get_settings()
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        return {
            "enabled": settings.distributed_enabled,
            "connected": False,
            "transport": "nats-jetstream",
            "reason": "disabled" if not settings.distributed_enabled else "not-connected",
        }
    return bus.status()


@router.post("/diagnostics/publish")
async def publish_diagnostic_event(
    payload: DiagnosticEventRequest,
    request: Request,
) -> dict:
    """Publish a harmless diagnostic event for checking the local event pipeline."""
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None or not bus.connected:
        raise HTTPException(status_code=503, detail="The local NOVA event broker is unavailable.")
    event = await bus.publish(
        "nova.events.diagnostic",
        {"message": payload.message},
    )
    return {"published": True, "event_id": event["event_id"], "event_type": event["event_type"]}
