#!/usr/bin/env python3
"""Append one workflow-level event to events.jsonl and refresh projection.json.

Concurrency model (DL-012, R-006)
-----------------------------------
Parallel same-run hook processes (e.g., two teammate hooks firing for the
same run_id simultaneously) are made safe by two complementary mechanisms:

1. **Kernel-atomic O_APPEND line write.**  Each event is serialised to a
   single newline-terminated line whose byte length is asserted to be below
   ``PIPE_BUF`` (4 096 bytes on macOS/Linux).  ``os.open(..., O_APPEND)`` +
   ``os.write`` lets the kernel guarantee that concurrent appenders never
   interleave bytes within one write syscall (POSIX O_APPEND atomicity for
   writes ≤ PIPE_BUF).

2. **Advisory ``fcntl.flock`` on the per-run ``.lock`` file.**  The lock
   serialises the *append + fold + projection rewrite* critical section so
   that two processes do not compute a projection from the same partial
   event list and then race to overwrite ``projection.json``.

``events.jsonl`` is append-only and NEVER rewritten.  ``projection.json``
is rewritten atomically (tmp + os.rename) after each append (atomic.py).
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from .atomic import write_atomic
from .fold import empty_projection, fold
from .rundir import RunDir

# POSIX guarantees O_APPEND writes <= PIPE_BUF are atomic.
# macOS/Linux PIPE_BUF == 512 (POSIX minimum); in practice 4096.
# We use the conservative POSIX minimum to be safe on all platforms.
_PIPE_BUF: int = 512


def append_event(run_dir: RunDir, event: dict) -> None:
    """Append *event* to ``events.jsonl`` and recompute ``projection.json``.

    The append and projection rewrite are serialised under an advisory
    ``fcntl.flock(LOCK_EX)`` on ``run_dir.lockfile`` so concurrent
    same-run processes do not interleave or produce a stale projection.

    Args:
        run_dir: Handle returned by ``create_run_dir``.
        event: A dict produced by ``event_schema()``.

    Raises:
        AssertionError: If the serialised event line exceeds ``PIPE_BUF``
            bytes, which would break the kernel O_APPEND atomicity guarantee.
    """
    line: bytes = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    assert len(line) < _PIPE_BUF, (
        f"Serialised event exceeds PIPE_BUF ({_PIPE_BUF} bytes): {len(line)} bytes.  "
        "Reduce payload size to maintain O_APPEND atomicity."
    )

    events_path: Path = run_dir.events_jsonl
    lock_path: Path = run_dir.lockfile

    lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # Kernel-atomic O_APPEND write — must succeed or raise; no partial.
        ev_fd = os.open(str(events_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(ev_fd, line)
        finally:
            os.close(ev_fd)

        # Recompute projection from the full event log.
        projection = _replay_from_path(events_path)
        write_atomic(run_dir.projection, projection)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


# ---------------------------------------------------------------------------
# Internal helper (reused by projection.replay without the lock)
# ---------------------------------------------------------------------------


def _replay_from_path(events_path: Path) -> dict:
    """Read *events_path* line by line and reduce through fold from empty."""
    projection = empty_projection()
    text = events_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        projection = fold(projection, event)
    return projection
