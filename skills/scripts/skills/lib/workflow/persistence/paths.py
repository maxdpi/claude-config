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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (override wins at the leaf).

    Nested dicts are merged key-by-key; any non-dict value (or a dict replacing
    a non-dict) is taken from ``override``.  ``base`` is not mutated.
    """
    out = dict(base)
    for key, value in override.items():
        existing = out.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            out[key] = _deep_merge(existing, value)
        else:
            out[key] = value
    return out


def read_settings_merged(claude_dir_path: Path | None = None) -> dict[str, Any]:
    """Return ``settings.json`` deep-merged with ``settings.local.json`` on top.

    THE single source of settings-precedence truth.  ``settings.local.json``
    overrides ``settings.json`` at the *leaf*, so a key present in only one file
    survives and a key in both resolves to the local value.  This replaces three
    independently-written precedence loops that achieved local-wins via *opposite*
    mechanisms — two used first-present-key iteration over ``(local, json)`` while
    a third used a shallow ``dict.update()`` over ``(json, local)``.  Both happened
    to be correct, but the divergence was a copy-paste hazard: any reorder or
    merge-semantics swap silently inverted precedence (the latent bug).

    A *deep* merge is used deliberately so that, e.g., a ``settings.local.json``
    that defines only ``permissions.allow`` does NOT shadow a ``permissions.
    defaultMode`` set in ``settings.json`` — preserving the per-key fallback the
    security-sensitive permission-mode read (R-003/R-007) relied on.

    Args:
        claude_dir_path: Base dir holding the two settings files.  Defaults to
            ``claude_dir()``; callers pass their module ``_CLAUDE_DIR`` so test
            monkeypatching of that constant continues to work.
    """
    base_dir = claude_dir_path if claude_dir_path is not None else claude_dir()
    base = read_settings_file(base_dir / "settings.json")
    local = read_settings_file(base_dir / "settings.local.json")
    return _deep_merge(base, local)


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
