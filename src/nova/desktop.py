"""NOVA's lightweight Windows desktop client."""

from __future__ import annotations

import json
import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any

import httpx
from nova.config import environment_file, get_settings, user_data_dir
from nova.core.computer.automation import AutomationEngine, AutomationPlanError, execute_plan
from nova.core.tasks.intents import plan_task_intent
from nova.core.computer.intents import application_candidates, plan_computer_intent, plan_multi_step_intent, plan_os_query, plan_system_intent, plan_window_intent, requested_application_name
from nova.desktop_computer import ComputerControlsDialog
from nova.desktop_command_centre import NovaCommandCentre
from nova.core.voice import WakeWordSession
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QAbstractNativeEventFilter, QLockFile
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient, QAction
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QSystemTrayIcon,
    QStyle,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


from nova.core.computer.shell_integration import ShellIntegrationError, notifications_enabled, set_notifications_enabled, set_startup_enabled, startup_enabled, show_windows_toast


_SETTINGS = get_settings()
API_ROOT = os.getenv("NOVA_API_URL", f"http://{_SETTINGS.host}:{_SETTINGS.port}").rstrip("/")


_HTTP_CLIENT = httpx.Client(timeout=httpx.Timeout(150.0, connect=5.0))




class _GlobalHotkeyFilter(QAbstractNativeEventFilter):
    """Bring NOVA forward on Ctrl+Alt+Space without installing a keyboard hook."""

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == 0x0312 and msg.wParam == 0x4E4F:
                    self.callback()
                    return True, 0
            except (TypeError, ValueError, OSError):
                pass
        return False, 0


class ApiWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)
    token = Signal(str)

    def __init__(self, endpoint: str, payload: dict[str, Any] | None = None, *, streaming: bool = False) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.payload = payload
        self.streaming = streaming

    def run(self) -> None:
        try:
            if self.streaming and self.payload is not None:
                with _HTTP_CLIENT.stream("POST", f"{API_ROOT}{self.endpoint}", json=self.payload) as response:
                    response.raise_for_status()
                    metadata: dict[str, Any] = {}
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:].strip())
                        if event.get("type") == "token":
                            self.token.emit(str(event.get("content", "")))
                        elif event.get("type") == "done":
                            metadata = event
                        elif event.get("type") == "error":
                            raise RuntimeError(str(event.get("message", "Streaming failed.")))
                self.completed.emit({"reply": "", "provider": metadata.get("provider", "unknown"), "model": metadata.get("model", "unknown"), "conversation_id": metadata.get("conversation_id"), "memory": metadata.get("memory"), "ttft_ms": metadata.get("ttft_ms"), "total_ms": metadata.get("total_ms")})
                return
            if self.payload is None:
                response = _HTTP_CLIENT.get(f"{API_ROOT}{self.endpoint}")
            else:
                response = _HTTP_CLIENT.post(f"{API_ROOT}{self.endpoint}", json=self.payload)
            response.raise_for_status()
            self.completed.emit(response.json())
        except httpx.ConnectError:
            self.failed.emit("NOVA's backend is offline. Start the API server first.")
        except httpx.TimeoutException:
            self.failed.emit("The request timed out. Check that your local model is running.")
        except httpx.HTTPStatusError as exc:
            detail = "The backend returned an error."
            try:
                detail = str(exc.response.json().get("detail", detail))
            except ValueError:
                pass
            self.failed.emit(detail)
        except Exception as exc:
            self.failed.emit(str(exc))


class VoiceInputWorker(QThread):
    """One-shot, local push-to-talk transcription using Vosk."""

    recognized = Signal(str)
    failed = Signal(str)
    listening = Signal(str)

    def __init__(self, model_path: str) -> None:
        super().__init__()
        self.model_path = Path(model_path).expanduser()
        self._stop_requested = threading.Event()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model

            if not self.model_path.is_dir():
                raise RuntimeError(
                    "Vosk model not found. Download and extract an English Vosk model, "
                    "then set NOVA_VOSK_MODEL_PATH to its folder."
                )

            model = Model(str(self.model_path))
            recognizer = KaldiRecognizer(model, 16000)
            self.listening.emit("Listening locally… speak now.")
            with sd.RawInputStream(
                samplerate=16000,
                blocksize=8000,
                dtype="int16",
                channels=1,
            ) as stream:
                while not self._stop_requested.is_set():
                    audio, overflowed = stream.read(4000)
                    if overflowed:
                        continue
                    if recognizer.AcceptWaveform(bytes(audio)):
                        result = json.loads(recognizer.Result())
                        phrase = str(result.get("text", "")).strip()
                        if phrase:
                            self.recognized.emit(phrase)
                            return

            final_result = json.loads(recognizer.FinalResult())
            phrase = str(final_result.get("text", "")).strip()
            if phrase:
                self.recognized.emit(phrase)
            else:
                self.failed.emit("No speech was recognized. Try again.")
        except Exception as exc:
            self.failed.emit(
                f"Voice input unavailable: {exc}. Check microphone permission and voice setup."
            )


class SpeechOutputWorker(QThread):
    """Interruptible local speech synthesis using the installed Windows voice."""

    failed = Signal(str)
    finished_speaking = Signal()

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text
        self._stop_requested = threading.Event()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        engine = None
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(self.text)
            engine.startLoop(False)
            while not self._stop_requested.is_set() and engine.isBusy():
                engine.iterate()
                time.sleep(0.01)
            if self._stop_requested.is_set():
                engine.stop()
            engine.endLoop()
        except Exception as exc:
            self.failed.emit(f"Speech output unavailable: {exc}")
        finally:
            self.finished_speaking.emit()


class WakeWordWorker(QThread):
    """Own the local microphone session on a worker thread."""

    activated = Signal()
    recognized = Signal(str)
    failed = Signal(str)
    listening = Signal()

    def __init__(self, model_path: str) -> None:
        super().__init__()
        self.model_path = model_path
        self._stop_requested = threading.Event()
        self.session: WakeWordSession | None = None

    def stop(self) -> None:
        self._stop_requested.set()
        if self.session is not None:
            self.session.stop(timeout=2.0)

    def run(self) -> None:
        self.session = WakeWordSession(
            self.model_path,
            on_wake=self.activated.emit,
            on_utterance=self.recognized.emit,
            on_error=self.failed.emit,
        )
        self.session.start()
        self.listening.emit()
        while not self._stop_requested.is_set() and self.session.running:
            self.msleep(100)
        self.session.stop(timeout=2.0)


