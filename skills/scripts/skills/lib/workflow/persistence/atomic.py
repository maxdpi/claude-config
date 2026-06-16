#!/usr/bin/env python3
"""Atomic JSON write: tmp-in-same-dir, fsync, os.rename.

Concurrent readers never see a torn or partial file because os.rename on
POSIX is atomic once the fsync drains the buffer (C-004, DL-003, DL-004).
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

    Args:
        path: Destination path.  The parent directory must already exist.
        data: Any JSON-serialisable dict.
    """
    path = Path(path)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)

    os.rename(tmp_path, path)
