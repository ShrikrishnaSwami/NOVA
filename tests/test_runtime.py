from nova.core.runtime.state import SystemStateMonitor
from nova.core.runtime.tools import SimulationCore, build_default_registry


def test_monitor_exposes_safe_initial_snapshot():
    monitor = SystemStateMonitor()
    snapshot = monitor.snapshot()
    assert snapshot["status"] == "nominal"
    assert "cpu_percent" in snapshot
    assert "top_processes" in snapshot


def test_simulation_subsystems_are_explicitly_labelled():
    core = SimulationCore()
    result = core.command("aerospace", "engage_simulation")
    assert result["state"]["mode"] == "simulated_engaged"
    assert "SIMULATION ONLY" in result["log"]["status"]
    assert len(core.logs) == 1


def test_registry_requires_approval_and_rejects_unknown_tools():
    registry = build_default_registry()
    calls = [{"name": "simulation.thermal", "arguments": {"operation": "cooling_simulation"}}]
    try:
        registry.execute_chain(calls)
        assert False, "approval should be required"
    except PermissionError:
        pass
    result = registry.execute_chain(calls, approved=True)
    assert result[0]["simulation"] is True
    assert "SIMULATION ONLY" in result[0]["result"]["log"]["status"]


def test_monitor_emits_alert_callback_without_breaking_sampling():
    events = []
    monitor = SystemStateMonitor(on_alert=events.append)
    monitor._record_alert("cpu.high", "warning", "CPU utilization is high.")
    assert events and events[0]["key"] == "cpu.high"
    assert monitor.recent_alerts()[0]["message"] == "CPU utilization is high."


def test_registry_validates_entire_chain_before_running():
    core = SimulationCore()
    registry = build_default_registry(core)
    calls = [
        {"name": "simulation.thermal", "arguments": {"operation": "cooling_simulation"}},
        {"name": "unregistered.tool", "arguments": {}},
    ]
    try:
        registry.execute_chain(calls, approved=True)
        assert False, "unknown tool should fail"
    except ValueError:
        pass
    assert core.logs == []
