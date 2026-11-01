from __future__ import annotations

import os

import psutil

from nova.service import _parent_is_alive


def test_service_recognizes_its_live_parent_process() -> None:
    current = psutil.Process(os.getpid())
    assert _parent_is_alive(current.pid, current.create_time())


def test_service_rejects_pid_reuse_or_missing_parent() -> None:
    current = psutil.Process(os.getpid())
    assert not _parent_is_alive(current.pid, current.create_time() + 10000)
    assert not _parent_is_alive(2147483647, 1.0)
