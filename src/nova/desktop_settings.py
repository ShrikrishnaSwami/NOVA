"""First-class desktop settings and microphone diagnostics for NOVA."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout
from nova.core.computer.shell_integration import (
    ShellIntegrationError, microphone_device_id, notifications_enabled,
    set_microphone_device_id, set_notifications_enabled, set_startup_enabled,
    set_wake_word_enabled, startup_enabled, wake_word_enabled,
)


class NovaSettingsDialog(QDialog):
    """User-facing controls for microphone privacy, startup, and notifications."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NOVA settings")
        self.setMinimumWidth(520)
        layout=QVBoxLayout(self)
        heading=QLabel("NOVA settings")
        heading.setStyleSheet("font-size:22px;font-weight:650;color:#eff8ff;")
        layout.addWidget(heading)
        intro=QLabel("Voice recognition runs locally on this computer. NOVA does not upload microphone audio. Wake-word standby is optional and disabled unless enabled here.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#91a6c1;")
        layout.addWidget(intro)
        self.wake=QCheckBox("Enable hands-free “Hey NOVA” wake word")
        self.wake.setChecked(wake_word_enabled())
        self.startup=QCheckBox("Start NOVA when I sign in to Windows")
        self.startup.setChecked(startup_enabled())
        self.notifications=QCheckBox("Allow NOVA Windows notifications")
        self.notifications.setChecked(notifications_enabled())
        for control in (self.wake,self.startup,self.notifications):
            control.setStyleSheet("padding:8px;color:#e7f1ff;")
            layout.addWidget(control)
        layout.addWidget(QLabel("Microphone input"))
        self.device=QComboBox()
        self.device.setMinimumHeight(36)
        self.device.addItem("Windows default microphone", None)
        try:
            import sounddevice as sd
            selected=microphone_device_id()
            found=[(i,d) for i,d in enumerate(sd.query_devices()) if int(d.get("max_input_channels",0))>0]
            for i,d in found:
                self.device.addItem(f"{d.get('name','Audio input')} · {int(d.get('max_input_channels',0))} input channel(s)",i)
            index=next((n for n in range(self.device.count()) if self.device.itemData(n)==selected),0)
            self.device.setCurrentIndex(index)
        except Exception:
            self.device.addItem("Audio device enumeration unavailable")
            self.device.setEnabled(False)
        layout.addWidget(self.device)
        self.test_status=QLabel("Use Test microphone to verify the selected input.")
        self.test_status.setWordWrap(True)
        self.test_status.setStyleSheet("color:#91a6c1;")
        layout.addWidget(self.test_status)
        test=QPushButton("Test microphone")
        test.clicked.connect(self._test_microphone)
        layout.addWidget(test)
        footer=QHBoxLayout()
        footer.addStretch()
        cancel=QPushButton("Cancel")
        save=QPushButton("Save settings")
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        footer.addWidget(cancel)
        footer.addWidget(save)
        layout.addLayout(footer)
        self.setStyleSheet("""
            QDialog { background:#0b1221;color:#e8f1ff; }
            QComboBox { background:#14243a;color:#e8f1ff;border:1px solid #29415f;border-radius:7px;padding:8px; }
            QPushButton { background:#14243a;color:#e8f1ff;border:1px solid #29415f;border-radius:8px;padding:9px 14px; }
            QPushButton:hover { background:#1b3452; }
            QCheckBox { spacing:8px; }
        """)
    def _test_microphone(self) -> None:
        try:
            import sounddevice as sd
            device_id=self.device.currentData()
            sd.check_input_settings(device=device_id,samplerate=16000,channels=1,dtype="int16")
            with sd.RawInputStream(samplerate=16000,blocksize=2000,dtype="int16",channels=1,device=device_id) as stream:
                audio,overflowed=stream.read(2000)
                if overflowed or not audio:
                    raise RuntimeError("The microphone returned no usable audio frames.")
            self.test_status.setText("Microphone test passed. NOVA can access this input.")
            self.test_status.setStyleSheet("color:#75dfb0;")
        except Exception as exc:
            self.test_status.setText(f"Microphone test failed: {exc}")
            self.test_status.setStyleSheet("color:#ff9b9b;")
    def _save(self) -> None:
        try:
            set_microphone_device_id(self.device.currentData() if self.device.isEnabled() else None)
            set_wake_word_enabled(self.wake.isChecked())
            set_notifications_enabled(self.notifications.isChecked())
            set_startup_enabled(self.startup.isChecked())
        except (ShellIntegrationError,ValueError) as exc:
            QMessageBox.warning(self,"Could not save settings",str(exc))
            return
        self.accept()
