"""Permission-scoped Windows computer tools and local audit logging."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_WINDOWS_SETTINGS_ID = "windows-settings"
_TEXT_SUFFIXES = {".txt", ".md", ".py", ".json", ".csv", ".log", ".yaml", ".yml", ".toml", ".ini"}
_MAX_READ_BYTES = 2 * 1024 * 1024
_MAX_SEARCH_RESULTS = 500
_TEXT_SUFFIXES.update({".html", ".htm", ".xml", ".sql", ".js", ".ts", ".tsx", ".jsx", ".css", ".java", ".c", ".cpp", ".h", ".hpp", ".ps1", ".bat", ".sh", ".rtf"})
_MAX_APPLICATIONS = 2000
_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".xlsm"}


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


def _registered_start_apps() -> list[dict[str, str]]:
    """Read Windows' registered Start Apps catalogue, including packaged/MSIX apps."""
    if os.name != "nt":
        return []
    command = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    apps = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name", "")).strip()
        app_id = str(row.get("AppID", "")).strip()
        if name and app_id:
            apps.append({"name": name, "app_id": "startapp:" + app_id})
    return apps


def _installed_registry_apps() -> list[dict[str, str]]:
    """Discover classic desktop apps using uninstall metadata and App Paths."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    results: dict[str, dict[str, str]] = {}

    def add_executable(name: str, raw_path: str) -> None:
        raw_path = os.path.expandvars(raw_path.strip().strip('"'))
        match = re.search(r'(?i)(.*?\.exe)(?:\s*,\s*-?\d+)?$', raw_path)
        if not match:
            return
        executable = Path(match.group(1).strip().strip('"'))
        try:
            if executable.is_file() and executable.suffix.lower() == ".exe":
                resolved = str(executable.resolve())
                results.setdefault(resolved.casefold(), {
                    "name": name.strip() or executable.stem,
                    "app_id": "exe:" + resolved,
                })
        except (OSError, RuntimeError):
            return

    def add_install_location(name: str, raw_location: str) -> None:
        if not raw_location:
            return
        location = Path(os.path.expandvars(raw_location.strip().strip('"')))
        if not location.is_dir():
            return
        candidates: list[Path] = []
        try:
            candidates.extend(p for p in location.iterdir() if p.is_file() and p.suffix.lower() == ".exe")
            for child_name in ("bin", "app", "current"):
                child = location / child_name
                if child.is_dir():
                    candidates.extend(p for p in child.iterdir() if p.is_file() and p.suffix.lower() == ".exe")
        except OSError:
            return
        excluded = ("uninstall", "update", "setup", "install", "crash", "helper", "repair")
        candidates = [p for p in candidates if not any(word in p.stem.casefold() for word in excluded)]
        if not candidates:
            return
        normalized_name = re.sub(r"[^a-z0-9]", "", name.casefold())
        candidates.sort(key=lambda p: (
            0 if re.sub(r"[^a-z0-9]", "", p.stem.casefold()) == normalized_name else 1,
            len(p.name),
            p.name.casefold(),
        ))
        add_executable(name, str(candidates[0]))

    uninstall_roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, subkey in uninstall_roots:
        try:
            with winreg.OpenKey(hive, subkey) as root:
                count = winreg.QueryInfoKey(root)[0]
                for index in range(count):
                    try:
                        child_name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, child_name) as entry:
                            values = {}
                            for value_name in ("DisplayName", "DisplayIcon", "InstallLocation", "SystemComponent", "ParentKeyName"):
                                try:
                                    values[value_name] = winreg.QueryValueEx(entry, value_name)[0]
                                except OSError:
                                    pass
                        name = str(values.get("DisplayName", "")).strip()
                        if not name or values.get("SystemComponent") == 1 or values.get("ParentKeyName"):
                            continue
                        before = len(results)
                        icon = str(values.get("DisplayIcon", ""))
                        if icon:
                            add_executable(name, icon)
                        if len(results) == before:
                            add_install_location(name, str(values.get("InstallLocation", "")))
                    except (OSError, ValueError, TypeError):
                        continue
        except OSError:
            continue

    app_path_roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
    )
    views = {0, getattr(winreg, "KEY_WOW64_32KEY", 0)}
    for hive, subkey in app_path_roots:
        for view in views:
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as root:
                    count = winreg.QueryInfoKey(root)[0]
                    for index in range(count):
                        try:
                            child_name = winreg.EnumKey(root, index)
                            with winreg.OpenKey(root, child_name) as entry:
                                raw_path = str(winreg.QueryValueEx(entry, "")[0])
                            add_executable(Path(child_name).stem, raw_path)
                        except (OSError, ValueError, TypeError):
                            continue
            except OSError:
                continue
    return list(results.values())


def _extract_document_text(path: Path) -> str:
    """Extract bounded text from common local document formats using optional libraries."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ComputerToolError("PDF reading requires: pip install -e '.[documents]'") from exc
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:100])[:500_000]
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ComputerToolError("Word reading requires: pip install -e '.[documents]'") from exc
        document = Document(str(path))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables[:100]:
            for row in table.rows[:500]:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)[:500_000]
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ComputerToolError("Excel reading requires: pip install -e '.[documents]'") from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        parts = []
        try:
            for sheet in workbook.worksheets[:30]:
                parts.append(f"[Sheet: {sheet.title}]")
                for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if row_index >= 5000:
                        break
                    values = [str(value) for value in row if value is not None]
                    if values:
                        parts.append(" | ".join(values))
                    if sum(len(part) for part in parts) >= 500_000:
                        break
        finally:
            workbook.close()
        return "\n".join(parts)[:500_000]
    raise ComputerToolError("This document format is not supported for local text extraction.")


