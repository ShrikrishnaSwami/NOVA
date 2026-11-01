"""Runtime telemetry and explicitly approved simulation tool endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from nova.core.ai import ChatMessage, get_provider
from nova.core.runtime.agent import propose_tools

router = APIRouter(prefix="/runtime", tags=["runtime"])


class ToolCall(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)


class ToolChainRequest(BaseModel):
    calls: list[ToolCall] = Field(min_length=1, max_length=5)
    approved: bool = False


class ToolPlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


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


@router.post("/tools/plan")
async def plan_tools(payload: ToolPlanRequest, request: Request) -> dict:
    """Ask the configured model to propose registered tools; never executes them."""
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Tool runtime is not ready.")
    try:
        proposal = await propose_tools(
            get_provider(),
            [ChatMessage(role="user", content=payload.message)],
            registry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Model returned an invalid tool plan: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="NOVA could not obtain a valid tool plan.") from exc
    return {"proposal": proposal, "requires_approval": bool(proposal["tool_calls"])}


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
