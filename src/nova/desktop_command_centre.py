"""Full-screen NOVA command-centre overlay (PySide6).

The dashboard visualises real local telemetry and clearly separates it from
simulated subsystem state. It does not pretend to control physical systems.
"""
from __future__ import annotations

import json
import os
import httpx

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from nova.config import get_settings

_SETTINGS = get_settings()
_API_ROOT = os.getenv("NOVA_API_URL", f"http://{_SETTINGS.host}:{_SETTINGS.port}").rstrip("/")


class _CommandWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def run(self) -> None:
        try:
            response = httpx.post(
                f"{_API_ROOT}/chat",
                json={"message": self.prompt, "history": []},
                timeout=120.0,
            )
            response.raise_for_status()
            self.completed.emit(str(response.json().get("reply", "")))
        except Exception as exc:
            self.failed.emit(f"Command channel unavailable: {exc}")


class DiagnosticNode(QWidget):
    """Low-cost animated diagnostic core suitable for integrated graphics."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(220, 220)
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.timer.start(45)
        self.alert = False

    def set_alert(self, active: bool) -> None:
        if self.alert != active:
            self.alert = active
            self.update()

    def _advance(self) -> None:
        self.phase = (self.phase + 2) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = min(self.width(), self.height()) * 0.30
        accent = QColor(255, 174, 70) if self.alert else QColor(58, 218, 255)
        glow = QRadialGradient(cx, cy, radius * 1.8)
        glow.setColorAt(0, QColor(accent.red(), accent.green(), accent.blue(), 90))
        glow.setColorAt(1, QColor(4, 10, 20, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(int(cx-radius*1.8), int(cy-radius*1.8), int(radius*3.6), int(radius*3.6))
        painter.setBrush(QColor("#081827"))
        painter.setPen(QPen(accent, 2))
        painter.drawEllipse(int(cx-radius), int(cy-radius), int(radius*2), int(radius*2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(accent, 2))
        painter.drawArc(int(cx-radius*1.25), int(cy-radius*1.25), int(radius*2.5), int(radius*2.5), self.phase*16, 235*16)
        painter.setPen(QPen(QColor("#6a8cff"), 2))
        painter.drawArc(int(cx-radius*1.42), int(cy-radius*1.42), int(radius*2.84), int(radius*2.84), -self.phase*11, 120*16)
        painter.setPen(QPen(QColor("#d8f8ff"), 1))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "N O V A")


class NovaCommandCentre(QDialog):
    """Borderless, full-screen telemetry and command dashboard."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NOVA Command Centre")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog { background: #050b14; color: #dff7ff; font-family: 'Segoe UI'; }
            QLabel#eyebrow { color: #58cfe8; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
            QLabel#metric { color: #e6fbff; font-size: 23px; font-weight: 650; }
            QLabel#muted { color: #7897aa; font-size: 11px; }
            QFrame#panel { background: #0a1724; border: 1px solid #17384a; border-radius: 12px; }
            QPushButton { background: #102a3a; color: #b9f2ff; border: 1px solid #286078; border-radius: 7px; padding: 9px 14px; }
            QPushButton:hover { background: #16435a; }
            QLineEdit { background: #081522; color: #e9fbff; border: 1px solid #246078; border-radius: 8px; padding: 12px; }
            QTextEdit, QListWidget { background: #06111c; color: #a8d5e2; border: 1px solid #163448; border-radius: 8px; }
        """)
        self._worker: _CommandWorker | None = None
        self._last_alert_keys: set[str] = set()
        self._build()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(2000)
        self.refresh()

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        heading = QLabel(title.upper())
        heading.setObjectName("eyebrow")
        layout.addWidget(heading)
        return frame, layout

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        top = QHBoxLayout()
        title = QLabel("N O V A   /   COMMAND CENTRE")
        title.setObjectName("eyebrow")
        top.addWidget(title)
        top.addStretch()
        self.system_status = QLabel("INITIALISING")
        self.system_status.setObjectName("eyebrow")
        top.addWidget(self.system_status)
        close = QPushButton("EXIT  ✕")
        close.clicked.connect(self.close)
        top.addWidget(close)
        root.addLayout(top)

        grid = QGridLayout()
        grid.setSpacing(12)
        left, left_layout = self._panel("System telemetry")
        self.cpu_value = QLabel("-- %"); self.cpu_value.setObjectName("metric")
        self.ram_value = QLabel("-- %"); self.ram_value.setObjectName("metric")
        self.net_value = QLabel("↓ -- KB/s   ↑ -- KB/s"); self.net_value.setObjectName("metric")
        self.window_value = QLabel("Awaiting foreground window"); self.window_value.setObjectName("muted")
        for label, value in [("CPU LOAD", self.cpu_value), ("MEMORY COMMITMENT", self.ram_value), ("NETWORK THROUGHPUT", self.net_value), ("FOREGROUND WINDOW", self.window_value)]:
            caption = QLabel(label); caption.setObjectName("eyebrow")
            left_layout.addWidget(caption); left_layout.addWidget(value)
        left_layout.addStretch()
        grid.addWidget(left, 0, 0)

        centre, centre_layout = self._panel("Core diagnostics")
        self.node = DiagnosticNode()
        centre_layout.addWidget(self.node, alignment=Qt.AlignmentFlag.AlignCenter)
        self.core_state = QLabel("LOCAL TELEMETRY LINK / CONNECTING")
        self.core_state.setObjectName("eyebrow")
        self.core_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre_layout.addWidget(self.core_state)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(180)
        centre_layout.addWidget(self.log)
        grid.addWidget(centre, 0, 1)

        right, right_layout = self._panel("Active processes")
        self.process_count = QLabel("-- processes"); self.process_count.setObjectName("metric")
        right_layout.addWidget(self.process_count)
        self.process_list = QListWidget()
        right_layout.addWidget(self.process_list, 1)
        grid.addWidget(right, 0, 2)
        grid.setColumnStretch(0, 2); grid.setColumnStretch(1, 3); grid.setColumnStretch(2, 2)
        root.addLayout(grid, 1)

        command_frame, command_layout = self._panel("Command interface")
        command_row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("Enter a request for NOVA…")
        self.command.returnPressed.connect(self.send_command)
        command_row.addWidget(self.command, 1)
        send = QPushButton("TRANSMIT  ↗")
        send.clicked.connect(self.send_command)
        command_row.addWidget(send)
        command_layout.addLayout(command_row)
        self.reply = QLabel("Command channel ready.")
        self.reply.setWordWrap(True)
        self.reply.setObjectName("muted")
        command_layout.addWidget(self.reply)
        root.addWidget(command_frame)

        footer = QLabel("LOCAL-FIRST  •  LIVE TELEMETRY  •  SIMULATED SUBSYSTEMS ARE NEVER PHYSICAL CONTROLS")
        footer.setObjectName("muted")
        root.addWidget(footer)

    def _append_log(self, line: str) -> None:
        self.log.append(f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] {line}")
        if self.log.document().blockCount() > 80:
            cursor = self.log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def refresh(self) -> None:
        try:
            response = httpx.get(f"{_API_ROOT}/runtime/state", timeout=1.2)
            response.raise_for_status()
            data = response.json()
            telemetry = data.get("telemetry", {})
            status = str(data.get("status", "unknown")).upper()
            self.system_status.setText(f"●  SYSTEM {status}")
            self.system_status.setStyleSheet("color: #ffb35c;" if status in {"WARNING", "CRITICAL"} else "color: #58d9ee;")
            self.node.set_alert(status in {"WARNING", "CRITICAL"})
            self.core_state.setText(f"TELEMETRY LINK / {status}")
            self.cpu_value.setText(f"{telemetry.get('cpu_percent', 0):.0f} %")
            self.ram_value.setText(f"{telemetry.get('memory_percent', 0):.0f} %")
            down = telemetry.get("network_recv_bytes_per_second", 0) / 1024
            up = telemetry.get("network_send_bytes_per_second", 0) / 1024
            self.net_value.setText(f"↓ {down:.1f} KB/s   ↑ {up:.1f} KB/s")
            self.window_value.setText(str(telemetry.get("active_window") or "Desktop / unavailable"))
            self.process_count.setText(f"{telemetry.get('process_count', 0)} processes")
            self.process_list.clear()
            for proc in telemetry.get("top_processes", []):
                mb = proc.get("memory_bytes", 0) / (1024 * 1024)
                self.process_list.addItem(f"{proc.get('name', 'process')}  ·  PID {proc.get('pid')}  ·  {mb:.0f} MB")
            for alert in data.get("alerts", []):
                key = str(alert.get("key", ""))
                if key and key not in self._last_alert_keys:
                    self._append_log(f"{alert.get('severity', 'notice').upper()}: {alert.get('message', '')}")
                    self._last_alert_keys.add(key)
            if not self.log.toPlainText():
                self._append_log("Local telemetry stream established.")
        except Exception as exc:
            self.system_status.setText("●  TELEMETRY OFFLINE")
            self.system_status.setStyleSheet("color: #ff7777;")
            self.core_state.setText("BACKEND LINK UNAVAILABLE")
            if not self.log.toPlainText():
                self._append_log(f"Telemetry connection unavailable: {type(exc).__name__}")

    def send_command(self) -> None:
        prompt = self.command.text().strip()
        if not prompt or (self._worker and self._worker.isRunning()):
            return
        self.command.clear()
        self.reply.setText("Processing command…")
        self._append_log(f"Command received ({len(prompt)} characters).")
        self._worker = _CommandWorker(prompt)
        self._worker.completed.connect(self._command_completed)
        self._worker.failed.connect(self.reply.setText)
        self._worker.start()

    def _command_completed(self, reply: str) -> None:
        self.reply.setText(reply)
        self._append_log("Response received from the configured NOVA model.")
