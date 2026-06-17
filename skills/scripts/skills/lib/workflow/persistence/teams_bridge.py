#!/usr/bin/env python3
"""Bridge from Agent Teams events to the durable event substrate.

Two complementary sources feed a substrate run with id ``team-<team_name>``:

1. AUTHORITATIVE membership (C1 fix) — the runtime writes a readable,
   well-structured ``~/.claude/teams/<team_name>/config.json`` (keys: ``name``,
   ``createdAt``, ``leadAgentId``, ``leadSessionId``, ``members[]`` with
   ``agentId``/``name``/``agentType``/``joinedAt``/… and optional ``prompt``/
   ``model`` on teammates).  ``read_team_config`` reads it READ-ONLY and
   TOLERANTLY (the dir is runtime-owned and may be rewritten while live, so we
   never pre-author or mutate it) and emits a ``team_members`` event so the
   teammates projection carries the REAL ``name`` + ``agentType``.  This
   replaces guessing hook-payload field names (DL-015 native-first: the runtime
   already records this — don't reconstruct it from a null payload field).

2. IN-FLIGHT activity — TaskCreated, TaskCompleted, TeammateIdle, SubagentStart,
   and SubagentStop hook payloads captured LIVE from the stream give per-event
   visibility (task graph, idle transitions) the static config cannot.

Historical note (the C1 lesson): an earlier version claimed the teams dir had
"unknown format + reaped at session end" and relied solely on the hook stream.
That was an over-generalization made before any team had formed (the dirs were
merely *not yet populated*, not reaped). The dirs persist and the JSON is
authoritative; config.json is now the source of truth for membership.

Team name derivation (when a payload lacks an explicit name):
    team_name = "session-" + session_id[:8]   (matches config.json ``name``)

Correlation key: ``team_name``.  Run id prefix: ``team-``.

Design references: M-003, DL-002, DL-015, R-008, C1.
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
from .events import EVENT_RUN_STARTED, EVENT_TEAM_MEMBERS, event_schema
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
# Payload field names for Agent Teams events (R-008 / C1)
#
# session_id is CONFIRMED (S1 live capture). The team_name fields below were
# never observed in a real payload — the live path always derives the name from
# session_id, and AUTHORITATIVE membership now comes from config.json (see
# read_team_config), not from these. They are kept only as a harmless
# best-effort shortcut should a future runtime add an explicit field.
# ---------------------------------------------------------------------------

_PAYLOAD_TEAM_NAME = "team_name"       # best-effort: never observed in a real payload
_PAYLOAD_TEAM_NAME_CAMEL = "teamName"  # best-effort: camelCase variant, never observed
_PAYLOAD_SESSION_ID = "session_id"     # CONFIRMED via S1 (snake_case)
_PAYLOAD_SESSION_ID_CAMEL = "sessionId"  # best-effort: camelCase fallback

# config.json filename written by the runtime under ~/.claude/teams/<team_name>/.
_TEAM_CONFIG_FILENAME = "config.json"

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
# Authoritative team membership from config.json (C1)
# ---------------------------------------------------------------------------


def _resolve_teams_dir(
    skill_runs_base: Path | str | None = None,
    teams_base: Path | str | None = None,
) -> Path:
    """Resolve the runtime-owned teams directory (``~/.claude/teams``).

    Precedence:
    1. An explicit ``teams_base`` (used by tests for full isolation).
    2. Otherwise the skill-runs base's SIBLING ``teams`` dir — in production
       (base=None) this is ``~/.claude/teams``.

    Note: tests pass ``skill_runs_base=tmp_path`` directly, whose parent is the
    SHARED pytest root, so config-driven tests MUST pass ``teams_base`` to stay
    isolated; the sibling-derivation is correct only for the real layout.
    """
    if teams_base is not None:
        return Path(teams_base).expanduser()
    base = Path(skill_runs_base).expanduser() if skill_runs_base else rundir._resolve_base_dir()
    return base.parent / "teams"


def read_team_config(
    team_name: str,
    *,
    skill_runs_base: Path | str | None = None,
    teams_base: Path | str | None = None,
) -> dict[str, Any] | None:
    """Read the runtime-written ``<teams_dir>/<team_name>/config.json``.

    AUTHORITATIVE source of team membership and teammate identity (C1).
    READ-ONLY and TOLERANT: the directory is runtime-owned and may be rewritten
    while a team is live, so this never creates, pre-authors, or mutates it, and
    returns ``None`` on any absence/read/parse failure rather than raising.

    Args:
        team_name: The team name (``session-<8char>``); also the dir name.
        skill_runs_base: Override the skill-runs base; teams dir is its sibling.
        teams_base: Explicit teams directory (tests); takes precedence.

    Returns:
        The parsed config dict, or ``None`` if the file is absent, unreadable,
        not valid JSON, or not a JSON object.
    """
    if not team_name:
        return None
    try:
        path = _resolve_teams_dir(skill_runs_base, teams_base) / team_name / _TEAM_CONFIG_FILENAME
        if not path.is_file():
            return None
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) else None


def _config_members(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the ``members`` list from a config dict, tolerantly.

    Returns only the dict entries; a malformed ``members`` (absent, non-list,
    or non-dict entries) yields an empty list rather than raising.
    """
    members = cfg.get("members")
    if not isinstance(members, list):
        return []
    return [m for m in members if isinstance(m, dict)]


