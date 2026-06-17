#!/usr/bin/env python3
"""Hook-driven bridge from Agent Teams / adversarial-skill hook events to the
durable event substrate.

Agent Teams runs are NOT captured via on-disk directories (format unknown +
dirs are reaped at session end). Instead, they are captured LIVE from the hook
stream: TaskCreated, TaskCompleted, TeammateIdle, SubagentStart, and
SubagentStop payloads that carry a resolvable team_name are written into a
substrate run with id ``team-<team_name>``.

ASSUMED FIELD NAMES (R-008 / teams_bridge)
-------------------------------------------
All field names extracted from hook payloads are ASSUMED — no real Agent Teams
run has been captured to verify them. Every assumed name is marked with an
``# ASSUMED (unverified)`` comment. Update the constant at the top of this
module when a real run confirms or refutes the name.

Team name derivation (per Agent Teams docs):
    team_name = "session-" + session_id[:8]

Correlation key: ``team_name`` (or derived from ``session_id``).
Run id prefix: ``team-``

Design references: M-003, DL-002, R-008.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from .atomic import write_atomic
from .eventlog import append_event, read_events
from .events import EVENT_RUN_STARTED, event_schema
from .fold import empty_projection
from .hook_adapter import normalize_hook_event
from .registry import find_run
from . import rundir
from .rundir import RunDir
# NOTE: resolve the base via the module (rundir._resolve_base_dir()) at CALL time,
# not a bound import, so tests can monkeypatch rundir._resolve_base_dir and never
# write into the real ~/.claude.

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ASSUMED payload field names for Agent Teams events (R-008, unverified)
#
# Change these constants — not any other code — if a real run reveals different
# field names. Each is marked ASSUMED (unverified) until confirmed.
# ---------------------------------------------------------------------------

_PAYLOAD_TEAM_NAME = "team_name"       # ASSUMED (unverified): team correlation key
_PAYLOAD_TEAM_NAME_CAMEL = "teamName"  # ASSUMED (unverified): camelCase fallback
_PAYLOAD_SESSION_ID = "session_id"     # CONFIRMED via S1 (snake_case)
_PAYLOAD_SESSION_ID_CAMEL = "sessionId"  # ASSUMED (unverified): camelCase fallback

# Debug capture path: raw payloads written here before normalization so the
# next real teammate run auto-records the actual field shapes.

# Hook event names that indicate an Agent Teams event (always try team capture).
_TEAM_HOOK_TYPES: frozenset[str] = frozenset({
    "TaskCreated",
    "TaskCompleted",
    "TeammateIdle",
})


# ---------------------------------------------------------------------------
# Team name helpers
# ---------------------------------------------------------------------------


def team_name_from_session(session_id: str) -> str:
    """Derive the team name from a session id.

    Per the Agent Teams docs, a team's name is ``"session-"`` + the first
    8 characters of the session id.

    Args:
        session_id: The Claude Code session identifier.

    Returns:
        ``"session-<session_id[:8]>"``
    """
    return "session-" + session_id[:8]


def extract_team_name(payload: dict[str, Any]) -> str | None:
    """Tolerantly extract the team name from a hook payload.

    Tries, in order:
    1. ``team_name`` field (ASSUMED, unverified)
    2. ``teamName`` field (ASSUMED, camelCase fallback, unverified)
    3. Derive from ``session_id`` (CONFIRMED snake_case)
    4. Derive from ``sessionId`` (ASSUMED camelCase fallback, unverified)

    Returns ``None`` if nothing resolves.
    """
    # Direct field — ASSUMED (unverified)
    direct = payload.get(_PAYLOAD_TEAM_NAME) or payload.get(_PAYLOAD_TEAM_NAME_CAMEL)
    if direct:
        return str(direct)

    # Derive from session_id
    session_id = (
        payload.get(_PAYLOAD_SESSION_ID)            # CONFIRMED via S1
        or payload.get(_PAYLOAD_SESSION_ID_CAMEL)   # ASSUMED (unverified)
    )
    if session_id:
        return team_name_from_session(str(session_id))

    return None


# ---------------------------------------------------------------------------
# Idempotent run creation
# ---------------------------------------------------------------------------


def ensure_team_run(
    team_name: str,
    *,
    skill_runs_base: Path | str | None = None,
    skill: str | None = None,
    session_id: str | None = None,
) -> RunDir:
    """Idempotently create or locate a substrate run for *team_name*.

    The substrate run id is ``team-<team_name>``.  If the run directory
    already exists it is reused without modification; if not, it is created
    with ``status="running"`` and an initial ``run_started`` event.

    Args:
        team_name: The correlated team name (``session-<8char>``).
        skill_runs_base: Override the skill-runs base directory (for tests).
        skill: Optional skill name to record in run-state.
        session_id: Optional session id to record in run-state.

    Returns:
        A :class:`RunDir` handle for the team run.
    """
    base = Path(skill_runs_base).expanduser() if skill_runs_base else rundir._resolve_base_dir()
    run_id = f"team-{team_name}"

    handle = find_run(run_id, base_dir=base)
    if handle is not None:
        return handle.as_run_dir()

    # Create the run directory and initial files.
    now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    run_dir = RunDir(run_id=run_id, base=base)
    run_dir.path.mkdir(parents=True, exist_ok=True)

    run_state: dict = {
        "run_id": run_id,
        "skill": skill or "agent-teams",
        "team_name": team_name,
        "session_id": session_id,
        "started_at": now_iso,
        "status": "running",
    }
    write_atomic(run_dir.run_state, run_state)
    run_dir.events_jsonl.touch()
    write_atomic(run_dir.projection, empty_projection())
    write_atomic(run_dir.manifest, {})
    run_dir.lockfile.touch()

    # Emit run_started exactly once (idempotent: we just created the run, so
    # no events exist yet; re-entrant callers hit the find_run branch above).
    run_started_ev = event_schema(
        type=EVENT_RUN_STARTED,
        run_id=run_id,
        payload={"skill": skill or "agent-teams", "team_name": team_name, "source": "teams_bridge"},
    )
    append_event(run_dir, run_started_ev)

    return run_dir


# ---------------------------------------------------------------------------
# Self-capture for format verification
# ---------------------------------------------------------------------------


def _debug_payloads_path(skill_runs_base: Path | str | None) -> Path:
    """Resolve the debug-capture file, sandboxed to the active skill-runs base.

    In production (base=None) this is ``~/.claude/skill-runs-debug/team-payloads.jsonl``;
    under a test/tmp base it sits alongside that base so tests NEVER write into the
    real ``~/.claude`` (mirrors how the quarantine log derives from the base).
    """
    base = Path(skill_runs_base).expanduser() if skill_runs_base else rundir._resolve_base_dir()
    return base.parent / "skill-runs-debug" / "team-payloads.jsonl"


def _capture_raw_payload(payload: dict[str, Any], skill_runs_base: Path | str | None = None) -> None:
    """Best-effort append the raw payload to the (base-scoped) debug capture file.

    This records the actual TaskCreated/TaskCompleted/TeammateIdle/SubagentStart/
    SubagentStop payload shapes on the next real teammate run so that the ASSUMED
    field names above (_PAYLOAD_TEAM_NAME, etc.) can be verified against reality
    and corrected with a one-line fix.

    Never raises — a write failure must never fail the hook.
    """
    import time
    # Never write the production debug capture during tests (bulletproof isolation):
    # the self-capture is a production-only field-verification aid.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        path = _debug_payloads_path(skill_runs_base)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), "payload": payload}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception:
        pass  # never fail the hook on a debug-write error


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def record_team_event(
    payload: dict[str, Any],
    *,
    skill_runs_base: Path | str | None = None,
) -> str | None:
    """Capture a team-related hook event into the durable substrate.

    This is the entrypoint called from ``run_event_hook`` when the standard
    run resolution fails (no CLAUDE_SKILL_RUN_ID and no registry match) but
    the payload looks like an Agent Teams event.

    Workflow:
    1. Best-effort write raw payload to the debug capture file (format
       verification — see ``_capture_raw_payload`` docstring).
    2. Extract the team name (tolerantly — returns None on failure).
    3. Ensure a substrate run exists for the team (idempotent).
    4. Normalize the payload via ``hook_adapter.normalize_hook_event``.
    5. Append the normalized event.
    6. Return the run_id (caller uses this to skip quarantine).

    Returns:
        The run_id string if the event was captured, or ``None`` if
        no team context could be resolved (caller should quarantine).

    Never raises — format-tolerant on any payload shape.
    """
    # Best-effort self-capture for field-name verification (step 1).
    _capture_raw_payload(payload, skill_runs_base)

    # Extract team name (step 2).
    team_name = extract_team_name(payload)
    if not team_name:
        return None

    session_id: str | None = (
        payload.get(_PAYLOAD_SESSION_ID)
        or payload.get(_PAYLOAD_SESSION_ID_CAMEL)  # ASSUMED (unverified)
    )

    try:
        # Ensure run directory (step 3).
        run_dir = ensure_team_run(
            team_name,
            skill_runs_base=skill_runs_base,
            session_id=session_id,
        )

        # Normalize payload (step 4).
        event = normalize_hook_event(payload, run_dir.run_id)
        if event is None:
            # Unknown hook type — not a team event we recognize; still return
            # the run_id so the caller does not quarantine.
            return run_dir.run_id

        if event is None:
            # normalize returned None (unknown hook type) — skip append but
            # still return run_id to avoid quarantine.
            return run_dir.run_id

        # Append event (step 5).
        append_event(run_dir, event)

    except Exception:
        log.warning("teams_bridge: record_team_event failed", exc_info=True)
        # Return None so the caller quarantines rather than silently dropping.
        return None

    return run_dir.run_id  # step 6


# ---------------------------------------------------------------------------
# Session-end: mark team runs completed
# ---------------------------------------------------------------------------


def mark_team_runs_completed(
    session_id: str,
    *,
    skill_runs_base: Path | str | None = None,
) -> None:
    """Mark all team runs for *session_id* as completed.

    Called from ``session_end_hook`` (alongside ``bridge_session_workflows``)
    so finished team runs stop being offered for resume and become eligible
    for TTL pruning.

    Derives the team_name from *session_id*, locates the corresponding run,
    and sets ``status="completed"`` + ``completed_at`` in ``run-state.json``.

    Non-fatal: errors are logged and swallowed.
    """
    if not session_id:
        return

    base = Path(skill_runs_base).expanduser() if skill_runs_base else rundir._resolve_base_dir()
    team_name = team_name_from_session(session_id)
    run_id = f"team-{team_name}"

    handle = find_run(run_id, base_dir=base)
    if handle is None:
        return  # no team run for this session — nothing to mark

    try:
        state_path = handle.run_state
        try:
            state: dict = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

        if state.get("status") == "completed":
            return  # already terminal

        now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        state["status"] = "completed"
        state.setdefault("completed_at", now_iso)
        write_atomic(state_path, state)
    except Exception:
        log.warning(
            "teams_bridge: mark_team_runs_completed failed for run_id=%r",
            run_id, exc_info=True,
        )
