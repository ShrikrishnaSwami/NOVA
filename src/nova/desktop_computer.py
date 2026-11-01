"""Small desktop surface for explicitly approved computer actions."""

from __future__ import annotations

import os

import httpx
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
    QVBoxLayout, QInputDialog,
)

API_ROOT = os.getenv("NOVA_API_URL", "http://127.0.0.1:8000").rstrip("/")
_HTTP_CLIENT = httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))


class ComputerControlsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NOVA Computer Controls")
        self.resize(680, 500)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "These tools are deliberately limited. Every operation requires your confirmation. "
            "File access is restricted to folders listed in NOVA_COMPUTER_ALLOWED_ROOTS."
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
            ("Audit log", self.show_audit),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
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
                "Approved folders:\n" + ("\n".join(roots) if roots else "None configured — file tools are disabled.")
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
                    self.output.addItem(match)
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
            QMessageBox.information(self, "No approved folders", "Add one or more folders to NOVA_COMPUTER_ALLOWED_ROOTS in your private .env file, then restart the backend.")
            return
        path, accepted = QInputDialog.getItem(self, "List folder", "Choose an approved folder:", roots, 0, False)
        if accepted:
            self.execute("list_directory", {"path": path}, f"list the contents of {path}")

    def search_files(self) -> None:
        capabilities = self.refresh_capabilities()
        roots = capabilities.get("file_roots", [])
        if not roots:
            QMessageBox.information(self, "No approved folders", "Add folders to NOVA_COMPUTER_ALLOWED_ROOTS in your private .env file, then restart the backend.")
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
            QMessageBox.information(self, "No approved folders", "Add folders to NOVA_COMPUTER_ALLOWED_ROOTS in your private .env file, then restart the backend.")
            return
        root, accepted = QInputDialog.getItem(self, "Read text file", "Choose an approved folder:", roots, 0, False)
        if not accepted:
            return
        path, accepted = QInputDialog.getText(self, "Read text file", "Enter the full path to a text file inside that folder:")
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
