from __future__ import annotations

import pytest

from nova.core.computer.automation import AutomationEngine, AutomationPlanError, execute_plan


def test_engine_accepts_typed_system_plan() -> None:
    plan = [
        {
            "kind": "system",
            "endpoint": "/computer/system/volume",
            "payload": {"percent": 35, "approved": True},
            "description": "set volume",
        },
        {
            "kind": "system",
            "endpoint": "/computer/system/brightness",
            "payload": {"percent": 60, "approved": True},
            "description": "set brightness",
        },
    ]
    result = AutomationEngine().validate_plan(plan)
    assert result[0]["action_id"] == "system.volume"
    assert result[1]["action_id"] == "system.brightness"


def test_engine_rejects_unapproved_or_unregistered_actions() -> None:
    engine = AutomationEngine()
    with pytest.raises(AutomationPlanError):
        engine.validate_plan([{
            "kind": "system",
            "endpoint": "/computer/system/volume",
            "payload": {"percent": 35, "approved": False},
        }])
    with pytest.raises(AutomationPlanError):
        engine.validate_plan([{"kind": "system", "endpoint": "/computer/system/execute", "payload": {}}])
    with pytest.raises(AutomationPlanError):
        engine.validate_plan([{"kind": "system", "endpoint": "/computer/system/volume", "payload": {"percent": 101, "approved": True}}])


def test_engine_caps_plan_and_stops_after_cancelled_step() -> None:
    engine = AutomationEngine()
    step = {
        "kind": "system",
        "endpoint": "/computer/system/volume",
        "payload": {"percent": 35, "approved": True},
    }
    with pytest.raises(AutomationPlanError):
        engine.validate_plan([step] * 6)
    calls = []
    results = execute_plan(engine, [step, step], lambda current, index: calls.append(index) or None)
    assert calls == [1]
    assert results == [{"step": 1, "status": "cancelled"}]