def _members_signature(members: list[dict[str, Any]]) -> tuple:
    """Stable signature of membership identity for change detection (idempotency).

    Captures only the authoritative identity fields so a ``team_members`` event
    is re-emitted ONLY when the roster actually changes (e.g. a teammate joins),
    not on every hook fire. Sorted so ordering differences do not spuriously
    trigger a re-emit.
    """
    sig = sorted(
        (
            str(m.get("name") or m.get("agentId") or m.get("agent_id") or ""),
            str(m.get("agentType") or m.get("agent_type") or ""),
            str(m.get("agentId") or m.get("agent_id") or ""),
        )
        for m in members
    )
    return tuple(sig)


def _last_recorded_members_signature(run_dir: RunDir) -> tuple | None:
    """Signature of the most recent ``team_members`` event already in the log.

    Returns ``None`` if no such event exists yet. Tolerant of a missing or
    unreadable event log (treated as "none recorded").
    """
    try:
        events = read_events(run_dir)
    except Exception:
        return None
    last: dict[str, Any] | None = None
    for ev in events:
        if ev.get("type") == EVENT_TEAM_MEMBERS:
            last = ev
    if last is None:
        return None
    payload = last.get("payload") or {}
    members = payload.get("members") or []
    members = [m for m in members if isinstance(m, dict)]
    return _members_signature(members)


def emit_team_members(
    team_name: str,
    run_dir: RunDir,
    *,
    skill_runs_base: Path | str | None = None,
    teams_base: Path | str | None = None,
) -> bool:
    """Read config.json and append a ``team_members`` event if the roster changed.

    Idempotent: appends nothing when config.json is absent/empty or when the
    membership signature matches the last recorded ``team_members`` event. This
    is the C1 enrichment path — the authoritative roster (real name + agentType)
    flows into the teammates projection via :func:`fold.fold`.

    Returns:
        ``True`` if a ``team_members`` event was appended, else ``False``.
    """
    cfg = read_team_config(team_name, skill_runs_base=skill_runs_base, teams_base=teams_base)
    if cfg is None:
        return False
    members = _config_members(cfg)
    if not members:
        return False

    new_sig = _members_signature(members)
    if new_sig == _last_recorded_members_signature(run_dir):
        return False  # roster unchanged — nothing to record

    lead_agent_id = cfg.get("leadAgentId") or cfg.get("lead_agent_id")
    event = event_schema(
        type=EVENT_TEAM_MEMBERS,
        run_id=run_dir.run_id,
        payload={
            "team_name": cfg.get("name") or team_name,
            "lead_agent_id": lead_agent_id,
            "lead_session_id": cfg.get("leadSessionId") or cfg.get("lead_session_id"),
            "members": members,
            "source": "config",
        },
    )
    append_event(run_dir, event)
    return True


# ---------------------------------------------------------------------------
# Idempotent run creation
# ---------------------------------------------------------------------------


