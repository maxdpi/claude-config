#!/usr/bin/env python3
"""Retention TTL and resumability gate for skill runs.

Design notes
------------
* ``prune_runs`` deletes ONLY runs whose ``status`` is ``done`` or
  ``tombstoned`` AND whose completion timestamp is older than the configured
  TTL.  Crashed/incomplete runs are KEPT FOREVER regardless of age (DL-005).
* ``is_resumable`` is CONSULTED AT DISPLAY TIME — it is NOT a persisted flag.
  Returns ``True`` iff the run copied its native transcript at SubagentStop
  (``transcript.jsonl`` exists in the run/subagent dir — PRIMARY path), OR
  the native transcript's own mtime (resolved via stored ``session_id`` +
  ``native_agent_id`` using the A4 probe helper) is within
  ``cleanupPeriodDays`` (FALLBACK — age guard; DL-020).
* Age is judged from the native transcript's OWN mtime, NOT from
  ``started_at``.  If the native transcript path cannot be resolved, return
  ``False`` (DL-020 default-deny).
* ``is_resumable(None)`` returns ``False``.

Config key (TTL)
----------------
``skillRuns.retentionDays`` in ``~/.claude/settings.json`` or
``~/.claude/settings.local.json``.  Default: 7 days.

Config key (cleanup period)
----------------------------
``cleanupPeriodDays`` (top-level) in the same settings files.  Default: 30.
This mirrors the native platform's cleanup behaviour as documented by M-000 /
PLATFORM-ASSUMPTIONS.md (A4 finding, medium confidence for subagent
transcripts specifically).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import paths
from .rundir import RunDir, _resolve_base_dir
from .registry import RunHandle, list_runs

# Import the A4 probe helper — reuse, never re-derive (DL-015, DL-020).
from .probe.subagent_transcript_probe import resolve_transcript_path

_CLAUDE_DIR = paths.claude_dir()
_DEFAULT_RETENTION_DAYS: int = 7
_DEFAULT_CLEANUP_PERIOD_DAYS: int = 30

# Statuses that are eligible for TTL pruning (DL-005).
_PRUNABLE_STATUSES: frozenset[str] = frozenset({"done", "tombstoned", "completed"})


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _read_settings() -> dict[str, Any]:
    """Merge ``settings.json`` and ``settings.local.json`` (local takes precedence).

    Thin wrapper over the canonical ``paths.read_settings_merged`` — the single
    source of settings-precedence truth (deep merge, local-over-base).
    """
    return paths.read_settings_merged(_CLAUDE_DIR)


def _retention_days(settings: dict[str, Any] | None = None) -> int:
    """Return the configured ``skillRuns.retentionDays`` (default 7)."""
    cfg = settings if settings is not None else _read_settings()
    val = cfg.get("skillRuns", {}).get("retentionDays")
    try:
        return int(val) if val is not None else _DEFAULT_RETENTION_DAYS
    except (TypeError, ValueError):
        return _DEFAULT_RETENTION_DAYS


def _cleanup_period_days(settings: dict[str, Any] | None = None) -> int:
    """Return the configured ``cleanupPeriodDays`` (default 30)."""
    cfg = settings if settings is not None else _read_settings()
    val = cfg.get("cleanupPeriodDays")
    try:
        return int(val) if val is not None else _DEFAULT_CLEANUP_PERIOD_DAYS
    except (TypeError, ValueError):
        return _DEFAULT_CLEANUP_PERIOD_DAYS


# ---------------------------------------------------------------------------
# Resumability gate (display-time, not persisted)
# ---------------------------------------------------------------------------


def _find_copied_transcript(run_path: Path) -> Path | None:
    """Search *run_path* tree for a copy-on-stop ``transcript.jsonl`` file.

    The M-003 SubagentStop hook copies the native transcript into the
    per-subagent dir as ``transcript.jsonl`` (DL-016 primary path).  We
    accept the FIRST one found anywhere in the run subtree.
    """
    for candidate in run_path.rglob("transcript.jsonl"):
        if candidate.is_file():
            return candidate
    return None


def _find_native_transcript(
    run_path: Path,
    settings: dict[str, Any],
) -> Path | None:
    """Resolve the native transcript path for any subagent in the run.

    Reads ``task.json`` files in the run subtree to extract
    ``native_session_id`` and ``native_agent_id`` (populated by M-003),
    then delegates to the A4 probe helper (DL-020 age-guard FALLBACK).
    Returns the first successfully resolved path, or ``None``.
    """
    for task_file in run_path.rglob("task.json"):
        try:
            task_data = json.loads(task_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # Substrate stores correlation in task.json when written by M-003.
        session_id: str | None = task_data.get("native_session_id")
        native_agent_id: str | None = task_data.get("native_agent_id")
        if not (session_id and native_agent_id):
            continue
        resolved = resolve_transcript_path(session_id, native_agent_id)
        if resolved is not None:
            return resolved
    return None


def is_resumable(run: RunHandle | RunDir | None, base_dir: Path | str | None = None) -> bool:
    """Return ``True`` if *run* has a reachable native transcript.

    PRIMARY: a ``transcript.jsonl`` copy exists in the run/subagent dir
    (written by M-003 SubagentStop hook — copy-on-stop).

    FALLBACK (age guard, DL-020): the native transcript's OWN mtime
    (resolved via ``session_id`` + ``native_agent_id`` stored in
    ``task.json`` using the probe's ``resolve_transcript_path``) is within
    ``cleanupPeriodDays``.  Age is judged from the transcript file mtime,
    NOT from ``started_at``.

    Unresolvable / absent native path with no copied transcript → ``False``.

    Args:
        run: A :class:`RunHandle` or :class:`RunDir`, or ``None``.
        base_dir: Unused; present for API symmetry with ``list_runs``.

    Returns:
        ``True`` if the run has a reachable transcript; ``False`` otherwise.
    """
    if run is None:
        return False

    run_path: Path = run.path

    # PRIMARY: copy-on-stop transcript.jsonl exists anywhere in the subtree.
    copied = _find_copied_transcript(run_path)
    if copied is not None:
        return True

    # FALLBACK: resolve native transcript and check its mtime.
    settings = _read_settings()
    native = _find_native_transcript(run_path, settings)
    if native is None:
        # DL-020: unresolvable path → assume cleaned → not resumable.
        return False

    cleanup_days = _cleanup_period_days(settings)
    cutoff = time.time() - cleanup_days * 86400
    try:
        mtime = native.stat().st_mtime
    except OSError:
        # Stat failed — treat as absent → not resumable.
        return False

    return mtime >= cutoff


# ---------------------------------------------------------------------------
# Retention pruning
# ---------------------------------------------------------------------------


def _completion_ts(run_path: Path) -> float | None:
    """Return the completion Unix timestamp for a run, or ``None``.

    Reads ``run-state.json`` for a ``completed_at`` field, then tries
    ``projection.json`` for the fold's completion timestamp.
    """
    state_file = run_path / "run-state.json"
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    # Explicit completed_at field written by the SessionEnd hook (M-003).
    completed_at: str | None = data.get("completed_at")
    if completed_at:
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(completed_at)
            return dt.timestamp()
        except (ValueError, TypeError):
            pass

    # Fall back to projection.json started_at as a conservative proxy.
    proj_file = run_path / "projection.json"
    try:
        proj = json.loads(proj_file.read_text(encoding="utf-8"))
        phases: dict[str, Any] = proj.get("phases") or {}
        completed_ats: list[float] = []
        for info in phases.values():
            if isinstance(info, dict):
                ts = info.get("completed_at")
                if isinstance(ts, (int, float)) and ts > 0:
                    completed_ats.append(float(ts))
        if completed_ats:
            return max(completed_ats)
    except (json.JSONDecodeError, OSError):
        pass

    # Last resort: use started_at from run-state.json if present.
    started_at: str | None = data.get("started_at")
    if started_at:
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(started_at)
            return dt.timestamp()
        except (ValueError, TypeError):
            pass

    return None


def prune_runs(
    base_dir: Path | str | None = None,
    retention_days: int | None = None,
) -> list[str]:
    """Delete done/tombstoned runs older than the configured TTL.

    NEVER deletes crashed or incomplete runs regardless of age (DL-005).
    Does NOT consult ``is_resumable`` — the sole prune gate is:
    ``status in {done, tombstoned, completed} AND age > retentionDays``.

    Args:
        base_dir: Base directory to scan.  Defaults to resolved base.
        retention_days: Override the TTL (days).  Defaults to the value
            from ``skillRuns.retentionDays`` in settings (default 7).

    Returns:
        A list of ``run_id`` strings that were deleted.
    """
    base = Path(base_dir).expanduser() if base_dir else _resolve_base_dir()
    if not base.exists():
        return []

    settings = _read_settings()
    ttl_days = retention_days if retention_days is not None else _retention_days(settings)
    cutoff = time.time() - ttl_days * 86400

    pruned: list[str] = []

    for summary in list_runs(base):
        status: str = summary.get("status", "")
        if status not in _PRUNABLE_STATUSES:
            # Crashed, running, pending, unknown → keep indefinitely.
            continue

        run_id: str = summary["run_id"]
        run_path = base / run_id

        ts = _completion_ts(run_path)
        if ts is None or ts >= cutoff:
            # No timestamp or within TTL → keep.
            continue

        # Delete the entire run directory tree.
        try:
            shutil.rmtree(run_path)
            pruned.append(run_id)
        except OSError:
            # Best-effort deletion; skip on error.
            pass

    return pruned