class NovaOrb(QWidget):
    """Simple animated identity visual; deliberately lightweight for integrated GPUs."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(190, 190)
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(45)

    def advance(self) -> None:
        self.phase = (self.phase + 2) % 360
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = min(self.width(), self.height()) * 0.31
        glow = QRadialGradient(cx, cy, radius * 1.8)
        glow.setColorAt(0.0, QColor(41, 176, 255, 90))
        glow.setColorAt(0.55, QColor(74, 91, 255, 35))
        glow.setColorAt(1.0, QColor(10, 15, 35, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(int(cx - radius * 1.8), int(cy - radius * 1.8),
                            int(radius * 3.6), int(radius * 3.6))

        painter.setBrush(QColor(9, 19, 42))
        painter.setPen(QPen(QColor(75, 190, 255, 210), 2))
        painter.drawEllipse(int(cx - radius), int(cy - radius),
                            int(radius * 2), int(radius * 2))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(104, 220, 255, 190), 2))
        painter.drawArc(int(cx - radius * 1.18), int(cy - radius * 1.18),
                        int(radius * 2.36), int(radius * 2.36),
                        self.phase * 16, 210 * 16)
        painter.setPen(QPen(QColor(119, 115, 255, 170), 2))
        painter.drawArc(int(cx - radius * 1.32), int(cy - radius * 1.32),
                        int(radius * 2.64), int(radius * 2.64),
                        -self.phase * 12, 125 * 16)

        core = QRadialGradient(cx - radius * 0.18, cy - radius * 0.2, radius)
        core.setColorAt(0.0, QColor(185, 245, 255, 230))
        core.setColorAt(0.35, QColor(49, 169, 255, 180))
        core.setColorAt(1.0, QColor(35, 70, 170, 20))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(int(cx - radius * 0.58), int(cy - radius * 0.58),
                            int(radius * 1.16), int(radius * 1.16))


class NovaWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NOVA — Personal AI")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)
        self._quit_requested = False
        self._tray_available = False
        self._hotkey_registered = False
        self._backend_process = None
        self.history: list[dict[str, str]] = []
        self.conversation_id = str(uuid4())
        self.worker: ApiWorker | None = None
        self._last_response_status: str | None = None
        self._stream_buffer = ""
        self.last_response_text = ""
        self.voice_worker: VoiceInputWorker | None = None
        self.speech_worker: SpeechOutputWorker | None = None
        self._skip_tool_planning = False
        self._pending_tool_message = ""
        self._pending_tool_calls: list[dict[str, Any]] = []
        self.tool_worker: ApiWorker | None = None
        self.wake_session = None
        self.wake_thread = None
        self._stream_flush_timer = QTimer(self)
        self._stream_flush_timer.setInterval(40)
        self._stream_flush_timer.timeout.connect(self._flush_stream_tokens)
        self._build_ui()
        self._setup_windows_shell()
        self._ensure_backend_process()
        QTimer.singleShot(1500, self._check_status)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._check_status)
        self.status_timer.start(15000)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 26, 22, 22)
        side.setSpacing(16)

        brand = QLabel("N O V A")
        brand.setObjectName("brand")
        side.addWidget(brand)
        tagline = QLabel("PERSONAL INTELLIGENCE")
        tagline.setObjectName("eyebrow")
        side.addWidget(tagline)
        side.addSpacing(26)

        new_chat = QPushButton("+   New conversation")
        new_chat.setObjectName("newChat")
        new_chat.clicked.connect(self._new_chat)
        side.addWidget(new_chat)

        memory_button = QPushButton("◈   Manage memories")
        memory_button.setObjectName("newChat")
        memory_button.clicked.connect(self._open_memory_manager)
        side.addWidget(memory_button)

        history_button = QPushButton("◷   Conversation history")
        history_button.setObjectName("newChat")
        history_button.clicked.connect(self._open_history_manager)
        side.addWidget(history_button)

        computer_button = QPushButton("⌘   Computer controls")
        computer_button.setObjectName("newChat")
        computer_button.clicked.connect(self._open_computer_controls)
        side.addWidget(computer_button)

        tasks_button = QPushButton("◷   Scheduled tasks")
        tasks_button.setObjectName("newChat")
        tasks_button.clicked.connect(self._open_task_manager)
        side.addWidget(tasks_button)

        command_centre_button = QPushButton("◎   Command centre")
        command_centre_button.setObjectName("newChat")
        command_centre_button.clicked.connect(self._open_command_centre)
        side.addWidget(command_centre_button)

        nav_label = QLabel("WORKSPACE")
        nav_label.setObjectName("eyebrow")
        side.addSpacing(22)
        side.addWidget(nav_label)
        nav = QLabel("◉   Assistant\n\n◷   Conversation history\n\n⌘   Capabilities")
        nav.setObjectName("navText")
        side.addWidget(nav)
        side.addStretch()

        self.backend_label = QLabel("●  BACKEND CHECKING")
        self.backend_label.setObjectName("statusPill")
        side.addWidget(self.backend_label)
        footer = QLabel("LOCAL-FIRST  •  OPEN SOURCE")
        footer.setObjectName("footer")
        side.addWidget(footer)
        outer.addWidget(sidebar)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(34, 24, 34, 24)
        main_layout.setSpacing(18)

        header = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading = QLabel("Assistant")
        heading.setObjectName("pageTitle")
        subheading = QLabel("Your personal intelligence, running on your machine.")
        subheading.setObjectName("muted")
        heading_box.addWidget(heading)
        heading_box.addWidget(subheading)
        header.addLayout(heading_box)
        header.addStretch()
        self.model_badge = QLabel("MODEL  •  CONNECTING")
        self.model_badge.setObjectName("modelBadge")
        header.addWidget(self.model_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        main_layout.addLayout(header)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 12, 34, 12)
        hero_layout.setSpacing(24)
        self.orb = NovaOrb()
        hero_layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)
        hero_copy = QVBoxLayout()
        hero_copy.addStretch()
        hero_title = QLabel("Always within reach.")
        hero_title.setObjectName("heroTitle")
        hero_text = QLabel("Ask a question, explore an idea, or get help with your day.\nNOVA is ready when you are.")
        hero_text.setObjectName("muted")
        hero_text.setWordWrap(True)
        hero_copy.addWidget(hero_title)
        hero_copy.addWidget(hero_text)
        hero_copy.addSpacing(8)
        self.connection_label = QLabel("Waiting for local model status…")
        self.connection_label.setObjectName("connection")
        hero_copy.addWidget(self.connection_label)
        hero_copy.addStretch()
        hero_layout.addLayout(hero_copy, 1)
        main_layout.addWidget(hero)

        chat_heading = QLabel("CONVERSATION")
        chat_heading.setObjectName("eyebrow")
        main_layout.addWidget(chat_heading)

        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setObjectName("chatArea")
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()
        self.chat_area.setWidget(self.chat_content)
        main_layout.addWidget(self.chat_area, 1)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(14, 10, 10, 10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message NOVA…")
        self.input.returnPressed.connect(self._send_message)
        self.input.setObjectName("messageInput")
        composer_layout.addWidget(self.input, 1)
        self.send_button = QPushButton("Send  ↗")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._send_message)
        composer_layout.addWidget(self.send_button)
        self.voice_button = QPushButton("🎙  Talk")
        self.voice_button.setObjectName("newChat")
        self.voice_button.setToolTip("Start local push-to-talk transcription")
        self.voice_button.clicked.connect(self._toggle_voice_input)
        composer_layout.addWidget(self.voice_button)
        self.wake_button = QPushButton("◉  Wake word off")
        self.wake_button.setObjectName("newChat")
        self.wake_button.setToolTip("Enable or disable local 'Hey NOVA' microphone standby")
        self.wake_button.clicked.connect(self._toggle_wake_word)
        composer_layout.addWidget(self.wake_button)
        self.speak_button = QPushButton("🔊  Read last reply")
        self.speak_button.setObjectName("newChat")
        self.speak_button.setToolTip("Read NOVA's latest response using a local Windows voice")
        self.speak_button.clicked.connect(self._speak_last_response)
        composer_layout.addWidget(self.speak_button)
        main_layout.addWidget(composer)

        hint = QLabel("Enter to send  ·  Conversations and approved memories are stored locally on this device.")
        hint.setObjectName("hint")
        main_layout.addWidget(hint)
        outer.addWidget(main, 1)
        self.setCentralWidget(root)

        self.setStyleSheet("""
            QWidget#root { background: #080d18; color: #e8f1ff; font-family: 'Segoe UI'; }
            QFrame#sidebar { background: #0b1221; border-right: 1px solid #1b2b43; }
            QLabel#brand { color: #eaf7ff; font-size: 23px; font-weight: 700; letter-spacing: 3px; }
            QLabel#eyebrow { color: #7188a8; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
            QLabel#footer, QLabel#hint { color: #647894; font-size: 10px; }
            QLabel#navText { color: #9aacc5; font-size: 13px; line-height: 1.5; }
            QPushButton#newChat { background: #14243a; border: 1px solid #29415f; border-radius: 9px; padding: 12px; color: #d9efff; text-align: left; }
            QPushButton#newChat:hover { background: #1b3452; }
            QLabel#pageTitle { font-size: 25px; font-weight: 650; color: #f0f6ff; }
            QLabel#muted { color: #8ea2bd; font-size: 12px; }
            QLabel#modelBadge, QLabel#statusPill { color: #8de5ff; background: #10263a; border: 1px solid #214b68; border-radius: 10px; padding: 8px 11px; font-size: 10px; font-weight: 700; }
            QFrame#hero { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #101d32, stop:1 #11172c); border: 1px solid #203653; border-radius: 16px; }
            QLabel#heroTitle { color: #eff8ff; font-size: 22px; font-weight: 600; }
            QLabel#connection { color: #79dfff; font-size: 11px; }
            QScrollArea#chatArea { border: none; background: transparent; }
            QFrame#messageUser { background: #142b45; border: 1px solid #244766; border-radius: 12px; }
            QFrame#messageAssistant { background: #101a2b; border: 1px solid #1e3049; border-radius: 12px; }
            QLabel#messageRole { color: #7fdcff; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QLabel#messageText { color: #e4edf9; font-size: 13px; }
            QFrame#composer { background: #0e1929; border: 1px solid #263c58; border-radius: 12px; }
            QLineEdit#messageInput { background: transparent; border: none; color: #f0f6ff; padding: 8px; font-size: 13px; }
            QPushButton#sendButton { background: #167bb5; border: none; border-radius: 8px; color: white; padding: 10px 18px; font-weight: 650; }
            QPushButton#sendButton:hover { background: #2195d4; }
            QPushButton:disabled { background: #26384c; color: #7b8ca1; }
        """)

    def _open_command_centre(self) -> None:
        """Open the full-screen telemetry and command overlay."""
        dialog = NovaCommandCentre(self)
        dialog.showFullScreen()
        dialog.exec()

    def _add_message(self, role: str, content: str) -> QLabel:
        card = QFrame()
        card.setObjectName("messageUser" if role == "YOU" else "messageAssistant")
        card.setMaximumWidth(760)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        label = QLabel(role)
        label.setObjectName("messageRole")
        body = QLabel(content)
        body.setObjectName("messageText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        layout.addWidget(body)
        row = QHBoxLayout()
        if role == "YOU":
            row.addStretch()
        row.addWidget(card, 0 if role == "YOU" else 1)
        if role != "YOU":
            row.addStretch()
        self.chat_layout.insertLayout(self.chat_layout.count() - 1, row)
        QTimer.singleShot(30, lambda: self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()
        ))
        return body

    def _handle_task_intent(self, message: str) -> bool:
        """Handle bounded scheduled-task commands directly from chat."""
        intent = plan_task_intent(message)
        if intent is None:
            return False

        self.input.clear()
        self._add_message("YOU", message)
        self.history.append({"role": "user", "content": message})

        def respond(reply: str) -> None:
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText(reply)

        kind = intent["kind"]
        navigation = {
            "open_computer": (self._open_computer_controls, "Opened Computer Controls."),
            "open_memory": (self._open_memory_manager, "Opened the memory manager."),
            "open_history": (self._open_history_manager, "Opened conversation history."),
        }
        if kind in navigation:
            callback, message_text = navigation[kind]
            callback()
            respond(message_text)
            return True

        if kind == "open":
            respond("Opening your scheduled tasks.")
            self._open_task_manager()
            return True

        if kind == "clarify" or kind == "unsupported":
            respond(str(intent.get("message", "I need a little more information to schedule that.")))
            return True

        try:
            response = _HTTP_CLIENT.get(f"{API_ROOT}/tasks")
            response.raise_for_status()
            tasks = response.json().get("tasks", [])
        except Exception as exc:
            respond(f"I couldn't reach the scheduled-task service: {exc}")
            return True

        if kind == "list":
            if not tasks:
                respond("You don't have any scheduled tasks yet. Try: 'schedule a storage report tomorrow at 10 AM'.")
                return True
            lines = []
            for task in tasks[:30]:
                lines.append(
                    f"• {task.get('title', 'Untitled')} — {task.get('status', 'unknown').replace('_', ' ')}"
                    f" — next run: {task.get('schedule_at', 'not scheduled')} ({task.get('recurrence', 'once')})"
                )
            respond("Here are your scheduled tasks:\n" + "\n".join(lines))
            return True

        if kind == "schedule":
            title = str(intent["title"])
            action_id = str(intent["action_id"])
            schedule_at = str(intent["schedule_at"])
            recurrence = str(intent["recurrence"])
            details = (
                f"Create this scheduled task?\n\n{title}\n"
                f"Action: {action_id}\nRun at: {schedule_at}\n"
                f"Repeat: {recurrence}\n\nIt will be created as pending approval."
            )
            answer = QMessageBox.question(
                self, "Confirm scheduled task", details,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                respond("I didn't create the scheduled task.")
                return True
            try:
                created = _HTTP_CLIENT.post(f"{API_ROOT}/tasks", json={
                    "title": title, "action_id": action_id, "parameters": {},
                    "schedule_at": schedule_at, "recurrence": recurrence,
                })
                created.raise_for_status()
                task = created.json()["task"]
            except Exception as exc:
                respond(f"I couldn't create that task: {exc}")
                return True

            approval = QMessageBox.question(
                self, "Approve scheduled task?",
                f"Approve this exact task to run automatically?\n\n"
                f"{task['title']}\nNext run: {task['schedule_at']}\n"
                f"Repeat: {task['recurrence']}\n\n"
                "The action is read-only and limited to NOVA's registered report handlers.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if approval == QMessageBox.StandardButton.Yes:
                try:
                    approved = _HTTP_CLIENT.post(f"{API_ROOT}/tasks/{task['id']}/approve")
                    approved.raise_for_status()
                    respond(f"Scheduled and approved: {title}. It will run at {schedule_at} ({recurrence}).")
                except Exception as exc:
                    respond(f"The task was created but I couldn't approve it: {exc}. You can approve it in Scheduled tasks.")
            else:
                respond(f"Created '{title}' as pending approval. It will not run until you approve it in Scheduled tasks.")
            return True

        if kind in {"pause", "cancel"}:
            target_name = str(intent["target"]).casefold()
            eligible = [
                task for task in tasks
                if target_name in str(task.get("title", "")).casefold()
                and task.get("status") in {"pending_approval", "scheduled", "paused"}
            ]
            if not eligible:
                respond(f"I couldn't find an active task matching '{intent['target']}'. Say 'show my tasks' to see the exact task names.")
                return True
            if len(eligible) > 1:
                labels = [f"{task['title']} — {task['status']} — {task['schedule_at']}" for task in eligible]
                selected, accepted = QInputDialog.getItem(
                    self, "Choose scheduled task", "Which task do you want to " + kind + "?",
                    labels, 0, False,
                )
                if not accepted:
                    respond("I left your tasks unchanged.")
                    return True
                task = eligible[labels.index(selected)]
            else:
                task = eligible[0]
            answer = QMessageBox.question(
                self, f"Confirm {kind}",
                f"{kind.title()} this task?\n\n{task['title']}\n"
                f"Current status: {task['status']}\nNext run: {task['schedule_at']}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                respond("I left your task unchanged.")
                return True
            try:
                changed = _HTTP_CLIENT.post(f"{API_ROOT}/tasks/{task['id']}/{kind}")
                changed.raise_for_status()
                respond(f"Task '{task['title']}' is now {changed.json()['task']['status']}.")
            except Exception as exc:
                respond(f"I couldn't {kind} that task: {exc}")
            return True

        return False

    def _send_message(self) -> None:
        message = self.input.text().strip()
        if not message or (self.worker and self.worker.isRunning()):
            return

        if self._handle_task_intent(message):
            return

        # A chained request is planned completely before any step runs.
        multi_plan = plan_multi_step_intent(message)
        if multi_plan:
            engine = AutomationEngine()
            try:
                engine.validate_plan(multi_plan)
            except AutomationPlanError as exc:
                self._add_message("NOVA", f"I couldn't safely validate that task: {exc}")
                return
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})

            def run_step(step: dict[str, Any], index: int) -> dict[str, Any] | None:
                dialog = ComputerControlsDialog(self)
                try:
                    if step["kind"] == "system":
                        return dialog.execute_system_action(
                            str(step["endpoint"]), dict(step["payload"]),
                            str(step["description"]),
                        )
                    if step["kind"] == "window":
                        response = _HTTP_CLIENT.get(f"{API_ROOT}/computer/windows?limit=200")
                        response.raise_for_status()
                        target_name = str(step["target"]).casefold()
                        candidates = [
                            item for item in response.json().get("windows", [])
                            if target_name in str(item.get("title", "")).casefold()
                        ]
                        if len(candidates) > 1:
                            labels = [f"{item.get('title')} · PID {item.get('pid')}" for item in candidates]
                            selected, accepted = QInputDialog.getItem(
                                self, "Choose a window", f"Step {index}: choose the matching window:",
                                labels, 0, False,
                            )
                            target = candidates[labels.index(selected)] if accepted else None
                        else:
                            target = candidates[0] if candidates else None
                        if target:
                            return dialog.execute_window_target(target, str(step["action"]))
                    return None
                finally:
                    dialog.close()

            results = execute_plan(engine, multi_plan, run_step)
            outcomes = []
            for result in results:
                status = result["status"]
                if status == "completed":
                    message_text = result.get("result", {}).get("message", "completed")
                    outcomes.append(f"Step {result['step']}: {message_text}")
                elif status == "failed":
                    outcomes.append(f"Step {result['step']}: failed — {result.get('message', 'unknown error')}")
                else:
                    outcomes.append(f"Step {result['step']}: cancelled or target unavailable.")
            reply = "Multi-step task finished:\n" + "\n".join(outcomes)
            if results and results[-1]["status"] != "completed" and len(results) < len(multi_plan):
                reply += f"\nStopped after {results[-1]['step']} of {len(multi_plan)} steps. Remaining steps were not run."
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText("Multi-step task completed with per-step approval.")
            return

        # Resolve direct launch requests against the live Windows application catalogue.
        requested_target = requested_application_name(message)
        requested_app = None
        discovered_apps = []
        if requested_target:
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/computer/capabilities")
                response.raise_for_status()
                discovered_apps = response.json().get("applications", [])
                candidates = application_candidates(message, discovered_apps)
                if len(candidates) == 1:
                    requested_app = candidates[0]
                elif len(candidates) > 1:
                    labels = [item.get("name", "Unnamed application") for item in candidates]
                    selected_name, accepted = QInputDialog.getItem(
                        self,
                        "Choose application",
                        f"More than one installed app matches '{requested_target}':",
                        labels,
                        0,
                        False,
                    )
                    if accepted:
                        requested_app = next(
                            (item for item in candidates if item.get("name") == selected_name),
                            None,
                        )
                    else:
                        return
            except Exception:
                discovered_apps = []

        if requested_app:
            app_name = requested_app["name"]
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})
            dialog = ComputerControlsDialog(self)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            result = dialog.execute(
                "open_application",
                {"app_id": requested_app["app_id"]},
                f"open {app_name}",
            )
            reply = (
                f"Windows accepted the launch request for {app_name}."
                if result
                else f"I didn't open {app_name}. The action was cancelled or Windows blocked it."
            )
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText(reply)
            dialog.close()
            return

        os_query = plan_os_query(message)
        if os_query:
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})
            try:
                response = httpx.get(f"{API_ROOT}{os_query['endpoint']}", timeout=15.0)
                response.raise_for_status()
                payload = response.json()
                if os_query["kind"] == "processes":
                    processes = payload.get("processes", [])
                    lines = [f"{item['name']} (PID {item['pid']}, {item['status']})" for item in processes[:30]]
                    reply = f"I can see {len(processes)} running processes.\n" + ("\n".join(lines) if lines else "No process records were returned.")
                    if len(processes) > 30:
                        reply += f"\nAnd {len(processes) - 30} more."
                elif os_query["kind"] == "windows":
                    foreground = payload.get("foreground")
                    windows = payload.get("windows", [])
                    lines = [f"{item['title']} (PID {item['pid']})" for item in windows[:30]]
                    reply = ("Foreground window: " + foreground["title"] + "\n" if foreground and foreground.get("title") else "")
                    reply += "Visible windows:\n" + ("\n".join(lines) if lines else "No visible titled windows were found.")
                else:
                    reply = (
                        f"{payload.get('platform')}\n"
                        f"Processor: {payload.get('processor') or 'Not reported'}\n"
                        f"Logical CPUs: {payload.get('cpu_count_logical', 'Not available')}\n"
                        f"Memory: {round(payload.get('memory_total_bytes', 0) / (1024**3), 1) if payload.get('memory_total_bytes') else 'Not available'} GB"
                    )
            except Exception as exc:
                reply = f"I couldn't read that Windows information: {exc}"
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText("Read-only Windows information retrieved.")
            return

        # Route narrow system-control and Windows Search requests through approval.
        system_plan = plan_system_intent(message)
        if system_plan:
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})
            dialog = ComputerControlsDialog(self)
            result = dialog.execute_system_action(
                str(system_plan["endpoint"]),
                dict(system_plan["payload"]),
                str(system_plan["description"]),
            )
            dialog.close()
            reply = (
                result.get("message", "Windows action completed.")
                if result else "I didn't change Windows. The action was cancelled or blocked."
            )
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText(reply)
            return

        # Resolve conversational window commands against live visible-window metadata.
        window_plan = plan_window_intent(message)
        if window_plan:
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/computer/windows?limit=200")
                response.raise_for_status()
                windows = response.json().get("windows", [])
                target_name = window_plan["target"].casefold()
                candidates = [
                    item for item in windows
                    if target_name in str(item.get("title", "")).casefold()
                ]
                if len(candidates) > 1:
                    labels = [f"{item.get('title')} · PID {item.get('pid')}" for item in candidates]
                    selected, accepted = QInputDialog.getItem(
                        self, "Choose a window", f"More than one window matches '{window_plan['target']}':",
                        labels, 0, False,
                    )
                    target = candidates[labels.index(selected)] if accepted else None
                else:
                    target = candidates[0] if candidates else None
                if target is None:
                    reply = f"I couldn't find an open visible window matching '{window_plan['target']}'."
                else:
                    dialog = ComputerControlsDialog(self)
                    result = dialog.execute_window_target(target, window_plan["action"])
                    dialog.close()
                    reply = (
                        result.get("message", "Window action requested.")
                        if result else "I didn't change that window. The action was cancelled or blocked."
                    )
            except Exception as exc:
                reply = f"I couldn't complete that window action: {exc}"
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText(reply)
            return

        # Route recognized local discovery/file requests through the same approval surface.
        # Searches are read-only, while opening/reading still require a per-action Yes/No.
        computer_plan = plan_computer_intent(message)
        if computer_plan:
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})
            dialog = ComputerControlsDialog(self)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            result = dialog.execute(
                str(computer_plan["action"]),
                dict(computer_plan["parameters"]),
                str(computer_plan["description"]),
            )
            if result is None:
                reply = "I didn't perform that computer action. It was cancelled or blocked."
            elif "matches" in result:
                found = result["matches"]
                reply = (f"I found {len(found)} matching item(s). The results are shown in Computer Controls."
                         if found else "I couldn't find any matching items in the accessible locations.")
                if result.get("truncated"):
                    reply += " The result list was capped; narrow the search to get more specific results."
            elif "entries" in result:
                reply = f"I listed {len(result['entries'])} items. They're shown in Computer Controls."
            elif "content" in result:
                reply = f"I read {Path(str(result.get('path', 'file'))).name}. Its contents are displayed locally in Computer Controls and were not sent to the AI model."
            else:
                reply = str(result.get("message", "The action completed."))
            self._add_message("NOVA", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.connection_label.setText(reply)
            return

        # Ask the configured model whether registered tools are needed.
        # The proposal is validated server-side and is never executed without approval.
        if not self._skip_tool_planning:
            self.input.clear()
            self._add_message("YOU", message)
            self.history.append({"role": "user", "content": message})
            self._pending_tool_message = message
            self.send_button.setEnabled(False)
            self.send_button.setText("Planning…")
            self.connection_label.setText("NOVA is considering its registered capabilities…")
            self.tool_worker = ApiWorker("/runtime/tools/plan", {"message": message})
            self.tool_worker.completed.connect(self._tool_plan_completed)
            self.tool_worker.failed.connect(self._tool_plan_failed)
            self.tool_worker.start()
            return

        self._skip_tool_planning = False
        self._start_chat_request(message)

    def _tool_plan_failed(self, message: str) -> None:
        self.connection_label.setText("Tool planning unavailable; continuing with ordinary chat.")
        self._start_chat_request(self._pending_tool_message, include_latest_user=False)

    def _tool_plan_finished(self) -> None:
        self.send_button.setEnabled(True)
        self.send_button.setText("Send  ↗")

    def _tool_plan_completed(self, data: dict) -> None:
        proposal = data.get("proposal") or {}
        calls = proposal.get("tool_calls") or []
        if not calls:
            self._start_chat_request(self._pending_tool_message)
            return
        self._pending_tool_calls = calls
        descriptions = "\\n".join(
            f"{index}. {call.get('name')} — {json.dumps(call.get('arguments', {}), ensure_ascii=False)}"
            for index, call in enumerate(calls, 1)
        )
        reason = str(proposal.get("reason", "")).strip()
        prompt = "NOVA proposes the following registered tool actions:\\n\\n" + descriptions
        if reason:
            prompt += "\\n\\nReason: " + reason
        prompt += "\\n\\nThese actions will only run if you approve."
        answer = QMessageBox.question(
            self, "Approve NOVA tool actions", prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._add_message("NOVA", "Understood. I haven't executed those actions.")
            self.history.append({"role": "assistant", "content": "Understood. I haven't executed those actions."})
            self.connection_label.setText("Tool actions declined.")
            self.send_button.setEnabled(True)
            self.send_button.setText("Send  ↗")
            return
        self.send_button.setEnabled(False)
        self.send_button.setText("Executing…")
        self.connection_label.setText("Executing approved registered actions…")
        self.tool_worker = ApiWorker("/runtime/tools/execute", {"calls": calls, "approved": True})
        self.tool_worker.completed.connect(self._tool_execute_completed)
        self.tool_worker.failed.connect(self._tool_execute_failed)
        self.tool_worker.start()

    def _tool_execute_failed(self, message: str) -> None:
        self._request_failed(message)
        self.send_button.setEnabled(True)
        self.send_button.setText("Send  ↗")

    def _tool_execute_completed(self, data: dict) -> None:
        results = data.get("results", [])
        result_text = json.dumps(results, ensure_ascii=False, indent=2)
        self._start_chat_request(
            "The user approved the proposed registered tools. Here are their actual results:\\n"
            + result_text
            + "\\nRespond to the user's original request using these results. Clearly distinguish simulation results from real system actions.",
            include_latest_user=True,
        )

    def _start_chat_request(self, message: str, *, include_latest_user: bool = False) -> None:
        self.send_button.setEnabled(False)
        self.send_button.setText("Thinking…")
        self.connection_label.setText("NOVA is generating…")
        self.streaming_body = self._add_message("NOVA", "")
        self.worker = ApiWorker(
            "/chat/stream",
            {"message": message, "history": (self.history if include_latest_user else self.history[:-1])[-20:], "conversation_id": self.conversation_id},
            streaming=True,
        )
        self.worker.token.connect(self._append_stream_token)
        self.worker.completed.connect(self._chat_completed)
        self.worker.failed.connect(self._request_failed)
        self.worker.finished.connect(self._request_finished)
        self.worker.start()

    def _append_stream_token(self, token: str) -> None:
        self._stream_buffer += token
        if not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream_tokens(self) -> None:
        self._stream_flush_timer.stop()
        if not self._stream_buffer:
            return
        pending = self._stream_buffer
        self._stream_buffer = ""
        self.streaming_body.setText(self.streaming_body.text() + pending)
        QTimer.singleShot(
            0,
            lambda: self.chat_area.verticalScrollBar().setValue(
                self.chat_area.verticalScrollBar().maximum()
            ),
        )

    def _chat_completed(self, data: dict) -> None:
        self._flush_stream_tokens()
        reply = self.streaming_body.text()
        self.conversation_id = str(data.get("conversation_id") or self.conversation_id)
        if not reply:
            reply = str(data.get("reply", "The model returned an empty response."))
            self.streaming_body.setText(reply)
        self.history.append({"role": "assistant", "content": reply})
        self.last_response_text = reply
        if self.isHidden() and notifications_enabled():
            try:
                show_windows_toast("NOVA has replied", reply[:350])
            except ShellIntegrationError:
                pass
        self.model_badge.setText(f"MODEL  •  {data.get('model', 'CONNECTED')}")
        ttft, total = data.get("ttft_ms"), data.get("total_ms")
        memory = data.get("memory")
        memory_note = ""
        if memory and memory.get("status") == "approved":
            memory_note = " · Memory saved locally"
        elif memory and memory.get("status") == "pending":
            memory_note = " · Memory awaiting your approval"
        if ttft is not None and total is not None:
            self._last_response_status = f"First token: {ttft} ms · Total: {total} ms · {data.get('provider', 'provider')}{memory_note}"
        else:
            self._last_response_status = f"Response generated by {data.get('provider', 'configured provider')}."
        self.connection_label.setText(self._last_response_status)

    def _request_failed(self, message: str) -> None:
        if hasattr(self, "streaming_body"):
            self._flush_stream_tokens()
        if hasattr(self, "streaming_body") and not self.streaming_body.text():
            self.streaming_body.setText(message)
        else:
            self._add_message("SYSTEM", message)
        self.connection_label.setText(message)

    def _request_finished(self) -> None:
        if hasattr(self, "streaming_body"):
            self._flush_stream_tokens()
        self.send_button.setEnabled(True)
        self.send_button.setText("Send  ↗")
        self.input.setFocus()

    def _toggle_voice_input(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.stop()
            self.voice_button.setText("🎙  Talk")
            self.connection_label.setText("Stopping microphone…")
            return

        model_path = get_settings().vosk_model_path.strip()
        if not model_path:
            QMessageBox.information(
                self,
                "Set up local voice input",
                "Download and extract a Vosk English model, then set "
                "NOVA_VOSK_MODEL_PATH to that folder. See docs/VOICE_SETUP.md.",
            )
            return

        self.voice_worker = VoiceInputWorker(model_path)
        self.voice_worker.listening.connect(self.connection_label.setText)
        self.voice_worker.recognized.connect(self._voice_recognized)
        self.voice_worker.failed.connect(self._voice_failed)
        self.voice_worker.finished.connect(lambda: self.voice_button.setText("🎙  Talk"))
        self.voice_button.setText("■  Stop listening")
        self.voice_worker.start()

    def _voice_recognized(self, phrase: str) -> None:
        self.input.setText(phrase)
        self.connection_label.setText("Voice transcribed locally. Sending to NOVA…")
        self._send_message()

    def _voice_failed(self, message: str) -> None:
        self.connection_label.setText(message)
        QMessageBox.warning(self, "Voice input", message)

    def _toggle_wake_word(self) -> None:
        if self.wake_thread and self.wake_thread.isRunning():
            self.wake_thread.stop()
            self.wake_button.setText("◉  Wake word off")
            self.connection_label.setText("Stopping local wake-word listener…")
            return
        model_path = get_settings().vosk_model_path.strip()
        if not model_path:
            QMessageBox.information(
                self, "Set up local voice",
                "Set NOVA_VOSK_MODEL_PATH to your extracted Vosk model folder first.",
            )
            return
        self.wake_thread = WakeWordWorker(model_path)
        self.wake_thread.activated.connect(self._wake_word_activated)
        self.wake_thread.recognized.connect(self._wake_word_recognized)
        self.wake_thread.failed.connect(self._voice_failed)
        self.wake_thread.listening.connect(
            lambda: self.connection_label.setText("Wake-word standby active. Microphone is listening locally.")
        )
        self.wake_thread.finished.connect(lambda: self.wake_button.setText("◉  Wake word off"))
        self.wake_button.setText("■  Wake word on")
        self.wake_thread.start()

    def _wake_word_activated(self) -> None:
        self._stop_speech_output()
        self.connection_label.setText("Wake phrase detected. Listening for your command…")

    def _wake_word_recognized(self, phrase: str) -> None:
        self.input.setText(phrase)
        self.connection_label.setText("Command recognized locally. Sending to NOVA…")
        self._send_message()

    def _stop_speech_output(self) -> None:
        if self.speech_worker and self.speech_worker.isRunning():
            self.speech_worker.stop()

    def _speak_last_response(self) -> None:
        if not self.last_response_text.strip():
            QMessageBox.information(self, "Nothing to read", "NOVA has not produced a response yet.")
            return
        if self.speech_worker and self.speech_worker.isRunning():
            self._stop_speech_output()
            self.speak_button.setText("🔊  Read last reply")
            return
        self.speech_worker = SpeechOutputWorker(self.last_response_text)
        self.speech_worker.failed.connect(self.connection_label.setText)
        self.speech_worker.start()

    def _check_status(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.worker = ApiWorker("/system/ai")
        self.worker.completed.connect(self._status_completed)
        self.worker.failed.connect(self._status_failed)
        self.worker.start()

    def _status_completed(self, data: dict) -> None:
        provider = str(data.get("provider", "unknown"))
        model = str(data.get("model", "unknown"))
        self.backend_label.setText("●  BACKEND ONLINE")
        self.model_badge.setText(f"MODEL  •  {model}")
        if self._last_response_status is None:
            self.connection_label.setText(
                f"{'Model configured' if data.get('configured') else 'Setup mode'} · {provider}"
            )

    def _status_failed(self, message: str) -> None:
        self.backend_label.setText("●  BACKEND OFFLINE")
        self.model_badge.setText("MODEL  •  DISCONNECTED")
        self.connection_label.setText(message)



    def _ensure_backend_process(self) -> None:
        """Start a private loopback backend only when one is not already healthy."""
        try:
            response = _HTTP_CLIENT.get(f"{API_ROOT}/health", timeout=0.6)
            if response.is_success:
                return
        except Exception:
            pass
        settings = get_settings()
        if settings.host not in {"127.0.0.1", "localhost"}:
            self.connection_label.setText("Backend auto-start disabled: NOVA must bind to loopback.")
            return
        if API_ROOT not in {
            f"http://127.0.0.1:{settings.port}",
            f"http://localhost:{settings.port}",
        }:
            self.connection_label.setText("Backend auto-start skipped because NOVA_API_URL points to a different server.")
            return
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--nova-backend"]
            project_root = Path(sys.executable).resolve().parent
        else:
            command = [sys.executable, "-m", "nova.service"]
            project_root = Path(__file__).resolve().parents[2]
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            child_environment = os.environ.copy()
            try:
                import psutil
                child_environment["NOVA_PARENT_PID"] = str(os.getpid())
                child_environment["NOVA_PARENT_CREATE_TIME"] = str(psutil.Process().create_time())
            except Exception:
                child_environment.pop("NOVA_PARENT_PID", None)
                child_environment.pop("NOVA_PARENT_CREATE_TIME", None)
            self._backend_process = subprocess.Popen(
                command,
                cwd=str(project_root),
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            self.connection_label.setText("Starting NOVA's local backend…")
        except Exception as exc:
            self._backend_process = None
            self.connection_label.setText(f"Could not start NOVA's backend automatically: {exc}")

    def _stop_owned_backend(self) -> None:
        process = self._backend_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except OSError:
                pass
        self._backend_process = None

    def _setup_windows_shell(self) -> None:
        if os.name != "nt":
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("NOVA — Personal AI")
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        show_action = QAction("Open NOVA", self)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        controls_action = QAction("Computer controls", self)
        controls_action.triggered.connect(self._open_computer_controls)
        menu.addAction(controls_action)
        settings_action = QAction("Open NOVA settings", self)
        settings_action.triggered.connect(self._open_user_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        self.startup_action = QAction("Start NOVA with Windows", self)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(startup_enabled())
        self.startup_action.triggered.connect(self._toggle_startup)
        menu.addAction(self.startup_action)
        self.notifications_action = QAction("Enable NOVA notifications", self)
        self.notifications_action.setCheckable(True)
        self.notifications_action.setChecked(notifications_enabled())
        self.notifications_action.triggered.connect(self._toggle_notifications)
        menu.addAction(self.notifications_action)
        notify_action = QAction("Send test notification", self)
        notify_action.triggered.connect(self._test_notification)
        menu.addAction(notify_action)
        menu.addSeparator()
        quit_action = QAction("Quit NOVA", self)
        quit_action.triggered.connect(self._quit_nova)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._tray_available = self.tray.isVisible()

        self._hotkey_filter = _GlobalHotkeyFilter(self._show_from_tray)
        app = QApplication.instance()
        if app:
            app.installNativeEventFilter(self._hotkey_filter)
        try:
            import ctypes
            self._hotkey_registered = bool(ctypes.windll.user32.RegisterHotKey(None, 0x4E4F, 0x0001 | 0x0002, 0x20))
        except Exception:
            self._hotkey_registered = False
        if self._hotkey_registered:
            self.tray.setToolTip("NOVA — Ctrl+Alt+Space to open")

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def _open_user_settings(self) -> None:
        path = environment_file()
        if not path.exists():
            QMessageBox.information(self, "NOVA settings", f"No settings file exists yet. Create one at:\n{path}")
            return
        try:
            os.startfile(str(path))
        except OSError as exc:
            QMessageBox.warning(self, "Could not open settings", str(exc))

    def _toggle_startup(self, checked: bool) -> None:
        try:
            enabled = set_startup_enabled(checked)
            self.startup_action.setChecked(enabled)
            self.tray.showMessage("NOVA startup", "NOVA will start when you sign in." if enabled else "NOVA was removed from Windows startup.")
        except ShellIntegrationError as exc:
            self.startup_action.setChecked(startup_enabled())
            QMessageBox.warning(self, "Startup integration unavailable", str(exc))

    def _toggle_notifications(self, checked: bool) -> None:
        try:
            enabled = set_notifications_enabled(checked)
            self.notifications_action.setChecked(enabled)
            if enabled:
                self.tray.showMessage("NOVA notifications", "NOVA reply notifications are enabled.")
        except ShellIntegrationError as exc:
            self.notifications_action.setChecked(notifications_enabled())
            QMessageBox.warning(self, "Could not save notification preference", str(exc))

    def _test_notification(self) -> None:
        try:
            show_windows_toast("NOVA notifications are working", "Windows native notifications are connected.")
        except ShellIntegrationError as exc:
            QMessageBox.warning(self, "Notifications unavailable", str(exc))

    def _quit_nova(self) -> None:
        self._quit_requested = True
        self._stop_owned_backend()
        if self._hotkey_registered:
            try:
                import ctypes
                ctypes.windll.user32.UnregisterHotKey(None, 0x4E4F)
            except Exception:
                pass
            self._hotkey_registered = False
        if hasattr(self, "tray"):
            self.tray.hide()
        app = QApplication.instance()
        if app:
            app.quit()

    def closeEvent(self, event) -> None:
        if self._quit_requested or not self._tray_available:
            if self.wake_thread and self.wake_thread.isRunning():
                self.wake_thread.stop()
            self._stop_speech_output()
            self._stop_owned_backend()
            if self._hotkey_registered:
                try:
                    import ctypes
                    ctypes.windll.user32.UnregisterHotKey(None, 0x4E4F)
                except Exception:
                    pass
                self._hotkey_registered = False
            event.accept()
            if not self._quit_requested:
                QTimer.singleShot(0, QApplication.instance().quit)
            return
        self.hide()
        if hasattr(self, "tray") and notifications_enabled():
            self.tray.showMessage("NOVA is still running", "Use Ctrl+Alt+Space or the tray icon to reopen NOVA.")
        event.ignore()

    def _open_task_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("NOVA scheduled tasks")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        description = QLabel("Approved tasks run locally on schedule. The current scheduler supports read-only system and storage reports.")
        description.setWordWrap(True)
        description.setObjectName("muted")
        layout.addWidget(description)
        items = QListWidget()
        layout.addWidget(items, 1)
        status = QLabel("Tasks are stored locally with NOVA's memory database.")
        status.setObjectName("muted")
        layout.addWidget(status)

        def refresh() -> None:
            items.clear()
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/tasks")
                response.raise_for_status()
                tasks = response.json().get("tasks", [])
                for task in tasks:
                    label = f"{task['status'].replace('_', ' ').upper()}  ·  {task['title']}  ·  {task['action_id']}  ·  {task['schedule_at']}  ·  {task['recurrence']}"
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, task)
                    items.addItem(item)
                status.setText(f"{len(tasks)} task(s). Pending approval tasks will not run.")
            except Exception as exc:
                status.setText(f"Task service unavailable: {exc}")

        def selected_task() -> dict | None:
            item = items.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def create_task() -> None:
            title, accepted = QInputDialog.getText(dialog, "New scheduled task", "Task name:")
            if not accepted or not title.strip():
                return
            action_label, accepted = QInputDialog.getItem(
                dialog, "Task action", "Choose a read-only action:",
                ["System status snapshot", "Storage usage report"], 0, False,
            )
            if not accepted:
                return
            action_id = "system.snapshot" if action_label.startswith("System") else "storage.report"
            default_time = (datetime.now().astimezone() + timedelta(hours=1)).isoformat(timespec="minutes")
            schedule_at, accepted = QInputDialog.getText(
                dialog, "Schedule time", "Enter a future ISO date/time with timezone offset:",
                text=default_time,
            )
            if not accepted or not schedule_at.strip():
                return
            recurrence, accepted = QInputDialog.getItem(
                dialog, "Repeat task", "Choose recurrence:", ["once", "daily", "weekly"], 0, False,
            )
            if not accepted:
                return
            try:
                response = _HTTP_CLIENT.post(f"{API_ROOT}/tasks", json={
                    "title": title.strip(), "action_id": action_id, "parameters": {},
                    "schedule_at": schedule_at.strip(), "recurrence": recurrence,
                })
                response.raise_for_status()
                status.setText("Task created. Review it and select Approve before it can run.")
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not create task", str(exc))

        def approve_task() -> None:
            task = selected_task()
            if not task:
                return
            if task.get("status") != "pending_approval":
                QMessageBox.information(dialog, "Approval not needed", "Only pending tasks can be approved.")
                return
            answer = QMessageBox.question(
                dialog, "Approve scheduled task?",
                f"Approve this exact task?\n\n{task['title']}\nAction: {task['action_id']}\nNext run: {task['schedule_at']}\nRecurrence: {task['recurrence']}\n\nThis action is read-only and will run automatically at the scheduled time.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                response = _HTTP_CLIENT.post(f"{API_ROOT}/tasks/{task['id']}/approve")
                response.raise_for_status()
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not approve task", str(exc))

        def set_task_state(action: str) -> None:
            task = selected_task()
            if not task:
                return
            endpoint = "pause" if action == "pause" else "cancel"
            answer = QMessageBox.question(
                dialog, f"{action.title()} task?",
                f"{action.title()} '{task['title']}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                response = _HTTP_CLIENT.post(f"{API_ROOT}/tasks/{task['id']}/{endpoint}")
                response.raise_for_status()
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, f"Could not {action} task", str(exc))

        def show_history() -> None:
            task = selected_task()
            if not task:
                return
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/tasks/{task['id']}/history")
                response.raise_for_status()
                runs = response.json().get("runs", [])
                if not runs:
                    QMessageBox.information(dialog, "Task history", "This task has not run yet.")
                    return
                lines = [f"{run['finished_at']} · {run['outcome'].upper()} · {run['result']}" for run in runs]
                QMessageBox.information(dialog, "Task execution history", "\n\n".join(lines))
            except Exception as exc:
                QMessageBox.warning(dialog, "History unavailable", str(exc))

        actions = QHBoxLayout()
        for label, callback in [
            ("Create task", create_task), ("Approve", approve_task),
            ("Pause", lambda: set_task_state("pause")),
            ("Cancel", lambda: set_task_state("cancel")), ("History", show_history),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        refresh()
        dialog.exec()

    def _open_computer_controls(self) -> None:
        dialog = ComputerControlsDialog(self)
        dialog.exec()

    def _open_history_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Conversation history")
        dialog.resize(620, 440)
        layout = QVBoxLayout(dialog)
        description = QLabel("Open a previous conversation saved in NOVA's local SQLite database.")
        description.setObjectName("muted")
        layout.addWidget(description)
        items = QListWidget()
        layout.addWidget(items, 1)

        def refresh() -> None:
            items.clear()
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/conversations")
                response.raise_for_status()
                conversations = response.json().get("conversations", [])
            except Exception as exc:
                QMessageBox.warning(dialog, "History unavailable", str(exc))
                return
            for conversation in conversations:
                item = QListWidgetItem(conversation.get("title", "Conversation"))
                item.setData(Qt.ItemDataRole.UserRole, conversation)
                items.addItem(item)

        actions = QHBoxLayout()
        load_button = QPushButton("Open conversation")
        delete_button = QPushButton("Delete")
        close_button = QPushButton("Close")
        actions.addWidget(load_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

        def selected_conversation() -> dict | None:
            item = items.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def load() -> None:
            conversation = selected_conversation()
            if not conversation:
                return
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/conversations/{conversation['id']}")
                response.raise_for_status()
                messages = response.json().get("messages", [])
                self.conversation_id = conversation["id"]
                self.history.clear()
                while self.chat_layout.count() > 1:
                    item = self.chat_layout.takeAt(0)
                    if item.layout():
                        while item.layout().count():
                            child = item.layout().takeAt(0)
                            if child.widget():
                                child.widget().deleteLater()
                        item.layout().deleteLater()
                for message in messages:
                    role = message.get("role", "assistant")
                    content = message.get("content", "")
                    self.history.append({"role": role, "content": content})
                    self._add_message("YOU" if role == "user" else "NOVA", content)
                dialog.accept()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not open conversation", str(exc))

        def delete() -> None:
            conversation = selected_conversation()
            if not conversation:
                return
            answer = QMessageBox.question(dialog, "Delete conversation", "Permanently delete this conversation and its messages?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                response = _HTTP_CLIENT.delete(f"{API_ROOT}/conversations/{conversation['id']}")
                response.raise_for_status()
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not delete conversation", str(exc))

        load_button.clicked.connect(load)
        delete_button.clicked.connect(delete)
        close_button.clicked.connect(dialog.accept)
        items.itemDoubleClicked.connect(lambda _item: load())
        refresh()
        dialog.exec()

    def _open_memory_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("NOVA Memory")
        dialog.resize(620, 440)
        layout = QVBoxLayout(dialog)
        description = QLabel("Memories stay on this device. Pending items are not used in responses until approved.")
        description.setWordWrap(True)
        description.setObjectName("muted")
        layout.addWidget(description)
        items = QListWidget()
        layout.addWidget(items, 1)

        def refresh() -> None:
            items.clear()
            try:
                response = _HTTP_CLIENT.get(f"{API_ROOT}/memory")
                response.raise_for_status()
                memories = response.json().get("memories", [])
            except Exception as exc:
                QMessageBox.warning(dialog, "Memory unavailable", str(exc))
                return
            for memory in memories:
                prefix = "PENDING · " if memory.get("status") == "pending" else ""
                item = QListWidgetItem(prefix + memory.get("content", ""))
                item.setData(Qt.ItemDataRole.UserRole, memory)
                items.addItem(item)

        actions = QHBoxLayout()
        approve_button = QPushButton("Approve")
        edit_button = QPushButton("Edit")
        delete_button = QPushButton("Delete")
        close_button = QPushButton("Close")
        actions.addWidget(approve_button)
        actions.addWidget(edit_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

        def selected_memory() -> dict | None:
            item = items.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def approve() -> None:
            memory = selected_memory()
            if not memory:
                return
            if memory.get("status") != "pending":
                QMessageBox.information(dialog, "Already approved", "This memory is already active.")
                return
            try:
                response = _HTTP_CLIENT.post(f"{API_ROOT}/memory/{memory['id']}/approve")
                response.raise_for_status()
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not approve memory", str(exc))

        def edit() -> None:
            memory = selected_memory()
            if not memory:
                return
            value, accepted = QInputDialog.getMultiLineText(dialog, "Edit memory", "Memory content:", memory.get("content", ""))
            if not accepted or not value.strip():
                return
            try:
                response = _HTTP_CLIENT.patch(f"{API_ROOT}/memory/{memory['id']}", json={"content": value.strip()})
                response.raise_for_status()
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not edit memory", str(exc))

        def delete() -> None:
            memory = selected_memory()
            if not memory:
                return
            answer = QMessageBox.question(dialog, "Delete memory", "Permanently delete this saved memory?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                response = _HTTP_CLIENT.delete(f"{API_ROOT}/memory/{memory['id']}")
                response.raise_for_status()
                refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, "Could not delete memory", str(exc))

        approve_button.clicked.connect(approve)
        edit_button.clicked.connect(edit)
        delete_button.clicked.connect(delete)
        close_button.clicked.connect(dialog.accept)
        refresh()
        dialog.exec()

    def _new_chat(self) -> None:
        self.history.clear()
        self.conversation_id = str(uuid4())
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                item.layout().deleteLater()
        self._add_message("NOVA", "New conversation started. How can I help?")
        self.input.setFocus()


def main() -> None:
    if "--nova-backend" in sys.argv:
        from nova.service import main as run_service
        run_service()
        return

    app = QApplication(sys.argv)
    app.setApplicationName("NOVA")
    app.setOrganizationName("NOVA")
    app.setFont(QFont("Segoe UI", 10))
    app.setQuitOnLastWindowClosed(False)
    instance_lock = QLockFile(str(user_data_dir() / "nova.lock"))
    if not instance_lock.tryLock(0):
        if "--background" not in sys.argv:
            QMessageBox.information(None, "NOVA is already running", "NOVA is already active in the Windows notification area.")
        return
    window = NovaWindow()
    if "--background" not in sys.argv:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()