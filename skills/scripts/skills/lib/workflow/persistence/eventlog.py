#!/usr/bin/env python3
"""Append one workflow-level event to events.jsonl and refresh projection.json.

Concurrency model (DL-012, R-006)
-----------------------------------
Parallel same-run hook processes (e.g., two teammate hooks firing for the
same run_id simultaneously) are made safe by two complementary mechanisms:

1. **Inode-level O_APPEND write on a regular file.**  ``os.open(..., O_APPEND)``
   + ``os.write`` gives a kernel-atomic seek+write per syscall for regular files
   (the kernel holds the inode lock for the duration of the write, preventing
   interleaving from concurrent appenders on the same fd).  Note: the POSIX
   PIPE_BUF atomicity guarantee applies to pipes and FIFOs only; for regular
   files O_APPEND gives inode-level atomicity regardless of write size.

2. **Advisory ``fcntl.flock`` on the per-run ``.lock`` file.**  The lock
   serialises the *append + fold + projection rewrite* critical section so
   that two processes do not compute a projection from the same partial
   event list and then race to overwrite ``projection.json``.

``events.jsonl`` is append-only and NEVER rewritten.  ``projection.json``
is rewritten atomically (tmp + os.rename) after each append (atomic.py).

Event size limit
----------------
The safe limit for regular file O_APPEND writes is much larger than the
POSIX PIPE_BUF minimum.  We enforce a generous limit of 65536 bytes per
event line. Events that exceed this limit truncate their ``resultPreview``
or ``result`` payload field rather than being silently dropped.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path

from .atomic import write_atomic
from .fold import empty_projection, fold
from .rundir import RunDir

log = logging.getLogger(__name__)

# Safe limit for a single event line on a regular file.
# Regular files use inode-level O_APPEND atomicity; 65536 is a generous but
# safe ceiling. Exceeding this limit triggers payload truncation, not event loss.
_MAX_EVENT_BYTES: int = 65_536


def _truncate_event(event: dict) -> bytes:
    """Return a serialized event line, truncating large payload fields if needed.

    Tries to truncate ``resultPreview`` then ``result`` from the payload to
    bring the event within ``_MAX_EVENT_BYTES``. Logs a warning if truncation
    was applied. Raises ``ValueError`` only if even a minimal event skeleton
    exceeds the limit (should never occur in practice).
    """
    line = (json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(line) <= _MAX_EVENT_BYTES:
        return line

    # Attempt truncation of large payload fields
    event = dict(event)
    payload = dict(event.get("payload") or {})
    for field in ("resultPreview", "result"):
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field][:300] + "…[truncated]"
            event["payload"] = payload
            line = (
                json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            if len(line) <= _MAX_EVENT_BYTES:
                log.warning(
                    "eventlog: event payload field %r truncated to fit within %d bytes",
                    field, _MAX_EVENT_BYTES,
                )
                return line

    # Last resort: drop the whole payload except for the journal_key dedup field
    if "payload" in event:
        jk = (event.get("payload") or {}).get("journal_key")
        event["payload"] = {"_truncated": True}
        if jk:
            event["payload"]["journal_key"] = jk
        line = (
            json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        log.warning(
            "eventlog: event payload fully stripped to fit within %d bytes "
            "(event type=%r, run_id=%r)",
            _MAX_EVENT_BYTES, event.get("type"), event.get("run_id"),
        )

    if len(line) > _MAX_EVENT_BYTES:
        raise ValueError(
            f"Event skeleton exceeds {_MAX_EVENT_BYTES} bytes even after full "
            f"payload strip ({len(line)} bytes). This should never occur."
        )
    return line


def append_event(run_dir: RunDir, event: dict) -> None:
    """Append *event* to ``events.jsonl`` and recompute ``projection.json``.

    The append and projection rewrite are serialised under an advisory
    ``fcntl.flock(LOCK_EX)`` on ``run_dir.lockfile`` so concurrent
    same-run processes do not interleave or produce a stale projection.

    Oversized events have their ``resultPreview``/``result`` payload fields
    truncated before appending. Events are NEVER silently dropped.

    Args:
        run_dir: Handle returned by ``create_run_dir``.
        event: A dict produced by ``event_schema()``.
    """
    line: bytes = _truncate_event(event)

    events_path: Path = run_dir.events_jsonl
    lock_path: Path = run_dir.lockfile

    lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # Inode-level O_APPEND write — atomic for regular files regardless of size.
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
# Public read helper
# ---------------------------------------------------------------------------


def read_events(run_dir: "RunDir") -> list[dict]:
    """Return all events from ``events.jsonl`` as a list of dicts.

    Skips blank lines and malformed JSON so a single corrupted append does
    not block inspection or replay.  Returns an empty list if the file is
    absent.

    Args:
        run_dir: Handle returned by ``create_run_dir`` (or ``as_run_dir()``).
    """
    path: Path = run_dir.events_jsonl
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


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
