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
