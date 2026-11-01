"""Shared contract registry for NOVA's permissioned automation engine.

Natural-language planners may propose only these typed actions. This module validates
complete plans before the desktop presents per-step approvals and calls typed APIs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ActionContract:
    action_id: str
    description: str
    endpoint: str
    required_payload: frozenset[str]
    optional_payload: frozenset[str] = frozenset()


_ACTIONS = {
    item.action_id: item
    for item in (
        ActionContract("system.volume", "Change master volume", "/computer/system/volume", frozenset({"percent", "approved"})),
        ActionContract("system.brightness", "Change display brightness", "/computer/system/brightness", frozenset({"percent", "approved"})),
        ActionContract("windows.search", "Open Windows Search", "/computer/windows/search", frozenset({"query", "approved"})),
        ActionContract("window.focus", "Focus a window", "/computer/windows/actions", frozenset({"handle", "action", "approved"})),
        ActionContract("window.minimize", "Minimize a window", "/computer/windows/actions", frozenset({"handle", "action", "approved"})),
        ActionContract("window.maximize", "Maximize a window", "/computer/windows/actions", frozenset({"handle", "action", "approved"})),
        ActionContract("window.restore", "Restore a window", "/computer/windows/actions", frozenset({"handle", "action", "approved"})),
        ActionContract("app.activate_control", "Activate an accessible application control", "/computer/windows/controls/actions", frozenset({"handle", "name", "control_type", "approved"})),
        ActionContract("app.enter_text", "Enter text into a non-password field", "/computer/windows/controls/text", frozenset({"handle", "name", "text", "approved"})),
    )
}


class AutomationPlanError(ValueError):
    """Raised when a proposed automation plan violates the shared action contracts."""


class AutomationEngine:
    """Validates bounded plans against NOVA's central action contract registry."""

    max_steps = 5

    @property
    def capabilities(self) -> list[dict[str, str]]:
        return [
            {"id": item.action_id, "description": item.description, "endpoint": item.endpoint}
            for item in _ACTIONS.values()
        ]

    def validate_plan(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(plan, list) or not 1 <= len(plan) <= self.max_steps:
            raise AutomationPlanError(f"An automation plan must contain 1 to {self.max_steps} steps.")
        validated: list[dict[str, Any]] = []
        for index, raw in enumerate(plan, start=1):
            if not isinstance(raw, dict):
                raise AutomationPlanError(f"Step {index} is not a valid action.")
            step = dict(raw)
            if step.get("kind") == "system":
                endpoint = str(step.get("endpoint", ""))
                action_id = {
                    "/computer/system/volume": "system.volume",
                    "/computer/system/brightness": "system.brightness",
                    "/computer/windows/search": "windows.search",
                }.get(endpoint)
                payload = step.get("payload")
                if action_id is None or not isinstance(payload, dict):
                    raise AutomationPlanError(f"Step {index} is not in the system action registry.")
                contract = _ACTIONS[action_id]
                if set(payload) != contract.required_payload or payload.get("approved") is not True:
                    raise AutomationPlanError(f"Step {index} does not match the {action_id} payload contract.")
                if action_id in {"system.volume", "system.brightness"}:
                    value = payload.get("percent")
                    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                        raise AutomationPlanError(f"Step {index} has an invalid percentage.")
                if action_id == "windows.search":
                    query = payload.get("query")
                    if not isinstance(query, str) or not query.strip() or len(query) > 200:
                        raise AutomationPlanError(f"Step {index} has an invalid Windows Search query.")
                step["action_id"] = action_id
            elif step.get("kind") == "window":
                action = str(step.get("action", ""))
                target = str(step.get("target", "")).strip()
                action_id = f"window.{action}"
                if action_id not in _ACTIONS or not target or len(target) > 120:
                    raise AutomationPlanError(f"Step {index} is not a supported window action.")
                step["action_id"] = action_id
            else:
                raise AutomationPlanError(f"Step {index} has an unsupported action kind.")
            validated.append(step)
        return validated


def execute_plan(
    engine: AutomationEngine,
    plan: list[dict[str, Any]],
    execute_step: Callable[[dict[str, Any], int], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Run a validated plan sequentially; stop at the first cancelled or failed step.

    The callback owns the user-facing approval prompt and must return None when
    the user cancels or the action cannot be completed.
    """
    validated = engine.validate_plan(plan)
    results: list[dict[str, Any]] = []
    for index, step in enumerate(validated, start=1):
        try:
            result = execute_step(step, index)
        except Exception as exc:
            results.append({"step": index, "status": "failed", "message": str(exc)})
            break
        if result is None:
            results.append({"step": index, "status": "cancelled"})
            break
        results.append({"step": index, "status": "completed", "result": result})
    return results
