from __future__ import annotations

from nova.distributed.supervisor import ClusterSupervisor


def test_disabled_supervisor_does_not_start_a_thread() -> None:
    supervisor = ClusterSupervisor(enabled=False)

    supervisor.start_background()

    assert supervisor.state == "disabled"
    assert supervisor._thread is None


def test_supervisor_reports_missing_docker_without_crashing(monkeypatch) -> None:
    supervisor = ClusterSupervisor(enabled=True)
    monkeypatch.setattr("nova.distributed.supervisor.shutil.which", lambda _name: None)

    supervisor._start_cluster()

    assert supervisor.state == "unavailable"
    assert "Docker Desktop" in (supervisor.error or "")