"""Live, read-only telemetry and proactive alert monitoring.

The monitor reports conditions; it never changes system settings or executes
maintenance actions autonomously.
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import psutil


def _foreground_window() -> str | None:
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.windll.user32
        handle = user32.GetForegroundWindow()
        if not handle:
            return None
        length = user32.GetWindowTextLengthW(handle)
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(min(length + 1, 512))
        user32.GetWindowTextW(handle, buffer, len(buffer))
        title = buffer.value.strip()
        return title[:240] or None
    except (AttributeError, OSError, ValueError):
        return None


@dataclass(slots=True)
class SystemState:
    """Latest local telemetry snapshot. Values are observations, not commands."""

    captured_at: float = field(default_factory=time.time)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_bytes: int = 0
    memory_available_bytes: int = 0
    network_sent_bytes: int = 0
    network_recv_bytes: int = 0
    network_send_bytes_per_second: float = 0.0
    network_recv_bytes_per_second: float = 0.0
    active_window: str | None = None
    process_count: int = 0
    top_processes: list[dict[str, Any]] = field(default_factory=list)
    status: str = "nominal"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SystemStateMonitor:
    """Async telemetry sampler with bounded alert history and no autonomous writes."""

    def __init__(self, interval_seconds: float = 2.0,
                 on_alert: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.interval_seconds = max(1.0, min(float(interval_seconds), 60.0))
        self.on_alert = on_alert
        self.state = SystemState()
        self.alerts: deque[dict[str, Any]] = deque(maxlen=100)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._previous_net: tuple[int, int, float] | None = None
        self._alerted: dict[str, float] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        psutil.cpu_percent(interval=None)
        self._task = asyncio.create_task(self._run(), name="nova-system-monitor")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._sample)
            except Exception as exc:
                self._record_alert("telemetry.unavailable", "warning", f"Telemetry sampling failed: {type(exc).__name__}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

    def _sample(self) -> None:
        vm = psutil.virtual_memory()
        net = psutil.net_io_counters()
        now = time.monotonic()
        send_rate = recv_rate = 0.0
        if self._previous_net:
            sent_before, recv_before, time_before = self._previous_net
            elapsed = max(now - time_before, 0.001)
            send_rate = max(0, net.bytes_sent - sent_before) / elapsed
            recv_rate = max(0, net.bytes_recv - recv_before) / elapsed
        self._previous_net = (net.bytes_sent, net.bytes_recv, now)

        processes: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = proc.info
                memory = info.get("memory_info")
                processes.append({
                    "pid": int(info["pid"]),
                    "name": str(info.get("name") or "unknown")[:80],
                    "memory_bytes": int(memory.rss) if memory else 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        processes.sort(key=lambda item: item["memory_bytes"], reverse=True)
        cpu = psutil.cpu_percent(interval=None)
        status = "critical" if cpu >= 95 or vm.percent >= 97 else (
            "warning" if cpu >= 85 or vm.percent >= 90 else "nominal"
        )
        self.state = SystemState(
            captured_at=time.time(),
            cpu_percent=cpu,
            memory_percent=float(vm.percent),
            memory_used_bytes=int(vm.used),
            memory_available_bytes=int(vm.available),
            network_sent_bytes=int(net.bytes_sent),
            network_recv_bytes=int(net.bytes_recv),
            network_send_bytes_per_second=round(send_rate, 2),
            network_recv_bytes_per_second=round(recv_rate, 2),
            active_window=_foreground_window(),
            process_count=len(processes),
            top_processes=processes[:8],
            status=status,
        )
        if cpu >= 95:
            self._record_alert("cpu.critical", "critical", f"CPU utilization is {cpu:.0f}%.")
        elif cpu >= 85:
            self._record_alert("cpu.high", "warning", f"CPU utilization is {cpu:.0f}%.")
        if vm.percent >= 97:
            self._record_alert("memory.critical", "critical", f"Memory utilization is {vm.percent:.0f}%.")
        elif vm.percent >= 90:
            self._record_alert("memory.high", "warning", f"Memory utilization is {vm.percent:.0f}%.")

    def _record_alert(self, key: str, severity: str, message: str) -> None:
        now = time.time()
        if now - self._alerted.get(key, 0.0) < 300:
            return
        self._alerted[key] = now
        alert = {
            "timestamp": now,
            "severity": severity,
            "key": key,
            "message": message,
            "source": "local-telemetry",
        }
        self.alerts.append(alert)
        if self.on_alert is not None:
            try:
                self.on_alert(alert)
            except Exception:
                # Monitoring remains healthy even if desktop notifications fail.
                pass

    def snapshot(self) -> dict[str, Any]:
        return self.state.to_dict()

    def recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.alerts)[-max(1, min(limit, 100)):]
