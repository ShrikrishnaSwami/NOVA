"""Small desktop surface for explicitly approved computer actions."""

from __future__ import annotations

import os
import json

import httpx
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
    QVBoxLayout, QInputDialog,
)

API_ROOT = os.getenv("NOVA_API_URL", "http://127.0.0.1:8000").rstrip("/")
_HTTP_CLIENT = httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0))


class ComputerControlsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NOVA Computer Controls")
        self.resize(680, 500)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "These tools are deliberately limited. Every operation requires your confirmation. "
            "NOVA discovers accessible local drives by default. Opening and reading items requires confirmation."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.status = QLabel("Loading computer permissions…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.output = QListWidget()
        layout.addWidget(self.output, 1)

        actions = QHBoxLayout()
        for label, callback in (
            ("Open app", self.open_app),
            ("List folder", self.list_folder),
            ("Search files", self.search_files),
            ("Search contents", self.search_contents),
            ("Open path", self.open_path),
            ("Read text file", self.read_file),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)

        os_actions = QHBoxLayout()
        for label, callback in (
            ("System overview", self.show_system),
            ("Running processes", self.show_processes),
            ("Open windows", self.show_windows),
            ("Audit log", self.show_audit),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            os_actions.addWidget(button)
        layout.addLayout(os_actions)

        window_actions = QHBoxLayout()
        control_windows = QPushButton("Control a window")
        control_windows.clicked.connect(self.control_window)
        window_actions.addWidget(control_windows)
        layout.addLayout(window_actions)

        system_controls = QHBoxLayout()
        for label, callback in (
            ("Set volume", self.set_volume),
            ("Set brightness", self.set_brightness),
            ("Windows Search", self.windows_search),
            ("Watch active app", self.toggle_foreground_watch),
            ("Watch battery", self.toggle_battery_watch),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            system_controls.addWidget(button)
        layout.addLayout(system_controls)

        automation_row = QHBoxLayout()
        interact_button = QPushButton("Interact with an app")
        interact_button.clicked.connect(self.interact_with_app)
        automation_row.addWidget(interact_button)
        text_button = QPushButton("Enter text into an app")
        text_button.clicked.connect(self.enter_text_into_app)
        automation_row.addWidget(text_button)
        layout.addLayout(automation_row)

        self.foreground_timer = QTimer(self)
        self.foreground_timer.setInterval(2000)
        self.foreground_timer.timeout.connect(self._poll_foreground)
        self._last_foreground_title = None
        self._foreground_watch_enabled = False
        self.battery_timer = QTimer(self)
        self.battery_timer.setInterval(60000)
        self.battery_timer.timeout.connect(self._poll_battery)
        self._battery_watch_enabled = False
        self._battery_low_notified = False
        self._battery_last_plugged = None

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.refresh_capabilities()

    def request(self, method: str, path: str, **kwargs):
        response = _HTTP_CLIENT.request(method, f"{API_ROOT}{path}", **kwargs)
        response.raise_for_status()
        return response.json()

    def refresh_capabilities(self) -> dict:
        try:
            data = self.request("GET", "/computer/capabilities")
            roots = data.get("file_roots", [])
            self.status.setText(
                "Accessible drives / configured folders:\n" + ("\n".join(roots) if roots else "No accessible locations found.")
                + f"\n\nDiscovered applications: {data.get('application_count', len(data.get('applications', [])))}"
            )
            return data
        except Exception as exc:
            self.status.setText(f"Could not load computer permissions: {exc}")
            return {}

    def execute(self, action: str, parameters: dict, description: str) -> dict | None:
        answer = QMessageBox.question(
            self,
            "Approve computer action?",
            f"NOVA is about to: {description}\n\nDo you want to allow this one action?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("Action cancelled. Nothing was executed.")
            return None
        try:
            data = self.request(
                "POST", "/computer/actions",
                json={"action": action, "parameters": parameters, "approved": True},
            )
            result = data.get("result", {})
            self.output.clear()
            if "entries" in result:
                for entry in result["entries"]:
                    self.output.addItem(f"{'[Folder]' if entry['type'] == 'folder' else '[File]'} {entry['name']}")
                self.status.setText(f"Contents of {result['path']}")
            elif "matches" in result:
                for match in result["matches"]:
                    self.output.addItem(match.get("path", "") + " — " + match.get("preview", "") if isinstance(match, dict) else str(match))
                self.status.setText(f"{len(result['matches'])} matching paths found.")
            elif "content" in result:
                self.output.addItem(f"File: {result['path']}")
                for line in result["content"].splitlines():
                    self.output.addItem(line)
                self.status.setText("File content displayed locally. It was not sent to the AI model.")
            else:
                self.status.setText(result.get("message", "Action completed."))
            return result
        except httpx.HTTPStatusError as exc:
            try:
                message = exc.response.json().get("detail", str(exc))
            except ValueError:
                message = str(exc)
            QMessageBox.warning(self, "Computer action blocked", str(message))
        except Exception as exc:
            QMessageBox.warning(self, "Computer action failed", str(exc))
        return None

    def open_app(self) -> None:
        capabilities = self.refresh_capabilities()
        apps = capabilities.get("applications", [])
        if not apps:
            return
        labels = [item.get("name", "Unnamed app") for item in apps]
        app_name, accepted = QInputDialog.getItem(self, "Open application", "Choose an installed app:", labels, 0, False)
        if accepted:
            selected = next((item for item in apps if item.get("name") == app_name), None)
            if selected:
                self.execute(
                    "open_application",
                    {"app_id": selected["app_id"]},
                    f"open {app_name}",
                )

    def list_folder(self) -> None:
        capabilities = self.refresh_capabilities()
        roots = capabilities.get("file_roots", [])
        if not roots:
            QMessageBox.information(self, "No approved folders", "No accessible drives or folders were discovered.")
            return
        path, accepted = QInputDialog.getItem(self, "List folder", "Choose an accessible drive or configured folder:", roots, 0, False)
        if accepted:
            self.execute("list_directory", {"path": path}, f"list the contents of {path}")

    def search_files(self) -> None:
        capabilities = self.refresh_capabilities()
        roots = capabilities.get("file_roots", [])
        if not roots:
            QMessageBox.information(self, "No approved folders", "No accessible drives or folders were discovered.")
            return
        root, accepted = QInputDialog.getItem(self, "Search files", "Search inside:", roots, 0, False)
        if not accepted:
            return
        query, accepted = QInputDialog.getText(self, "Search files", "File or folder name contains:")
        if accepted and query.strip():
            self.execute("search_files", {"root": root, "query": query.strip()}, f"search for '{query.strip()}' inside {root}")

    def open_path(self) -> None:
        path, accepted = QInputDialog.getText(self, "Open file or folder", "Full path to an item on an accessible drive:")
        if accepted and path.strip():
            self.execute("open_path", {"path": path.strip()}, "open " + path.strip() + " in Windows")

    def search_contents(self) -> None:
        query, accepted = QInputDialog.getText(self, "Search file contents", "Text to find inside supported local text files:")
        if accepted and query.strip():
            self.execute("search_file_contents", {"query": query.strip()}, "search accessible drives for " + query.strip())

    def read_file(self) -> None:
        capabilities = self.refresh_capabilities()
        roots = capabilities.get("file_roots", [])
        if not roots:
            QMessageBox.information(self, "No approved folders", "No accessible drives or folders were discovered.")
            return
        root, accepted = QInputDialog.getItem(self, "Read text file", "Choose an approved folder:", roots, 0, False)
        if not accepted:
            return
        path, accepted = QInputDialog.getText(self, "Read text file", "Enter the full path to a supported text, PDF, Word, or Excel file:")
        if accepted and path.strip():
            try:
                import os
                if os.path.commonpath([os.path.realpath(root), os.path.realpath(path)]) != os.path.realpath(root):
                    QMessageBox.warning(self, "Outside approved folder", "That file is not inside the selected approved folder.")
                    return
            except (OSError, ValueError):
                QMessageBox.warning(self, "Invalid path", "The path could not be validated.")
                return
            self.execute("read_text_file", {"path": path.strip()}, f"read the text content of {path.strip()}")

    def show_system(self) -> None:
        try:
            data = self.request("GET", "/computer/system")
            self.output.clear()
            for key, value in data.items():
                rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                self.output.addItem(f"{key}: {rendered}")
            self.status.setText("Read-only snapshot of the current Windows session.")
        except Exception as exc:
            QMessageBox.warning(self, "System overview unavailable", str(exc))

    def show_processes(self) -> None:
        try:
            processes = self.request("GET", "/computer/processes?limit=200").get("processes", [])
            self.output.clear()
            for process in processes:
                memory_mb = process.get("memory_bytes", 0) / (1024 * 1024)
                self.output.addItem(f"{process['name']}  ·  PID {process['pid']}  ·  {process['status']}  ·  {memory_mb:.1f} MB")
            self.status.setText(f"{len(processes)} visible process records. No command lines or environment variables are collected.")
        except Exception as exc:
            QMessageBox.warning(self, "Process inventory unavailable", str(exc))

    def show_windows(self) -> None:
        try:
            data = self.request("GET", "/computer/windows?limit=200")
            self.output.clear()
            foreground = data.get("foreground")
            if foreground:
                self.output.addItem(f"FOREGROUND  ·  {foreground.get('title', '')}  ·  PID {foreground.get('pid')}")
            for window in data.get("windows", []):
                self.output.addItem(f"{window.get('title', '')}  ·  PID {window.get('pid')}")
            self.status.setText(f"{len(data.get('windows', []))} visible top-level windows.")
        except Exception as exc:
            QMessageBox.warning(self, "Window inventory unavailable", str(exc))

    def show_audit(self) -> None:
        try:
            entries = self.request("GET", "/computer/audit?limit=100").get("entries", [])
            self.output.clear()
            for entry in entries:
                self.output.addItem(
                    f"{entry['created_at']} · {entry['outcome'].upper()} · {entry['action']} · {entry['summary']}"
                )
            self.status.setText("Recent computer actions. File contents are never stored in this log.")
        except Exception as exc:
            QMessageBox.warning(self, "Audit log unavailable", str(exc))


    def control_window(self) -> None:
        try:
            windows = self.request("GET", "/computer/windows?limit=200").get("windows", [])
            if not windows:
                QMessageBox.information(self, "No open windows", "NOVA could not find any visible titled windows.")
                return
            labels = [f"{item.get('title', 'Untitled')}  ·  PID {item.get('pid')}  ·  {item.get('handle')}" for item in windows]
            selected, accepted = QInputDialog.getItem(self, "Choose a window", "Select a visible window:", labels, 0, False)
            if not accepted:
                return
            target = windows[labels.index(selected)]
            action, accepted = QInputDialog.getItem(
                self, "Window action", "Choose what NOVA should do:",
                ["Focus / switch to", "Minimize", "Restore", "Maximize", "Close window (may prompt to save)"], 0, False,
            )
            if not accepted:
                return
            action_id = {
                "Focus / switch to": "focus", "Minimize": "minimize",
                "Restore": "restore", "Maximize": "maximize",
                "Close window (may prompt to save)": "close",
            }[action]
            answer = QMessageBox.question(
                self, "Approve window control?",
                f"NOVA will {action.lower()} this window:\n\n{target.get('title')}\n\nAllow this one action?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status.setText("Window action cancelled.")
                return
            result = self.request(
                "POST", "/computer/windows/actions",
                json={"handle": target["handle"], "action": action_id, "approved": True},
            )
            self.status.setText(result.get("message", "Window action requested."))
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except ValueError:
                detail = str(exc)
            QMessageBox.warning(self, "Window control blocked", str(detail))
        except Exception as exc:
            QMessageBox.warning(self, "Window control unavailable", str(exc))


    def execute_window_target(self, target: dict, action: str) -> dict | None:
        """Ask for one confirmation, then perform one selected window action."""
        labels = {"focus": "switch to", "minimize": "minimize", "restore": "restore", "maximize": "maximize", "close": "close"}
        if action not in labels:
            QMessageBox.warning(self, "Unsupported window action", "That window action is not supported.")
            return None
        title = str(target.get("title") or "selected window")
        answer = QMessageBox.question(
            self, "Approve window control?",
            f"NOVA will {labels[action]} this window:\n\n{title}\n\n"
            + ("The app may prompt you to save changes. NOVA will not force-quit it.\n\n" if action == "close" else "")
            + "Allow this one action?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("Window action cancelled.")
            return None
        try:
            result = self.request(
                "POST", "/computer/windows/actions",
                json={"handle": target["handle"], "action": action, "approved": True},
            )
            self.status.setText(result.get("message", "Window action requested."))
            return result
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except ValueError:
                detail = str(exc)
            QMessageBox.warning(self, "Window control blocked", str(detail))
        except Exception as exc:
            QMessageBox.warning(self, "Window control unavailable", str(exc))
        return None


    def set_volume(self) -> None:
        percent, accepted = QInputDialog.getInt(self, "System volume", "Set master volume (0–100%):", 35, 0, 100)
        if not accepted:
            return
        answer = QMessageBox.question(
            self, "Approve volume change?", f"Set Windows master volume to {percent}%?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.request("POST", "/computer/system/volume",
                                  json={"percent": percent, "approved": True})
            self.status.setText(result.get("message", "Volume updated."))
        except Exception as exc:
            QMessageBox.warning(self, "Volume control unavailable", str(exc))

    def set_brightness(self) -> None:
        percent, accepted = QInputDialog.getInt(self, "Display brightness", "Set internal display brightness (0–100%):", 60, 0, 100)
        if not accepted:
            return
        answer = QMessageBox.question(
            self, "Approve brightness change?", f"Set supported display brightness to {percent}%?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.request("POST", "/computer/system/brightness",
                                  json={"percent": percent, "approved": True})
            self.status.setText(result.get("message", "Brightness update requested."))
        except Exception as exc:
            QMessageBox.warning(self, "Brightness control unavailable", str(exc))

    def windows_search(self) -> None:
        query, accepted = QInputDialog.getText(self, "Windows Search", "Search Windows-indexed files, apps, and settings for:")
        if not accepted or not query.strip():
            return
        answer = QMessageBox.question(
            self, "Open Windows Search?",
            f"NOVA will open the native Windows Search results for:\n\n{query.strip()}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.request("POST", "/computer/windows/search",
                                  json={"query": query.strip(), "approved": True})
            self.status.setText(result.get("message", "Windows Search opened."))
        except Exception as exc:
            QMessageBox.warning(self, "Windows Search unavailable", str(exc))

    def toggle_foreground_watch(self) -> None:
        if self._foreground_watch_enabled:
            self.foreground_timer.stop()
            self._foreground_watch_enabled = False
            self.status.setText("Active-app awareness paused. No further window polling.")
            return
        answer = QMessageBox.question(
            self, "Enable active-app awareness?",
            "While this dialog remains open, NOVA will check the foreground window title every 2 seconds and show changes here. Titles stay local and are not sent to the AI or saved. Enable this temporary monitor?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._foreground_watch_enabled = True
        self._last_foreground_title = None
        self.foreground_timer.start()
        self.status.setText("Active-app awareness enabled for this dialog only. Click again to pause.")

    def _poll_foreground(self) -> None:
        if not self._foreground_watch_enabled:
            return
        try:
            data = self.request("GET", "/computer/system")
            foreground = data.get("foreground_window") or {}
            title = str(foreground.get("title") or "(no titled foreground window)")
            if title != self._last_foreground_title:
                self._last_foreground_title = title
                self.output.addItem("Active window changed: " + title)
                self.status.setText("Temporary active-app awareness is running. Window titles remain local.")
        except Exception as exc:
            self.status.setText(f"Active-app monitor paused after an error: {exc}")
            self.foreground_timer.stop()
            self._foreground_watch_enabled = False

    def closeEvent(self, event) -> None:
        self.foreground_timer.stop()
        self._foreground_watch_enabled = False
        self.battery_timer.stop()
        self._battery_watch_enabled = False
        super().closeEvent(event)


    def execute_system_action(self, endpoint: str, payload: dict, description: str) -> dict | None:
        answer = QMessageBox.question(
            self, "Approve Windows action?",
            f"NOVA is about to {description}.\n\nAllow this one action?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("Action cancelled. Windows was not changed.")
            return None
        try:
            result = self.request("POST", endpoint, json=payload)
            self.status.setText(result.get("message", "Windows action completed."))
            return result
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except ValueError:
                detail = str(exc)
            QMessageBox.warning(self, "Windows action blocked", str(detail))
        except Exception as exc:
            QMessageBox.warning(self, "Windows action failed", str(exc))
        return None


    def interact_with_app(self) -> None:
        try:
            windows = self.request("GET", "/computer/windows?limit=200").get("windows", [])
            if not windows:
                QMessageBox.information(self, "No open apps", "NOVA could not find visible titled application windows.")
                return
            labels = [f"{item.get('title')} · PID {item.get('pid')}" for item in windows]
            selected, accepted = QInputDialog.getItem(self, "Choose application", "Inspect controls in:", labels, 0, False)
            if not accepted:
                return
            target = windows[labels.index(selected)]
            controls = self.request("GET", f"/computer/windows/{target['handle']}/controls?limit=200").get("controls", [])
            if not controls:
                QMessageBox.information(self, "No supported controls", "This app exposes no enabled visible buttons, tabs, menu items, links, checkboxes, or radio buttons through Windows UI Automation.")
                return
            control_labels = [f"{item['name']}  ·  {item['control_type']}" for item in controls]
            chosen, accepted = QInputDialog.getItem(self, "Choose app control", "NOVA can activate one named control:", control_labels, 0, False)
            if not accepted:
                return
            control = controls[control_labels.index(chosen)]
            answer = QMessageBox.question(
                self, "Approve app interaction?",
                f"NOVA will activate this control in {target.get('title')}:\n\n{control['name']} ({control['control_type']})\n\nAllow this one click?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            result = self.request(
                "POST", "/computer/windows/controls/actions",
                json={
                    "handle": target["handle"], "name": control["name"],
                    "control_type": control["control_type"], "approved": True,
                },
            )
            self.status.setText(result.get("message", "Application control activated."))
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except ValueError:
                detail = str(exc)
            QMessageBox.warning(self, "App interaction blocked", str(detail))
        except Exception as exc:
            QMessageBox.warning(self, "App interaction unavailable", str(exc))


    def enter_text_into_app(self) -> None:
        try:
            windows = self.request("GET", "/computer/windows?limit=200").get("windows", [])
            if not windows:
                QMessageBox.information(self, "No open apps", "NOVA could not find visible titled application windows.")
                return
            labels = [f"{item.get('title')} · PID {item.get('pid')}" for item in windows]
            selected, accepted = QInputDialog.getItem(self, "Choose application", "Enter text into:", labels, 0, False)
            if not accepted:
                return
            target = windows[labels.index(selected)]
            fields = self.request("GET", f"/computer/windows/{target['handle']}/editable-fields?limit=100").get("fields", [])
            if not fields:
                QMessageBox.information(self, "No safe text fields", "NOVA found no enabled visible non-password text fields in this application.")
                return
            field_labels = [item["name"] for item in fields]
            field_name, accepted = QInputDialog.getItem(self, "Choose text field", "Select the exact accessible field:", field_labels, 0, False)
            if not accepted:
                return
            text, accepted = QInputDialog.getMultiLineText(self, "Text to enter", f"Enter text for {field_name} in {target.get('title')}:")
            if not accepted or not text:
                return
            answer = QMessageBox.question(
                self, "Approve application text entry?",
                f"NOVA will enter the following text into {target.get('title')} → {field_name}:\n\n{text[:500]}\n\nAllow this one text-entry action?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            result = self.request(
                "POST", "/computer/windows/controls/text",
                json={"handle": target["handle"], "name": field_name, "text": text, "approved": True},
            )
            self.status.setText(result.get("message", "Text entered."))
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except ValueError:
                detail = str(exc)
            QMessageBox.warning(self, "Text entry blocked", str(detail))
        except Exception as exc:
            QMessageBox.warning(self, "Text entry unavailable", str(exc))


    def toggle_battery_watch(self) -> None:
        if self._battery_watch_enabled:
            self.battery_timer.stop()
            self._battery_watch_enabled = False
            self.status.setText("Battery event monitoring paused.")
            return
        answer = QMessageBox.question(
            self, "Enable battery alerts?",
            "NOVA will check battery percentage and charging state once per minute while this dialog is open. It will show a Windows notification at 20% or below and when charging state changes. Battery data stays local. Enable?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._battery_watch_enabled = True
        self._battery_low_notified = False
        self._battery_last_plugged = None
        self.battery_timer.start()
        self._poll_battery()
        self.status.setText("Battery event monitoring enabled for this dialog only.")

    def _poll_battery(self) -> None:
        if not self._battery_watch_enabled:
            return
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery is None:
                self.status.setText("No battery telemetry is available on this device.")
                self.battery_timer.stop()
                self._battery_watch_enabled = False
                return
            percent = int(round(battery.percent))
            plugged = bool(battery.power_plugged)
            if self._battery_last_plugged is not None and plugged != self._battery_last_plugged:
                from nova.core.computer.shell_integration import show_windows_toast
                show_windows_toast("NOVA power event", "Power connected." if plugged else "Running on battery.")
            self._battery_last_plugged = plugged
            if percent <= 20 and not plugged and not self._battery_low_notified:
                from nova.core.computer.shell_integration import show_windows_toast
                show_windows_toast("NOVA low battery alert", f"Battery is at {percent}%. Connect power when convenient.")
                self._battery_low_notified = True
            elif percent > 25 or plugged:
                self._battery_low_notified = False
            self.status.setText(f"Battery: {percent}% · {'Charging / plugged in' if plugged else 'On battery'}")
        except Exception as exc:
            self.status.setText(f"Battery monitoring stopped: {exc}")
            self.battery_timer.stop()
            self._battery_watch_enabled = False
