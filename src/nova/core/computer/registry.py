"""Permission-scoped Windows computer tools and local audit logging."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_WINDOWS_SETTINGS_ID = "windows-settings"
_TEXT_SUFFIXES = {".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml", ".toml", ".ini"}
_MAX_READ_BYTES = 64 * 1024
_MAX_SEARCH_RESULTS = 200
_MAX_APPLICATIONS = 2000


def _start_shortcut(path: str) -> None:
    """Launch a discovered Windows shortcut through the Windows Shell."""
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise ComputerToolError("Start Menu shortcut launching is only available on Windows.")
    startfile(path)


def _start_menu_roots() -> list[Path]:
    roots = []
    for raw in (os.environ.get("APPDATA", ""), os.environ.get("PROGRAMDATA", "")):
        if not raw:
            continue
        base = Path(raw) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        try:
            resolved = base.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ComputerToolError(ValueError):
    """Raised when a requested computer operation is not permitted or valid."""


class ComputerToolRegistry:
    """Small allowlisted tool registry. No shell, command strings, or arbitrary executables."""

    def __init__(self, database_path: str | Path, allowed_roots: str = "") -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.allowed_roots = self._parse_roots(allowed_roots)
        self._initialize_audit()

    @staticmethod
    def _parse_roots(value: str) -> list[Path]:
        roots: list[Path] = []
        for entry in value.split(";"):
            entry = entry.strip().strip('"')
            if not entry:
                continue
            path = Path(entry).expanduser()
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
        return roots

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _initialize_audit(self) -> None:
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS computer_audit (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_computer_audit_created ON computer_audit(created_at)"
            )

    def _audit(self, action: str, parameters: dict[str, Any], outcome: str, summary: str) -> None:
        # Do not store file contents or arbitrary exception tracebacks in the audit log.
        safe_parameters = {
            key: str(value)[:500]
            for key, value in parameters.items()
            if key in {"app", "path", "root", "query"}
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO computer_audit(id, action, parameters, outcome, summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), action, json.dumps(safe_parameters), outcome, summary[:500], _now()),
            )

    def discover_applications(self) -> list[dict[str, str]]:
        """Discover apps exposed as shortcuts in either Windows Start Menu."""
        found: dict[str, dict[str, str]] = {}
        for root in _start_menu_roots():
            for current, directories, files in os.walk(root, followlinks=False):
                current_path = Path(current)
                directories[:] = [name for name in directories if not (current_path / name).is_symlink()]
                for filename in files:
                    shortcut = current_path / filename
                    if shortcut.suffix.lower() != ".lnk" or shortcut.is_symlink():
                        continue
                    try:
                        resolved = shortcut.resolve(strict=True)
                        resolved.relative_to(root)
                    except (OSError, RuntimeError, ValueError):
                        continue
                    name = shortcut.stem.strip()
                    if name:
                        found[str(resolved).casefold()] = {"name": name, "app_id": str(resolved)}
                    if len(found) >= _MAX_APPLICATIONS:
                        break
                if len(found) >= _MAX_APPLICATIONS:
                    break
        apps = sorted(found.values(), key=lambda item: item["name"].casefold())
        apps.append({"name": "Windows Settings", "app_id": _WINDOWS_SETTINGS_ID})
        return apps

    def capabilities(self) -> dict[str, Any]:
        applications = self.discover_applications()
        return {
            "applications": applications,
            "application_count": len(applications),
            "file_roots": [str(root) for root in self.allowed_roots],
            "actions": ["open_application", "list_directory", "search_files", "read_text_file"],
            "file_access_enabled": bool(self.allowed_roots),
        }

    def _resolve_allowed_path(self, value: str, *, must_exist: bool = True) -> Path:
        if not value or len(value) > 2048:
            raise ComputerToolError("A valid file or folder path is required.")
        try:
            candidate = Path(value).expanduser().resolve(strict=must_exist)
        except (OSError, RuntimeError) as exc:
            raise ComputerToolError("The requested path does not exist or cannot be accessed.") from exc
        for root in self.allowed_roots:
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
        raise ComputerToolError("That path is outside NOVA's approved folders. Add its parent folder to NOVA_COMPUTER_ALLOWED_ROOTS.")

    def execute(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute one registered operation after the UI has obtained explicit approval."""
        try:
            if action == "open_application":
                app_id = str(parameters.get("app_id", "")).strip()
                selected = next(
                    (item for item in self.discover_applications() if item["app_id"] == app_id),
                    None,
                )
                if selected is None:
                    raise ComputerToolError("That application is not in the current Windows Start Menu catalogue. Refresh the app list and try again.")
                app = selected["name"]
                if app_id == _WINDOWS_SETTINGS_ID:
                    subprocess.Popen(["explorer.exe", "ms-settings:"], shell=False, close_fds=True)
                else:
                    _start_shortcut(app_id)
                result = {"message": f"Opened {app}."}
            elif action == "list_directory":
                folder = self._resolve_allowed_path(str(parameters.get("path", "")))
                if not folder.is_dir():
                    raise ComputerToolError("The selected path is not a folder.")
                entries = []
                for child in sorted(folder.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:100]:
                    try:
                        if child.is_symlink():
                            continue
                        entries.append({"name": child.name, "type": "folder" if child.is_dir() else "file"})
                    except OSError:
                        continue
                result = {"path": str(folder), "entries": entries}
            elif action == "search_files":
                root = self._resolve_allowed_path(str(parameters.get("root", "")))
                if not root.is_dir():
                    raise ComputerToolError("The search root is not a folder.")
                query = str(parameters.get("query", "")).strip().lower()
                if not query or len(query) > 120:
                    raise ComputerToolError("Enter a search term between 1 and 120 characters.")
                matches: list[str] = []
                for current, directories, files in os.walk(root, followlinks=False):
                    current_path = Path(current)
                    directories[:] = [
                        name for name in directories
                        if not (current_path / name).is_symlink()
                    ]
                    for name in directories + files:
                        if query in name.lower():
                            candidate = current_path / name
                            try:
                                resolved = candidate.resolve(strict=True)
                                resolved.relative_to(root)
                            except (OSError, RuntimeError, ValueError):
                                continue
                            matches.append(str(resolved))
                            if len(matches) >= _MAX_SEARCH_RESULTS:
                                break
                    if len(matches) >= _MAX_SEARCH_RESULTS:
                        break
                result = {"root": str(root), "query": query, "matches": matches, "truncated": len(matches) >= _MAX_SEARCH_RESULTS}
            elif action == "read_text_file":
                file_path = self._resolve_allowed_path(str(parameters.get("path", "")))
                if not file_path.is_file() or file_path.suffix.lower() not in _TEXT_SUFFIXES:
                    raise ComputerToolError("NOVA can only read approved text formats (TXT, MD, PY, JSON, CSV, LOG, YAML, TOML, INI).")
                size = file_path.stat().st_size
                if size > _MAX_READ_BYTES:
                    raise ComputerToolError("That file is larger than NOVA's 64 KB reading limit.")
                content = file_path.read_text(encoding="utf-8-sig")
                result = {"path": str(file_path), "content": content}
            else:
                raise ComputerToolError("Unknown computer action.")
            self._audit(action, parameters, "success", result.get("message", f"{action} completed"))
            return result
        except Exception as exc:
            summary = str(exc) if isinstance(exc, ComputerToolError) else "The operation failed."
            self._audit(action, parameters, "blocked" if isinstance(exc, ComputerToolError) else "error", summary)
            if isinstance(exc, ComputerToolError):
                raise
            raise ComputerToolError(summary) from exc

    def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, action, parameters, outcome, summary, created_at FROM computer_audit ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["parameters"] = json.loads(item["parameters"])
            results.append(item)
        return results
