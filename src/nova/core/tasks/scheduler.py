"""Background scheduler for explicitly approved, read-only maintenance tasks."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from nova.core.tasks.store import TaskStore


class TaskScheduler:
    """Poll due tasks and dispatch only registered read-only handlers."""

    def __init__(self, store: TaskStore, interval_seconds: float = 15.0,
                 handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None) -> None:
        self.store = store
        self.interval_seconds = interval_seconds
        self.handlers = handlers or {"system.snapshot": self._system_snapshot, "storage.report": self._storage_report}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def capabilities() -> list[dict[str, str]]:
        return [
            {"id": "system.snapshot", "title": "System status snapshot", "risk": "read_only", "description": "Record CPU, memory, and platform status."},
            {"id": "storage.report", "title": "Storage usage report", "risk": "read_only", "description": "Report disk capacity and free space without modifying files."},
        ]

    @staticmethod
    def _system_snapshot(_: dict[str, Any]) -> dict[str, Any]:
        import psutil
        return {"platform": __import__("platform").platform(), "cpu_percent": psutil.cpu_percent(interval=0.2),
                "memory_percent": psutil.virtual_memory().percent, "status": "collected"}

    @staticmethod
    def _storage_report(_: dict[str, Any]) -> dict[str, Any]:
        import psutil
        drives = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append({"mountpoint": partition.mountpoint, "total_bytes": usage.total,
                               "used_bytes": usage.used, "free_bytes": usage.free,
                               "percent": usage.percent})
            except (PermissionError, OSError):
                continue
        return {"drives": drives, "status": "collected"}

    def run_due(self, now: datetime | None = None) -> int:
        executed = 0
        for task in self.store.due(now=now):
            handler = self.handlers.get(task["action_id"])
            if handler is None:
                self.store.record_run(task, "blocked", {"error": "Action is not registered."})
                continue
            try:
                result = handler(task["parameters"])
                self.store.record_run(task, "success", result)
            except Exception as exc:
                self.store.record_run(task, "error", {"error": str(exc)[:500]})
            executed += 1
        return executed

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="NOVA-TaskScheduler", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due()
            except Exception:
                # A transient scheduler error must not terminate the desktop service.
                pass
            self._stop.wait(self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