def ensure_team_run(
    team_name: str,
    *,
    skill_runs_base: Path | str | None = None,
    teams_base: Path | str | None = None,
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
        # This is the Agent Teams capture path by definition, so the mode is a
        # constant here — it must still be recorded (third creation site) so
        # resume classifies team runs without re-reading the env var (DL-T1-01).
        "orchestration_mode": "agent_teams",
        "started_at": now_iso,
        "status": "running",
    }
    # C1: enrich run-state with authoritative lead identity from config.json
    # (read-only, tolerant — absent config leaves these unset).
    cfg = read_team_config(team_name, skill_runs_base=skill_runs_base, teams_base=teams_base)
    if cfg is not None:
        lead_session_id = cfg.get("leadSessionId") or cfg.get("lead_session_id")
        lead_agent_id = cfg.get("leadAgentId") or cfg.get("lead_agent_id")
        if lead_session_id:
            run_state["lead_session_id"] = lead_session_id
        if lead_agent_id:
            run_state["lead_agent_id"] = lead_agent_id
        if not run_state.get("session_id") and lead_session_id:
            run_state["session_id"] = lead_session_id
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

    # C1: seed the authoritative roster immediately so the teammates projection
    # is populated even before the first TeammateIdle hook fires (idempotent).
    emit_team_members(team_name, run_dir, skill_runs_base=skill_runs_base, teams_base=teams_base)

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


#: Opt-in gate for the raw-payload debug capture. Default OFF (DL-029): the
#: capture previously ran on every team hook, an unbounded-growth liability.
#: This is the one INTENTIONAL behavior change in Tier-3 — a future reader must
#: not "restore" the always-on behavior thinking the gate was a bug.
CLAUDE_SKILL_DEBUG_TEAMS_ENV: str = "CLAUDE_SKILL_DEBUG_TEAMS"

#: Defense-in-depth size cap: even when the gate is on, skip the append once the
#: capture file exceeds this size so a forgotten debug session cannot grow it
#: without bound. Overridable per call for tests.
CLAUDE_SKILL_DEBUG_TEAMS_CAP_BYTES: int = 50 * 1024 * 1024  # 50 MB


def _capture_raw_payload(
    payload: dict[str, Any],
    skill_runs_base: Path | str | None = None,
    *,
    cap_bytes: int = CLAUDE_SKILL_DEBUG_TEAMS_CAP_BYTES,
) -> None:
    """Best-effort append the raw payload to the (base-scoped) debug capture file.

    Gated and bounded (DL-029):

    - Writes ONLY when ``CLAUDE_SKILL_DEBUG_TEAMS=1`` (default OFF), mirroring the
      ``os.environ.get`` idiom in ``team_mode.py``/``resume.py``. The default is
      intentionally OFF — the previous always-on capture was an unbounded-growth
      liability with diagnostic value only when a Teams-hook payload bug is being
      investigated.
    - Even when enabled, the append is skipped once the target file exceeds
      ``cap_bytes`` (default 50 MB) so a re-enabled-and-forgotten capture cannot
      grow without bound.

    When enabled, it records the actual TaskCreated/TaskCompleted/TeammateIdle/
    SubagentStart/SubagentStop payload shapes so the ASSUMED field names above
    (_PAYLOAD_TEAM_NAME, etc.) can be verified against reality.

    Never raises — a write failure must never fail the hook.
    """
    import time
    # Never write the production debug capture during tests (bulletproof isolation):
    # the self-capture is a production-only field-verification aid.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    # Opt-in gate (default OFF): absent or non-"1" value means do nothing.
    if os.environ.get(CLAUDE_SKILL_DEBUG_TEAMS_ENV) != "1":
        return
    try:
        path = _debug_payloads_path(skill_runs_base)
        # Size cap: skip the append once the file is already over the cap.
        if path.exists() and path.stat().st_size > cap_bytes:
            return
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
    teams_base: Path | str | None = None,
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
            teams_base=teams_base,
            session_id=session_id,
        )

        # Refresh authoritative roster (C1): re-read config.json so a teammate
        # that joined AFTER run creation is captured. No-op when unchanged.
        emit_team_members(team_name, run_dir, skill_runs_base=skill_runs_base, teams_base=teams_base)

        # Normalize payload (step 4).
        event = normalize_hook_event(payload, run_dir.run_id)
        if event is None:
            # Unknown hook type — not a team event we recognize. Still return the
            # run_id so the caller does not quarantine (the roster refresh above
            # may already have recorded useful membership data).
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