def _accessible_computer_roots() -> list[Path]:
    """Return ready local drive roots on Windows, or the user home elsewhere."""
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for index in range(26):
                if mask & (1 << index):
                    drive = Path(chr(65 + index) + ":" + os.sep)
                    if drive.is_dir():
                        roots.append(drive.resolve())
        except (AttributeError, OSError):
            pass
    else:
        home = Path.home()
        if home.is_dir():
            roots.append(home.resolve())
    return roots

def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ComputerToolError(ValueError):
    """Raised when a requested computer operation is not permitted or valid."""


class ComputerToolRegistry:
    """Permission-gated Windows discovery and file operations; no arbitrary shell commands."""

    def __init__(self, database_path: str | Path, allowed_roots: str = "") -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        has_explicit_scope = bool(allowed_roots.strip())
        configured_roots = self._parse_roots(allowed_roots)
        self.access_scope = "configured_folders" if has_explicit_scope else "accessible_drives"
        self.allowed_roots = configured_roots if has_explicit_scope else _accessible_computer_roots()
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
            if key in {"app", "app_id", "path", "root", "query"}
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
                directories[:] = [name for name in directories if not _is_link_or_junction(current_path / name)]
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
        for app in _registered_start_apps() + _installed_registry_apps():
            key = app["app_id"].casefold()
            found.setdefault(key, app)
        apps = sorted(found.values(), key=lambda item: item["name"].casefold())
        apps.append({"name": "Windows Settings", "app_id": _WINDOWS_SETTINGS_ID})
        return apps

    def capabilities(self) -> dict[str, Any]:
        applications = self.discover_applications()
        return {
            "applications": applications,
            "application_count": len(applications),
            "file_roots": [str(root) for root in self.allowed_roots],
            "actions": ["open_application", "open_path", "list_directory", "search_files", "search_file_contents", "read_text_file"],
            "file_access_enabled": bool(self.allowed_roots),
            "access_scope": self.access_scope,
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
                    raise ComputerToolError("That application is no longer in the current installed-app catalogue. Refresh the app list and try again.")
                app = selected["name"]
                if not hasattr(os, "startfile"):
                    raise ComputerToolError("Windows application launching is only available on Windows.")
                if app_id == _WINDOWS_SETTINGS_ID:
                    os.startfile("ms-settings:")
                elif app_id.startswith("exe:"):
                    executable = Path(app_id.removeprefix("exe:")).resolve(strict=True)
                    if not executable.is_file() or executable.suffix.lower() != ".exe":
                        raise ComputerToolError("The registered application executable is no longer available.")
                    os.startfile(str(executable))
                elif app_id.startswith("startapp:"):
                    registered_id = app_id.removeprefix("startapp:")
                    if Path(registered_id).is_file() and Path(registered_id).suffix.lower() == ".lnk":
                        os.startfile(registered_id)
                    else:
                        os.startfile("shell:AppsFolder\\" + registered_id)
                else:
                    os.startfile(app_id)
                result = {"message": f"Opened {app}."}
            elif action == "open_path":
                target = self._resolve_allowed_path(str(parameters.get("path", "")))
                if os.name != "nt" or not hasattr(os, "startfile"):
                    raise ComputerToolError("Opening paths through Windows Explorer is only available on Windows.")
                os.startfile(str(target))
                result = {"path": str(target), "message": f"Opened {target.name or target}."}
            elif action == "list_directory":
                folder = self._resolve_allowed_path(str(parameters.get("path", "")))
                if not folder.is_dir():
                    raise ComputerToolError("The selected path is not a folder.")
                entries = []
                for child in sorted(folder.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:100]:
                    try:
                        if _is_link_or_junction(child):
                            continue
                        entries.append({"name": child.name, "type": "folder" if child.is_dir() else "file"})
                    except OSError:
                        continue
                result = {"path": str(folder), "entries": entries}
            elif action == "search_files":
                raw_root = str(parameters.get("root", "")).strip()
                roots = [self._resolve_allowed_path(raw_root)] if raw_root else list(self.allowed_roots)
                if not roots:
                    raise ComputerToolError("No accessible folders are available to search.")
                if any(not root.is_dir() for root in roots):
                    raise ComputerToolError("The search root is not a folder.")
                query = str(parameters.get("query", "")).strip().lower()
                if not query or len(query) > 120:
                    raise ComputerToolError("Enter a search term between 1 and 120 characters.")
                matches: list[str] = []
                for root in roots:
                    for current, directories, files in os.walk(root, followlinks=False):
                        current_path = Path(current)
                        directories[:] = [
                            name for name in directories
                            if not _is_link_or_junction(current_path / name)
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
                    if len(matches) >= _MAX_SEARCH_RESULTS:
                        break
                result = {"root": raw_root or "all accessible locations", "query": query, "matches": matches, "truncated": len(matches) >= _MAX_SEARCH_RESULTS}
            elif action == "search_file_contents":
                query = str(parameters.get("query", "")).strip().casefold()
                if not query or len(query) > 200:
                    raise ComputerToolError("Enter content to search for (1–200 characters).")
                matches: list[dict[str, str]] = []
                for root in self.allowed_roots:
                    for current, directories, files in os.walk(root, followlinks=False):
                        current_path = Path(current)
                        directories[:] = [name for name in directories if not _is_link_or_junction(current_path / name)]
                        for name in files:
                            candidate = current_path / name
                            if candidate.suffix.lower() not in (_TEXT_SUFFIXES | _DOCUMENT_SUFFIXES) or _is_link_or_junction(candidate):
                                continue
                            try:
                                if candidate.stat().st_size > _MAX_READ_BYTES:
                                    continue
                                text = (
                                    _extract_document_text(candidate)
                                    if candidate.suffix.lower() in _DOCUMENT_SUFFIXES
                                    else candidate.read_text(encoding="utf-8-sig", errors="ignore")
                                )
                                if query in text.casefold():
                                    matches.append({"path": str(candidate), "preview": text[:240].replace("\n", " ")})
                            except (OSError, UnicodeError, ComputerToolError, ValueError):
                                continue
                            if len(matches) >= _MAX_SEARCH_RESULTS:
                                break
                        if len(matches) >= _MAX_SEARCH_RESULTS:
                            break
                    if len(matches) >= _MAX_SEARCH_RESULTS:
                        break
                result = {"query": query, "matches": matches, "truncated": len(matches) >= _MAX_SEARCH_RESULTS}
            elif action == "read_text_file":
                file_path = self._resolve_allowed_path(str(parameters.get("path", "")))
                if not file_path.is_file() or file_path.suffix.lower() not in (_TEXT_SUFFIXES | _DOCUMENT_SUFFIXES):
                    raise ComputerToolError("NOVA can only read supported text and document formats up to 2 MB.")
                size = file_path.stat().st_size
                if size > _MAX_READ_BYTES:
                    raise ComputerToolError("That file is larger than NOVA's 2 MB reading limit.")
                content = (
                    _extract_document_text(file_path)
                    if file_path.suffix.lower() in _DOCUMENT_SUFFIXES
                    else file_path.read_text(encoding="utf-8-sig")
                )
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
