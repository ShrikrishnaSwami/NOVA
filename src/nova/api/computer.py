"""Permission-gated computer tool API."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from nova.config import get_settings
from nova.core.computer import ComputerToolError, ComputerToolRegistry

router = APIRouter(prefix="/computer", tags=["computer control"])


def _registry() -> ComputerToolRegistry:
    settings = get_settings()
    return ComputerToolRegistry(settings.memory_db_path, settings.computer_allowed_roots)


class ComputerActionRequest(BaseModel):
    action: Literal["open_application", "open_path", "list_directory", "search_files", "search_file_contents", "read_text_file"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False


@router.get("/capabilities")
def computer_capabilities() -> dict[str, Any]:
    return _registry().capabilities()


@router.post("/actions")
def run_computer_action(request: ComputerActionRequest) -> dict[str, Any]:
    if not request.approved:
        raise HTTPException(status_code=403, detail="This action requires explicit approval in the NOVA desktop interface.")
    try:
        result = _registry().execute(request.action, request.parameters)
    except ComputerToolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"action": request.action, "result": result}


@router.get("/audit")
def computer_audit(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"entries": _registry().list_audit(limit)}


@router.get("/system")
def computer_system_overview() -> dict[str, Any]:
    from nova.core.computer.windows import foreground_window, system_overview
    result = system_overview()
    result["foreground_window"] = foreground_window()
    return result


@router.get("/processes")
def computer_processes(limit: int = Query(default=100, ge=1, le=300)) -> dict[str, Any]:
    from nova.core.computer.windows import list_processes
    try:
        return {"processes": list_processes(limit)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/windows")
def computer_windows(limit: int = Query(default=100, ge=1, le=300)) -> dict[str, Any]:
    from nova.core.computer.windows import foreground_window, list_windows
    return {"foreground": foreground_window(), "windows": list_windows(limit)}
