"""NOVA's lightweight Windows desktop client."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from uuid import uuid4
from typing import Any

import httpx
from nova.config import get_settings
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


API_ROOT = os.getenv("NOVA_API_URL", "http://127.0.0.1:8000").rstrip("/")


_HTTP_CLIENT = httpx.Client(timeout=httpx.Timeout(150.0, connect=5.0))


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
    """Speak text through the operating system's installed local TTS voices."""

    failed = Signal(str)

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def run(self) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(self.text)
            engine.runAndWait()
            engine.stop()
        except Exception as exc:
            self.failed.emit(f"Speech output unavailable: {exc}")


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
        self.history: list[dict[str, str]] = []
        self.conversation_id = str(uuid4())
        self.worker: ApiWorker | None = None
        self._last_response_status: str | None = None
        self._stream_buffer = ""
        self.last_response_text = ""
        self.voice_worker: VoiceInputWorker | None = None
        self.speech_worker: SpeechOutputWorker | None = None
        self._stream_flush_timer = QTimer(self)
        self._stream_flush_timer.setInterval(40)
        self._stream_flush_timer.timeout.connect(self._flush_stream_tokens)
        self._build_ui()
        self._check_status()

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

    def _send_message(self) -> None:
        message = self.input.text().strip()
        if not message or (self.worker and self.worker.isRunning()):
            return
        self.input.clear()
        self._add_message("YOU", message)
        self.history.append({"role": "user", "content": message})
        self.send_button.setEnabled(False)
        self.send_button.setText("Thinking…")
        self.connection_label.setText("NOVA is generating…")
        self.streaming_body = self._add_message("NOVA", "")
        self.worker = ApiWorker("/chat/stream", {"message": message, "history": self.history[:-1][-20:], "conversation_id": self.conversation_id}, streaming=True)
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

    def _speak_last_response(self) -> None:
        if not self.last_response_text.strip():
            QMessageBox.information(self, "Nothing to read", "NOVA has not produced a response yet.")
            return
        if self.speech_worker and self.speech_worker.isRunning():
            QMessageBox.information(self, "Speech in progress", "NOVA is already speaking.")
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
    app = QApplication(sys.argv)
    app.setApplicationName("NOVA")
    app.setFont(QFont("Segoe UI", 10))
    window = NovaWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
