"""Typed tool registry for bounded, auditable NOVA function execution.

This is a small agent runtime foundation, not an unrestricted Python or shell
execution facility. Simulation tools report simulated state only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    simulation: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def describe(self) -> list[dict[str, Any]]:
        return [{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "simulation": tool.simulation,
        } for tool in self._tools.values()]

    def validate_chain(self, calls: list[dict[str, Any]]) -> list[tuple[ToolSpec, dict[str, Any]]]:
        """Validate every call and argument before any handler can run."""
        if not calls or len(calls) > 5:
            raise ValueError("A tool chain must contain between one and five calls.")
        validated: list[tuple[ToolSpec, dict[str, Any]]] = []
        for call in calls:
            if not isinstance(call, dict):
                raise ValueError("Each tool call must be an object.")
            name = str(call.get("name", ""))
            tool = self._tools.get(name)
            if tool is None:
                raise ValueError(f"Unregistered tool: {name}")
            arguments = call.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError(f"Arguments for {name} must be an object.")
            required = tool.parameters.get("required", [])
            properties = tool.parameters.get("properties", {})
            if set(arguments) - set(properties):
                raise ValueError(f"Unknown argument supplied to {name}.")
            if any(key not in arguments for key in required):
                raise ValueError(f"Missing required argument for {name}.")
            for key, value in arguments.items():
                schema = properties.get(key, {})
                if "enum" in schema and value not in schema["enum"]:
                    raise ValueError(f"Invalid value for {name}.{key}.")
                expected = schema.get("type")
                if expected == "string" and not isinstance(value, str):
                    raise ValueError(f"{name}.{key} must be a string.")
                if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                    raise ValueError(f"{name}.{key} must be an integer.")
                if expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                    raise ValueError(f"{name}.{key} must be numeric.")
                if expected == "boolean" and not isinstance(value, bool):
                    raise ValueError(f"{name}.{key} must be a boolean.")
            validated.append((tool, arguments))
        return validated

    def execute_chain(self, calls: list[dict[str, Any]], *, approved: bool = False) -> list[dict[str, Any]]:
        """Run a fully validated, approved chain and preserve partial outcomes."""
        validated = self.validate_chain(calls)
        if not approved:
            raise PermissionError("Tool chain requires explicit approval.")
        results: list[dict[str, Any]] = []
        for index, (tool, arguments) in enumerate(validated, start=1):
            try:
                result = tool.handler(arguments)
                if not isinstance(result, dict):
                    raise TypeError("Tool handler returned an unsupported result.")
                results.append({
                    "step": index, "tool": tool.name,
                    "simulation": tool.simulation, "status": "completed",
                    "result": result,
                })
            except Exception as exc:
                results.append({
                    "step": index, "tool": tool.name,
                    "simulation": tool.simulation, "status": "failed",
                    "error": str(exc)[:500] or type(exc).__name__,
                })
                for skipped_index, (skipped_tool, _args) in enumerate(validated[index:], start=index + 1):
                    results.append({
                        "step": skipped_index, "tool": skipped_tool.name,
                        "simulation": skipped_tool.simulation, "status": "skipped",
                        "reason": f"Stopped because step {index} failed.",
                    })
                break
        return results


class SimulationCore:
    """Deterministic in-memory mock subsystems; no physical interfaces exist."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {
            "aerospace": {"mode": "standby", "altitude_km": 0, "status": "SIMULATED"},
            "smart_grid": {"routing": "balanced", "load_percent": 42, "status": "SIMULATED"},
            "thermal": {"profile": "nominal", "temperature_c": 22.0, "status": "SIMULATED"},
            "holographics": {"projection": "idle", "diagnostics": "ready", "status": "SIMULATED"},
        }
        self.logs: list[dict[str, Any]] = []

    def command(self, subsystem: str, operation: str) -> dict[str, Any]:
        if subsystem not in self.state:
            raise ValueError("Unknown simulation subsystem.")
        allowed = {
            "aerospace": {"diagnostics", "standby", "engage_simulation"},
            "smart_grid": {"diagnostics", "balance_simulation"},
            "thermal": {"diagnostics", "cooling_simulation"},
            "holographics": {"diagnostics", "project_simulation", "clear_simulation"},
        }
        if operation not in allowed[subsystem]:
            raise ValueError("Operation is not available for this simulation subsystem.")
        target = self.state[subsystem]
        if operation == "standby":
            target["mode"] = "standby"
        elif operation == "engage_simulation":
            target["mode"] = "simulated_engaged"
        elif operation == "balance_simulation":
            target["routing"] = "balanced"
        elif operation == "cooling_simulation":
            target["profile"] = "cooling_simulation"
        elif operation == "project_simulation":
            target["projection"] = "active_simulation"
        elif operation == "clear_simulation":
            target["projection"] = "idle"
        entry = {
            "subsystem": subsystem,
            "operation": operation,
            "status": "SIMULATION ONLY — no physical system was controlled",
        }
        self.logs.append(entry)
        self.logs = self.logs[-100:]
        return {"state": dict(target), "log": entry}


def build_default_registry(simulation: SimulationCore | None = None) -> ToolRegistry:
    core = simulation or SimulationCore()
    registry = ToolRegistry()
    # Read-only tools expose real information from the signed-in user session.
    # They remain subject to the same explicit approval gate as every tool chain.
    from nova.core.computer.windows import (
        foreground_window,
        list_processes,
        list_windows,
        system_overview,
    )

    registry.register(ToolSpec(
        name="system.overview",
        description="Read a compact, local snapshot of the operating system and hardware resources.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda _args: system_overview(),
    ))
    registry.register(ToolSpec(
        name="system.processes",
        description="List up to 30 visible process names, IDs, status, and memory use. Does not read command lines or environment variables.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda _args: {"processes": list_processes(30)},
    ))
    registry.register(ToolSpec(
        name="windows.foreground",
        description="Read the title and process ID of the current foreground window.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda _args: {"foreground": foreground_window()},
    ))
    registry.register(ToolSpec(
        name="windows.list_visible",
        description="List up to 30 visible titled application windows and their process IDs.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda _args: {"windows": list_windows(30)},
    ))

    for subsystem, operations in {
        "aerospace": ["diagnostics", "standby", "engage_simulation"],
        "smart_grid": ["diagnostics", "balance_simulation"],
        "thermal": ["diagnostics", "cooling_simulation"],
        "holographics": ["diagnostics", "project_simulation", "clear_simulation"],
    }.items():
        registry.register(ToolSpec(
            name=f"simulation.{subsystem}",
            description=f"Run a labelled simulation operation for the {subsystem} mock subsystem.",
            parameters={
                "type": "object",
                "properties": {"operation": {"type": "string", "enum": operations}},
                "required": ["operation"],
            },
            handler=lambda args, subsystem=subsystem: core.command(subsystem, args["operation"]),
            simulation=True,
        ))
    return registry
