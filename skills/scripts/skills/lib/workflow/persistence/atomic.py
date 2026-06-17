#!/usr/bin/env python3
"""Atomic JSON write: tmp-in-same-dir, fsync, os.rename, parent-dir fsync.

Concurrent readers never see a torn or partial file because os.rename on
POSIX is atomic once the fsync drains the buffer (C-004, DL-003, DL-004).

Parent-directory fsync
----------------------
After os.rename, the new directory entry is in the kernel's page cache but
may not be on disk yet. A power failure between os.rename and the directory
fsync can lose the rename — the parent directory's old entry is restored but
the new target path vanishes. Fsyncing the parent directory flushes the
directory block so the rename survives a crash (POSIX requirement for
durable renames on journaling + non-journaling filesystems alike).

Some platforms (e.g., macOS strict sandbox) disallow opening directories with
O_RDONLY for fsync. The guard try/except around the dir fsync tolerates this:
a missing dir fsync degrades durability guarantees but never corrupts data.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_atomic(path: Path | str, data: dict) -> None:
    """Serialize *data* to *path* atomically.

    1. Encode to JSON bytes.
    2. Write to a sibling temp file in the SAME directory (same filesystem
       as target, so os.rename is guaranteed atomic on POSIX).
    3. fsync the file descriptor to flush kernel buffers.
    4. os.rename over the target — visible to any reader as an instantaneous
       swap; a crashed writer never leaves the target in a partial state.
    5. fsync the parent directory so the rename survives a crash (the rename
       is durably recorded in the directory block on disk).

    Args:
        path: Destination path.  The parent directory must already exist.
        data: Any JSON-serialisable dict.
    """
    path = Path(path)
    payload = json.dumps(data, ensure_ascii=True, sort_keys=True).encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)

    os.rename(tmp_path, path)

    # Fsync the parent directory to durably record the rename on disk.
    # Guarded: some platforms (macOS sandbox) disallow opening dirs for fsync.
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        # Degraded durability (dir fsync unsupported on this platform/mode),
        # but never a data-corruption risk — the rename itself is atomic.
        pass
