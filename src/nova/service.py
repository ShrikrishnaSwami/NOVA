"""Managed local API process for the NOVA desktop session."""
from __future__ import annotations

import os
import threading

import psutil
import uvicorn

from nova.config import get_settings


def _parent_is_alive(pid: int, expected_created: float) -> bool:
    try:
        parent = psutil.Process(pid)
        return parent.is_running() and abs(parent.create_time() - expected_created) < 1.0
    except psutil.Error:
        return False


def main() -> None:
    settings = get_settings()
    config = uvicorn.Config(
        "nova.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.casefold(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    shutdown_watch = threading.Event()
    watcher: threading.Thread | None = None

    try:
        parent_pid = int(os.environ.get("NOVA_PARENT_PID", "0"))
        parent_created = float(os.environ.get("NOVA_PARENT_CREATE_TIME", "0"))
    except ValueError:
        parent_pid, parent_created = 0, 0.0

    if parent_pid > 0 and parent_created > 0:
        def watch_parent() -> None:
            while not shutdown_watch.wait(2.0):
                if not _parent_is_alive(parent_pid, parent_created):
                    server.should_exit = True
                    return

        watcher = threading.Thread(target=watch_parent, name="nova-parent-watch", daemon=True)
        watcher.start()

    try:
        server.run()
    finally:
        shutdown_watch.set()
        if watcher is not None:
            watcher.join(timeout=1.0)


if __name__ == "__main__":
    main()
