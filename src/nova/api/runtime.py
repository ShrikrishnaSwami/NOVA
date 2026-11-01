"""Runtime telemetry and explicitly approved simulation tool endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/runtime", tags=["runtime"])


class ToolCall(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)


class ToolChainRequest(BaseModel):
    calls: list[ToolCall] = Field(min_length=1, max_length=5)
    approved: bool = False


@router.get("/state")
async def runtime_state(request: Request) -> dict:
    monitor = getattr(request.app.state, "system_monitor", None)
    if monitor is None:
        return {"status": "starting", "telemetry": {}}
    return {
        "status": monitor.state.status,
        "telemetry": monitor.snapshot(),
        "alerts": monitor.recent_alerts(),
    }


@router.get("/tools")
async def runtime_tools(request: Request) -> dict:
    registry = getattr(request.app.state, "tool_registry", None)
    return {"tools": registry.describe() if registry else []}


@router.post("/tools/execute")
async def execute_tools(payload: ToolChainRequest, request: Request) -> dict:
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Tool runtime is not ready.")
    try:
        results = registry.execute_chain(
            [call.model_dump() for call in payload.calls],
            approved=payload.approved,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": results}
