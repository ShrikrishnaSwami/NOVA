"""Continuous local Vosk wake-word and dictation session.

No audio is uploaded. The wake recognizer uses a constrained local grammar;
after activation a second recognizer captures one utterance and returns to standby.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable


class WakeWordSession:
    def __init__(
        self,
        model_path: str | Path,
        on_wake: Callable[[], None],
        on_utterance: Callable[[str], None],
        on_error: Callable[[str], None] | None = None,
        *,
        wake_phrases: tuple[str, ...] = ("hey nova",),
        sample_rate: int = 16000,
        silence_timeout_seconds: float = 1.2,
        command_timeout_seconds: float = 8.0,
        device: int | None = None,
    ) -> None:
        self.model_path = Path(model_path).expanduser()
        self.on_wake = on_wake
        self.on_utterance = on_utterance
        self.on_error = on_error or (lambda _message: None)
        self.wake_phrases = tuple(p.strip().lower() for p in wake_phrases if p.strip())
        if not self.wake_phrases:
            raise ValueError("At least one wake phrase is required.")
        self.sample_rate = sample_rate
        self.silence_timeout_seconds = max(0.5, float(silence_timeout_seconds))
        self.command_timeout_seconds = max(self.silence_timeout_seconds, float(command_timeout_seconds))
        self.device = device
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="NOVA-WakeWord", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._running.clear()

    @staticmethod
    def _text(result: str) -> str:
        try:
            return str(json.loads(result).get("text", "")).strip().lower()
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model

            if not self.model_path.is_dir():
                raise RuntimeError(
                    "Vosk model not found. Set NOVA_VOSK_MODEL_PATH to the extracted model folder."
                )
            model = Model(str(self.model_path))
            grammar = json.dumps([*self.wake_phrases, "[unk]"])
            wake = KaldiRecognizer(model, self.sample_rate, grammar)
            self._running.set()
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=4000,
                dtype="int16",
                channels=1,
                device=self.device,
            ) as stream:
                while not self._stop.is_set():
                    audio, overflowed = stream.read(2000)
                    if overflowed:
                        continue
                    frame = bytes(audio)
                    if not wake.AcceptWaveform(frame):
                        partial = self._text(wake.PartialResult())
                        if not any(phrase in partial for phrase in self.wake_phrases):
                            continue
                        # Wait for the recognizer's endpoint so the activation phrase
                        # is not mixed into the user's command.
                        continue
                    detected = self._text(wake.Result())
                    if not any(phrase in detected for phrase in self.wake_phrases):
                        wake = KaldiRecognizer(model, self.sample_rate, grammar)
                        continue

                    self.on_wake()
                    command = KaldiRecognizer(model, self.sample_rate)
                    utterance = ""
                    deadline = time.monotonic() + self.command_timeout_seconds
                    while not self._stop.is_set() and time.monotonic() < deadline:
                        audio, overflowed = stream.read(2000)
                        if overflowed:
                            continue
                        if command.AcceptWaveform(bytes(audio)):
                            utterance = self._text(command.Result())
                            if utterance:
                                break
                    if not utterance and not self._stop.is_set():
                        utterance = self._text(command.FinalResult())
                    if utterance and not self._stop.is_set():
                        self.on_utterance(utterance)
                    wake = KaldiRecognizer(model, self.sample_rate, grammar)
        except Exception as exc:
            self.on_error(
                f"Wake-word session stopped: {exc}. Check microphone permission and Vosk setup."
            )
        finally:
            self._running.clear()
