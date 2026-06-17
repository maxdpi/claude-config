#!/usr/bin/env python3
"""Shared filesystem primitives for the persistence substrate.

Single home for the base ``~/.claude`` path, tolerant settings parsing,
ISO-8601 timestamps, and the quarantine-log path.  These primitives were
previously re-implemented in every persistence module and hook entrypoint;
defining them once removes the lockstep-edit hazard where copies silently
diverge (I5).

Read helpers distinguish *absence* (a legitimate empty result) from
*corruption* (a present-but-unreadable file, logged at WARNING) so a broken
file never silently masquerades as "not configured" (I1).

This module is intentionally dependency-free (stdlib only) so any persistence
module or hook entrypoint can import it without risking an import cycle.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Quarantine log filename; sits beside the skill-runs base dir.
_QUARANTINE_FILENAME = "skill-run-quarantine.jsonl"


def claude_dir() -> Path:
    """Return the base ``~/.claude`` configuration directory."""
    return Path.home() / ".claude"


def read_settings_file(path: Path) -> dict[str, Any]:
    """Read a settings JSON file tolerantly.

    Returns an empty dict when the file is ABSENT (a legitimate empty result),
    and an empty dict plus a WARNING log when the file is PRESENT but
    unreadable/corrupt (an anomaly worth surfacing rather than swallowing).  A
    non-object top-level JSON value is also treated as empty (I1).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(
            "persistence: settings file %s is present but unreadable (%s) -- "
            "treating as empty", path, exc,
        )
        return {}
    return data if isinstance(data, dict) else {}


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


def quarantine_path(skill_runs_base: Path) -> Path:
    """Return the quarantine-log path that sits beside the skill-runs base.

    The quarantine log is a SIBLING of the skill-runs base dir so a tmp/test
    base keeps its quarantine writes out of the real ``~/.claude`` (mirrors how
    the debug-capture path is derived; DL-002).
    """
    return skill_runs_base.parent / _QUARANTINE_FILENAME
