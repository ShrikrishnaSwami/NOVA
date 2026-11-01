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



class WindowControlRequest(BaseModel):
    handle: int = Field(ge=1)
    action: Literal["focus", "minimize", "restore", "maximize"]
    approved: bool = False


@router.post("/windows/actions")
def control_computer_window(request: WindowControlRequest) -> dict[str, Any]:
    if not request.approved:
        raise HTTPException(status_code=403, detail="Window control requires explicit approval in the NOVA desktop interface.")
    from nova.core.computer.window_control import WindowControlError, control_window
    try:
        return control_window(request.handle, request.action)
    except WindowControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



class VolumeControlRequest(BaseModel):
    percent: int = Field(ge=0, le=100)
    muted: bool | None = None
    approved: bool = False


class BrightnessControlRequest(BaseModel):
    percent: int = Field(ge=0, le=100)
    approved: bool = False


class WindowsSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    approved: bool = False


@router.post("/system/volume")
def set_computer_volume(request: VolumeControlRequest) -> dict[str, Any]:
    if not request.approved:
        raise HTTPException(status_code=403, detail="Changing system volume requires explicit approval.")
    from nova.core.computer.system_controls import WindowsControlError, set_master_volume
    try:
        result = set_master_volume(request.percent, request.muted)
        _registry()._audit("set_system_volume", {}, "success", result["message"])
        return result
    except WindowsControlError as exc:
        _registry()._audit("set_system_volume", {}, "blocked", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/system/brightness")
def set_computer_brightness(request: BrightnessControlRequest) -> dict[str, Any]:
    if not request.approved:
        raise HTTPException(status_code=403, detail="Changing display brightness requires explicit approval.")
    from nova.core.computer.system_controls import WindowsControlError, set_display_brightness
    try:
        result = set_display_brightness(request.percent)
        _registry()._audit("set_display_brightness", {}, "success", result["message"])
        return result
    except WindowsControlError as exc:
        _registry()._audit("set_display_brightness", {}, "blocked", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/windows/search")
def launch_windows_search(request: WindowsSearchRequest) -> dict[str, Any]:
    if not request.approved:
        raise HTTPException(status_code=403, detail="Opening Windows Search requires explicit approval.")
    from nova.core.computer.system_controls import WindowsControlError, open_windows_search
    try:
        result = open_windows_search(request.query)
        _registry()._audit("windows_search", {"query": request.query}, "success", "Opened native Windows Search.")
        return result
    except WindowsControlError as exc:
        _registry()._audit("windows_search", {"query": request.query}, "blocked", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc



@router.get("/windows/{handle}/controls")
def inspect_window_controls(handle: int, limit: int = Query(default=100, ge=1, le=200)) -> dict[str, Any]:
    from nova.core.computer.ui_automation import UIAutomationError, list_interactive_controls
    try:
        return {"controls": list_interactive_controls(handle, limit)}
    except UIAutomationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class UIControlActionRequest(BaseModel):
    handle: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    control_type: Literal["Button", "TabItem", "MenuItem", "Hyperlink", "CheckBox", "RadioButton"]
    approved: bool = False


@router.post("/windows/controls/actions")
def activate_window_control(request: UIControlActionRequest) -> dict[str, Any]:
    if not request.approved:
        raise HTTPException(status_code=403, detail="Activating an application control requires explicit approval.")
    from nova.core.computer.ui_automation import UIAutomationError, click_named_control
    try:
        result = click_named_control(request.handle, request.name, request.control_type)
        _registry()._audit("activate_ui_control", {}, "success", f"Activated {request.control_type}: {request.name}")
        return result
    except UIAutomationError as exc:
        _registry()._audit("activate_ui_control", {}, "blocked", str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
