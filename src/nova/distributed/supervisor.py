"""Own the optional local Docker Compose cluster for the desktop session."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from nova.config import user_data_dir


class ClusterSupervisor:
    """Start NOVA's local Compose services without blocking the desktop UI."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.context_dir = self._resolve_context_dir()
        self.compose_file = self.context_dir / "docker-compose.yml"
        self._state = "disabled" if not enabled else "idle"
        self._error: str | None = None
        self._owned = False
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _resolve_context_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "cluster"
        return Path(__file__).resolve().parents[3]

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def _set_state(self, state: str, error: str | None = None) -> None:
        with self._lock:
            self._state = state
            self._error = error

    def _compose_command(self) -> list[str]:
        docker = shutil.which("docker")
        if not docker:
            raise RuntimeError("Docker Desktop is not installed or docker.exe is not on PATH.")
        if not self.compose_file.is_file():
            raise RuntimeError(f"NOVA's local Compose file was not found: {self.compose_file}")
        return [
            docker,
            "compose",
            "--project-name",
            "nova-local-cluster",
            "--project-directory",
            str(self.context_dir),
            "-f",
            str(self.compose_file),
        ]

    def _run(self, command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=str(self.context_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        self._write_log(command, result.stdout, result.stderr)
        return result

    @staticmethod
    def _write_log(command: list[str], stdout: str, stderr: str) -> None:
        try:
            log_dir = user_data_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "cluster.log").open("a", encoding="utf-8") as handle:
                handle.write("\n$ " + " ".join(command) + "\n")
                if stdout:
                    handle.write(stdout.rstrip() + "\n")
                if stderr:
                    handle.write(stderr.rstrip() + "\n")
        except OSError:
            pass

    def start_background(self) -> None:
        if not self.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_requested.clear()
        self._set_state("starting")
        self._thread = threading.Thread(
            target=self._start_cluster,
            name="nova-cluster-supervisor",
            daemon=True,
        )
        self._thread.start()

    def _start_cluster(self) -> None:
        try:
            command = self._compose_command()
            docker_check = self._run(command[:2] + ["info", "--format", "{{.ServerVersion}}"], 12)
            if docker_check.returncode != 0:
                raise RuntimeError("Docker Desktop is installed but its engine is not running. Start Docker Desktop and try again.")

            base = command + ["ps", "--services", "--filter", "status=running"]
            existing = self._run(base, 20)
            if existing.returncode != 0:
                raise RuntimeError(existing.stderr.strip() or "Could not inspect the NOVA Compose project.")
            self._owned = not bool(existing.stdout.strip())

            started = self._run(command + ["up", "-d", "--build"], 600)
            if started.returncode != 0:
                self._owned = False
                raise RuntimeError(started.stderr.strip() or started.stdout.strip() or "Docker Compose could not start NOVA's services.")
            self._set_state("running")
            if self._stop_requested.is_set():
                self._stop_cluster_detached()
        except subprocess.TimeoutExpired:
            self._owned = False
            self._set_state("error", "Docker Compose timed out while starting NOVA's local services.")
        except Exception as exc:
            self._owned = False
            self._set_state("unavailable", str(exc))

    def stop_background(self) -> None:
        self._stop_requested.set()
        if not self._owned:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_cluster_detached()

    def _stop_cluster_detached(self) -> None:
        if not self._owned:
            return
        try:
            command = self._compose_command() + ["down"]
            log_dir = user_data_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_handle = (log_dir / "cluster.log").open("a", encoding="utf-8")
            subprocess.Popen(
                command,
                cwd=str(self.context_dir),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
            self._owned = False
            self._set_state("stopping")
        except Exception as exc:
            self._set_state("error", f"Could not stop NOVA's local containers: {exc}")