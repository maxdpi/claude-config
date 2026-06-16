#!/usr/bin/env python3
"""Best-effort mirror of Workflow-tool journal entries into events.jsonl (M-006, CI-M-006-004).

The Workflow tool writes a journal.jsonl under:
    ~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/journal.jsonl

Each line is:
    {"type":"started","key":"v2:<sha256>","agentId":"<id>"}
    {"type":"result","key":"v2:<sha256>","agentId":"<id>","result":"<preview>"}

where ``key`` is a content hash (v2: + sha256) of the agent() call's (prompt, opts),
used by resumeFromRunId to match cached results (confirmed in PLATFORM-ASSUMPTIONS.md A1).

This bridge:
  1. Reads the Workflow journal (A1 confirmed true — fallback DL-013 NOT selected).
  2. Mirrors entries that are not yet in events.jsonl (best-effort, idempotent).
  3. On cross-session RESUME: RECONCILES journal vs events.jsonl and DETECTS divergence
     (entries in the journal that are missing from events.jsonl due to a crash,
     un-fired hook, or session exit between journal write and bridge append).
  4. When divergence is detected: RE-DERIVES from the authoritative journal rather
     than folding a stale eventlog (DL-011).

``seq=0`` fix: use ``entry.get('seq') is not None`` (not falsy ``or``) so seq=0
(the legitimate first journal entry) is not wrongly skipped.

Design: The bridge is an optimization, not a correctness dependency (DL-013).
If the journal is not accessible (A1 false for this run), the bridge is skipped
and ported skills emit durable events directly.

Decision refs: DL-003, DL-008, DL-011, DL-013.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .eventlog import append_event, read_events
from .events import (
    EVENT_PHASE_COMPLETED,
    EVENT_PHASE_STARTED,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_SUBAGENT_SPAWNED,
    event_schema,
)
from .rundir import RunDir

# ---------------------------------------------------------------------------
# Journal location resolution
# ---------------------------------------------------------------------------

_CLAUDE_DIR = Path.home() / ".claude"


def _resolve_journal_path(run_id: str, session_id: str | None = None) -> Path | None:
    """Locate the Workflow journal for *run_id* under ~/.claude/projects/.

    Searches every project/session directory for the run.  Returns the first
    match or None if not found (A1 false for this run).

    Per PLATFORM-ASSUMPTIONS.md A1, the confirmed layout is:
        ~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/journal.jsonl
    """
    projects_dir = _CLAUDE_DIR / "projects"
    if not projects_dir.exists():
        return None

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        sessions = [project_dir] if session_id is None else []
        if session_id:
            candidate = project_dir / session_id
            if candidate.is_dir():
                sessions.append(candidate)
        else:
            # Walk all session dirs
            try:
                sessions = [d for d in project_dir.iterdir() if d.is_dir()]
            except PermissionError:
                continue

        for session_dir in sessions:
            journal = session_dir / "subagents" / "workflows" / run_id / "journal.jsonl"
            if journal.exists():
                return journal

    return None


# ---------------------------------------------------------------------------
# Journal reading
# ---------------------------------------------------------------------------


def _read_journal(journal_path: Path) -> list[dict[str, Any]]:
    """Read all parseable lines from the journal.  Skips blank/malformed lines."""
    entries: list[dict[str, Any]] = []
    try:
        text = journal_path.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return entries

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


# ---------------------------------------------------------------------------
# Stable per-entry key
# ---------------------------------------------------------------------------


def _entry_dedup_key(entry: dict[str, Any]) -> str:
    """Return a stable dedup key for a journal entry.

    The journal's ``key`` field is a content hash of the agent() call's
    (prompt, opts) — so ``started`` and ``result`` entries for the SAME
    agent() call share the same ``key`` value (that's the cache key for
    resumeFromRunId matching, per A1/A2).

    To distinguish ``started`` from ``result`` for dedup purposes we
    include the entry ``type`` as a prefix: ``{type}:{key}``.

    Fall back to a composite of (type, agentId, seq) for entries without
    a ``key`` field (older journal format or unknown entries).

    seq=0 fix: ``entry.get('seq') is not None`` so seq=0 is preserved,
    not falsy-skipped (CI-M-006-004 requirement).
    """
    entry_type = entry.get("type", "")

    # Primary: {type}:{key} — distinguishes started vs result for same agent()
    if "key" in entry:
        return f"{entry_type}:{entry['key']}"

    # Fallback: composite of type + agentId + seq
    agent_id = entry.get("agentId", "")
    seq = entry.get("seq")
    if seq is not None:  # NOTE: explicit None check — seq=0 is valid (CI-M-006-004)
        return f"{entry_type}:{agent_id}:{seq}"
    return f"{entry_type}:{agent_id}"


# ---------------------------------------------------------------------------
# Already-mirrored key set
# ---------------------------------------------------------------------------


def _mirrored_keys(run_dir: RunDir) -> set[str]:
    """Return the set of journal keys already recorded in events.jsonl.

    We store the journal key in the event payload under ``journal_key``.
    """
    mirrored: set[str] = set()
    for event in read_events(run_dir):
        payload = event.get("payload") or {}
        jk = payload.get("journal_key")
        if jk:
            mirrored.add(jk)
    return mirrored


# ---------------------------------------------------------------------------
# Journal → event mapping
# ---------------------------------------------------------------------------


def _journal_entry_to_event(
    entry: dict[str, Any],
    run_id: str,
    dedup_key: str,
) -> dict[str, Any] | None:
    """Convert a Workflow journal entry to a durable event envelope.

    Returns None for entry types we don't map (e.g., unknown types).
    """
    entry_type = entry.get("type")
    agent_id = entry.get("agentId")

    if entry_type == "started":
        return event_schema(
            type=EVENT_SUBAGENT_SPAWNED,
            run_id=run_id,
            agent_id=agent_id,
            ts=entry.get("ts") or time.time(),
            payload={
                "journal_key": dedup_key,
                "source": "journal_bridge",
            },
        )

    if entry_type == "result":
        return event_schema(
            type=EVENT_SUBAGENT_COMPLETED,
            run_id=run_id,
            agent_id=agent_id,
            ts=entry.get("ts") or time.time(),
            payload={
                "journal_key": dedup_key,
                "result": entry.get("result"),
                "source": "journal_bridge",
            },
        )

    return None


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------


def detect_divergence(
    run_dir: RunDir,
    journal_path: Path,
) -> dict[str, Any]:
    """Detect divergence between the Workflow journal and events.jsonl.

    A divergence exists when the journal contains entries whose keys are NOT
    present in events.jsonl — meaning the bridge append was missed (crash,
    un-fired hook, or session exit between journal write and bridge append).

    Returns:
        {
            "divergent": bool,
            "missing_keys": list[str],   # keys in journal but not in events
            "journal_count": int,
            "events_count": int,
        }
    """
    journal_entries = _read_journal(journal_path)
    mirrored = _mirrored_keys(run_dir)

    missing: list[str] = []
    for entry in journal_entries:
        key = _entry_dedup_key(entry)
        if key not in mirrored:
            missing.append(key)

    return {
        "divergent": bool(missing),
        "missing_keys": missing,
        "journal_count": len(journal_entries),
        "events_count": len(read_events(run_dir)),
    }


# ---------------------------------------------------------------------------
# Re-derive from journal (authoritative source on divergence)
# ---------------------------------------------------------------------------


def rederive_from_journal(
    run_dir: RunDir,
    journal_path: Path,
) -> int:
    """Re-derive events.jsonl from the authoritative Workflow journal.

    Called when divergence is detected on resume.  Mirrors ALL journal entries
    that are not yet in events.jsonl (idempotent — already-mirrored entries
    are skipped).

    Returns:
        Number of new events appended.
    """
    journal_entries = _read_journal(journal_path)
    mirrored = _mirrored_keys(run_dir)
    appended = 0

    for entry in journal_entries:
        key = _entry_dedup_key(entry)
        if key in mirrored:
            continue  # Already bridged — skip (idempotent)

        event = _journal_entry_to_event(entry, run_dir.run_id, key)
        if event is not None:
            try:
                append_event(run_dir, event)
                appended += 1
            except AssertionError:
                # Event too large for PIPE_BUF atomicity — skip and log
                # (bridge is best-effort per DL-013)
                pass

    return appended


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bridge_journal(
    run_dir: RunDir,
    run_id: str | None = None,
    session_id: str | None = None,
    journal_path: Path | None = None,
) -> dict[str, Any]:
    """Best-effort mirror of Workflow journal entries into events.jsonl.

    On cross-session resume, RECONCILES the journal against events.jsonl and
    DETECTS divergence (entries in the journal that are missing from events.jsonl
    due to a crash, un-fired hook, or session exit between journal write and
    bridge append).  When divergence is detected, RE-DERIVES from the
    authoritative Workflow journal rather than folding a stale eventlog (DL-011).

    Args:
        run_dir:      The RunDir for this skill run (M-001 durable store).
        run_id:       The Workflow tool run_id.  Defaults to run_dir.run_id.
        session_id:   Optional session_id to narrow the journal search.
        journal_path: Explicit path to journal.jsonl (skips auto-discovery;
                      useful in tests and when the caller already located it).

    Returns:
        A summary dict:
        {
            "bridged": bool,              # True if journal was found + processed
            "journal_path": str | None,   # Resolved journal path
            "appended": int,              # Events appended this call
            "divergence": dict | None,    # Divergence report (if resume)
            "rederived": bool,            # True if we re-derived from journal
            "skipped": bool,              # True if journal not accessible (A1 false)
        }
    """
    effective_run_id = run_id or run_dir.run_id

    # ── Locate the journal ────────────────────────────────────────────────────
    if journal_path is None:
        journal_path = _resolve_journal_path(effective_run_id, session_id)

    if journal_path is None or not journal_path.exists():
        # A1 false for this run — bridge is skipped (DL-013)
        return {
            "bridged": False,
            "journal_path": None,
            "appended": 0,
            "divergence": None,
            "rederived": False,
            "skipped": True,
        }

    # ── Detect divergence ─────────────────────────────────────────────────────
    divergence = detect_divergence(run_dir, journal_path)

    rederived = False
    appended = 0

    if divergence["divergent"]:
        # Resume case: journal has entries missing from events.jsonl.
        # Re-derive from the authoritative journal (DL-011).
        appended = rederive_from_journal(run_dir, journal_path)
        rederived = True
    else:
        # Normal case (incremental bridge): mirror any new entries.
        journal_entries = _read_journal(journal_path)
        mirrored = _mirrored_keys(run_dir)

        for entry in journal_entries:
            key = _entry_dedup_key(entry)
            if key in mirrored:
                continue

            event = _journal_entry_to_event(entry, effective_run_id, key)
            if event is not None:
                try:
                    append_event(run_dir, event)
                    appended += 1
                except AssertionError:
                    pass  # Too large — best-effort skip (DL-013)

    return {
        "bridged": True,
        "journal_path": str(journal_path),
        "appended": appended,
        "divergence": divergence,
        "rederived": rederived,
        "skipped": False,
    }
