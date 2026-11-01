import pytest

from nova.core.runtime.agent import _extract_json, validate_proposal
from nova.core.runtime.tools import build_default_registry


def test_extracts_json_from_plain_or_fenced_model_output():
    assert _extract_json('{"tool_calls": [], "reason": ""}')["tool_calls"] == []
    assert _extract_json(' ```json\n{"tool_calls": [], "reason": ""}\n``` ')["tool_calls"] == []


def test_empty_tool_plan_is_valid():
    proposal = validate_proposal({"tool_calls": [], "reason": ""}, build_default_registry())
    assert proposal == {"tool_calls": [], "reason": ""}


def test_rejects_unregistered_model_tool():
    with pytest.raises(ValueError, match="unregistered"):
        validate_proposal(
            {"tool_calls": [{"name": "python.exec", "arguments": {}}]},
            build_default_registry(),
        )


def test_rejects_invalid_registered_tool_arguments():
    with pytest.raises(ValueError, match="Invalid value"):
        validate_proposal(
            {"tool_calls": [{
                "name": "simulation.thermal",
                "arguments": {"operation": "disable_safety"},
            }]},
            build_default_registry(),
        )


def test_rejects_more_than_five_calls():
    calls = [{"name": "simulation.thermal", "arguments": {"operation": "diagnostics"}}] * 6
    with pytest.raises(ValueError, match="invalid tool-call list"):
        validate_proposal({"tool_calls": calls}, build_default_registry())



def test_real_read_only_system_tool_is_registered_and_requires_approval():
    registry = build_default_registry()
    assert "system.overview" in {item["name"] for item in registry.describe()}
    calls = [{"name": "system.overview", "arguments": {}}]
    with pytest.raises(PermissionError, match="approval"):
        registry.execute_chain(calls, approved=False)
    results = registry.execute_chain(calls, approved=True)
    assert results[0]["tool"] == "system.overview"
    assert "platform" in results[0]["result"]



def test_tool_chain_reports_partial_success_and_stops_after_failure():
    from nova.core.runtime.tools import ToolRegistry, ToolSpec

    registry = ToolRegistry()
    registry.register(ToolSpec("test.ok", "success", {"properties": {}, "required": []},
                               lambda _args: {"message": "done"}))
    registry.register(ToolSpec("test.fail", "failure", {"properties": {}, "required": []},
                               lambda _args: (_ for _ in ()).throw(RuntimeError("device unavailable"))))
    registry.register(ToolSpec("test.never", "must not run", {"properties": {}, "required": []},
                               lambda _args: pytest.fail("A later step ran after failure.")))
    results = registry.execute_chain([
        {"name": "test.ok", "arguments": {}},
        {"name": "test.fail", "arguments": {}},
        {"name": "test.never", "arguments": {}},
    ], approved=True)
    assert [item["status"] for item in results] == ["completed", "failed", "skipped"]
    assert results[1]["error"] == "device unavailable"
    assert results[2]["reason"] == "Stopped because step 2 failed."


def test_tool_chain_validates_all_calls_before_any_execution():
    from nova.core.runtime.tools import ToolRegistry, ToolSpec

    executed = []
    registry = ToolRegistry()
    registry.register(ToolSpec("test.record", "record", {"properties": {}, "required": []},
                               lambda _args: executed.append(True) or {"ok": True}))
    with pytest.raises(ValueError, match="Unregistered tool"):
        registry.execute_chain([
            {"name": "test.record", "arguments": {}},
            {"name": "not.registered", "arguments": {}},
        ], approved=True)
    assert executed == []
