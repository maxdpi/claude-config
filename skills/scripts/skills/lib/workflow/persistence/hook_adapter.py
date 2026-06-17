#!/usr/bin/env python3
"""Hook payload normalization: map Claude Code hook payloads to SkillEvent dicts.

Single normalization point (DL-002/DL-003): fold() and the rest of the substrate
stay payload-shape-agnostic.  All Claude Code hook payload translation lives here
so a field-name change in the runtime is a ONE-LINE fix in this file.

NATIVE CORRELATION PRODUCER (DL-022)
--------------------------------------
``normalize_hook_event`` is the SOLE producer of ``native_agent_id`` and
``native_session_id`` values in SubagentStart events.  M-001 only DEFINES
the schema fields; this module fills them from the live hook payload.

A SubagentStart payload with no resolvable ``native_agent_id`` (the field is
absent or None) is QUARANTINED: ``normalize_hook_event`` returns ``None``
and the entrypoint MUST log a WARNING and write to the quarantine log rather
than appending a null-correlated spawn record.

ASSUMED PAYLOAD FIELD NAMES (R-008)
--------------------------------------
These names are NOT confirmed by a live SubagentStart/SubagentStop hook fire
in M-000.  They are derived from the A4 transcript probe result, which
confirmed that native transcript records carry:

  - ``agentId``    — the native subagent identifier
  - ``sessionId``  — the native session identifier

Hook payload field names are assumed to match the transcript record names.
If the runtime uses different names (e.g. ``agent_id`` snake_case), update
``_SUBAGENT_START_FIELDS`` and ``_SUBAGENT_STOP_FIELDS`` — the rest of the
substrate is unaffected (DL-022/R-008).
"""
from __future__ import annotations

import logging
from typing import Any

from .events import (
    EVENT_SUBAGENT_SPAWNED,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_COMPLETED,
    EVENT_TEAMMATE_IDLE,
    event_schema,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SINGLE NORMALIZATION POINT (R-008)
#
# Assumed SubagentStart payload field names (source: A4 probe result showing
# transcript records carry agentId + sessionId; hook payload field names are
# assumed to match).  Change these constants -- not any other code -- if the
# runtime uses different names.
# ---------------------------------------------------------------------------

# Fields the SubagentStart/SubagentStop payloads carry. CONFIRMED by the S1
# live-capture probe (R-008, 2026-06-16): Claude Code uses snake_case, NOT the
# camelCase that the A4 *transcript records* use. Change these constants -- not
# any other code -- if a future runtime uses different names.
#   agent_id       — native subagent identifier (the correlation join key);
#                    matches the agent-<id>.jsonl filename (A4 join holds)
#   session_id     — native session identifier
#   parentAgentId  — NOT emitted by current CC (confirmed absent); absent = top-level
#   depth          — NOT emitted by current CC (confirmed absent); absent = 0
_PAYLOAD_AGENT_ID = "agent_id"          # CONFIRMED via S1 live capture (was "agentId")
_PAYLOAD_SESSION_ID = "session_id"      # CONFIRMED via S1 live capture (was "sessionId")
_PAYLOAD_PARENT_AGENT_ID = "parentAgentId"  # confirmed absent in current CC; kept for forward-compat
_PAYLOAD_DEPTH = "depth"                    # confirmed absent in current CC; default 0

# SubagentStop carries TWO transcript paths (confirmed via S1):
#   transcript_path        — the PARENT SESSION transcript (NOT the subagent's)
#   agent_transcript_path  — the SUBAGENT's own transcript at
#                            .../subagents/agent-<id>.jsonl  <-- copy-on-stop target (DL-016)
# Copy-on-stop MUST use agent_transcript_path; transcript_path points at the wrong file.
_PAYLOAD_AGENT_TRANSCRIPT_PATH = "agent_transcript_path"  # CONFIRMED via S1; subagent transcript
_PAYLOAD_TRANSCRIPT_PATH = "transcript_path"  # parent session transcript; NOT used for copy-on-stop

# TaskCreated / TaskCompleted assumed field names:
_PAYLOAD_TASK_ID = "task_id"
_PAYLOAD_TITLE = "title"

# TeammateIdle assumed field names:
_PAYLOAD_TEAMMATE_ID = "teammate_id"

# ---------------------------------------------------------------------------
# Public sentinel
# ---------------------------------------------------------------------------

#: Returned by ``normalize_hook_event`` when the SubagentStart payload carries
#: no resolvable ``native_agent_id``.  The entrypoint MUST quarantine rather
#: than append this as a null-correlated spawn record (DL-022).
QUARANTINE: None = None


# ---------------------------------------------------------------------------
# normalize_hook_event — SINGLE normalization point
# ---------------------------------------------------------------------------


def normalize_hook_event(
    payload: dict[str, Any],
    run_id: str,
) -> dict[str, Any] | None:
    """Map a Claude Code hook payload to the stable SkillEvent envelope.

    Args:
        payload: Raw hook payload dict parsed from stdin.  MUST contain a
            ``hook_event_name`` (or ``hookEventName``) key identifying the
            hook type.  Unknown fields are dropped.
        run_id: Durable run identifier to stamp on the produced event.

    Returns:
        A SkillEvent dict ready for ``eventlog.append_event``, or ``None``
        (``QUARANTINE``) if the event should not be appended:
          - Unknown hook type -> None (silently skipped, not quarantined).
          - SubagentStart with no resolvable native_agent_id -> None +
            caller MUST warn and quarantine (DL-022).

    Notes:
        The hook type is read from ``hook_event_name`` (snake_case CC
        convention) with a fallback to ``hookEventName`` (camelCase).
        Unknown payload fields are dropped so the stable envelope is all
        fold() needs.
    """
    hook_type = payload.get("hook_event_name") or payload.get("hookEventName", "")

    if hook_type == "SubagentStart":
        return _normalize_subagent_start(payload, run_id)

    if hook_type == "SubagentStop":
        return _normalize_subagent_stop(payload, run_id)

    if hook_type == "TaskCreated":
        return _normalize_task_created(payload, run_id)

    if hook_type == "TaskCompleted":
        return _normalize_task_completed(payload, run_id)

    if hook_type == "TeammateIdle":
        return _normalize_teammate_idle(payload, run_id)

    log.debug("normalize_hook_event: unknown hook type %r -- skipping", hook_type)
    return None


# ---------------------------------------------------------------------------
# Per-hook normalizers
# ---------------------------------------------------------------------------


def _normalize_subagent_start(raw: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    """SubagentStart -> EVENT_SUBAGENT_SPAWNED.

    Extracts native_agent_id from the ``agentId`` field (R-008 assumed name,
    confirmed in A4 transcript records).  Returns QUARANTINE (None) if
    native_agent_id cannot be extracted so the entrypoint can warn + quarantine
    rather than appending a null-correlated spawn record (DL-022).
    """
    native_agent_id: str | None = raw.get(_PAYLOAD_AGENT_ID) or None
    if not native_agent_id:
        # DL-022: quarantine -- a null-correlated spawn record is worse than
        # a quarantine entry because resume age-guard (DL-020) would fail open.
        log.warning(
            "normalize_hook_event: SubagentStart payload has no %r field "
            "(or it is None/empty) -- signalling QUARANTINE (DL-022).  "
            "Assumed field name: %r.  If the runtime uses a different name, "
            "update _PAYLOAD_AGENT_ID in hook_adapter.py.",
            _PAYLOAD_AGENT_ID, _PAYLOAD_AGENT_ID,
        )
        return QUARANTINE

    native_session_id: str | None = raw.get(_PAYLOAD_SESSION_ID) or None
    parent_agent_id: str | None = raw.get(_PAYLOAD_PARENT_AGENT_ID) or None
    depth: int = int(raw.get(_PAYLOAD_DEPTH) or 0)

    return event_schema(
        type=EVENT_SUBAGENT_SPAWNED,
        run_id=run_id,
        agent_id=native_agent_id,
        native_agent_id=native_agent_id,
        native_session_id=native_session_id,
        parent_agent_id=parent_agent_id,
        depth=depth,
        payload={
            "native_agent_id": native_agent_id,
            "native_session_id": native_session_id,
            "parent_agent_id": parent_agent_id,
            "depth": depth,
        },
    )


def _normalize_subagent_stop(raw: dict[str, Any], run_id: str) -> dict[str, Any]:
    """SubagentStop -> EVENT_SUBAGENT_COMPLETED.

    Carries the SUBAGENT's own transcript path (``agent_transcript_path``) for
    copy-on-stop (DL-016). The plain ``transcript_path`` field is the PARENT
    session transcript and must NOT be used as the copy source. When the
    subagent path is absent, copy-on-stop logic in run_event_hook derives it
    from session_id+agent_id.
    """
    native_agent_id: str | None = raw.get(_PAYLOAD_AGENT_ID) or None
    native_session_id: str | None = raw.get(_PAYLOAD_SESSION_ID) or None
    transcript_path: str | None = raw.get(_PAYLOAD_AGENT_TRANSCRIPT_PATH) or None

    return event_schema(
        type=EVENT_SUBAGENT_COMPLETED,
        run_id=run_id,
        agent_id=native_agent_id,
        native_agent_id=native_agent_id,
        native_session_id=native_session_id,
        payload={
            "native_agent_id": native_agent_id,
            "native_session_id": native_session_id,
            "transcript_path": transcript_path,
        },
    )


def _normalize_task_created(raw: dict[str, Any], run_id: str) -> dict[str, Any]:
    """TaskCreated -> EVENT_TASK_CREATED."""
    return event_schema(
        type=EVENT_TASK_CREATED,
        run_id=run_id,
        agent_id=raw.get(_PAYLOAD_TASK_ID),
        payload={
            "task_id": raw.get(_PAYLOAD_TASK_ID),
            "title": raw.get(_PAYLOAD_TITLE) or "",
            "session_id": raw.get(_PAYLOAD_SESSION_ID),
        },
    )


def _normalize_task_completed(raw: dict[str, Any], run_id: str) -> dict[str, Any]:
    """TaskCompleted -> EVENT_TASK_COMPLETED."""
    return event_schema(
        type=EVENT_TASK_COMPLETED,
        run_id=run_id,
        agent_id=raw.get(_PAYLOAD_TASK_ID),
        payload={
            "task_id": raw.get(_PAYLOAD_TASK_ID),
            "session_id": raw.get(_PAYLOAD_SESSION_ID),
        },
    )


def _normalize_teammate_idle(raw: dict[str, Any], run_id: str) -> dict[str, Any]:
    """TeammateIdle -> EVENT_TEAMMATE_IDLE.

    The teammate-identifier field name is UNVERIFIED (the live S5 run showed
    `teammate_id` is absent — value null — and the payload was not preserved).
    Extract tolerantly across candidate names; the production self-capture
    (team-payloads.jsonl) records the real payload so the true name can be pinned.
    """
    teammate_id = (
        raw.get(_PAYLOAD_TEAMMATE_ID)        # ASSUMED "teammate_id" (null in live run)
        or raw.get(_PAYLOAD_AGENT_ID)        # "agent_id" (teammates are agents)
        or raw.get("agentId")                # camelCase fallback
        or raw.get("teammate")               # candidate
        or raw.get("teammate_name")          # candidate
        or raw.get("name")                   # candidate
        or raw.get("member")                 # candidate
    )
    return event_schema(
        type=EVENT_TEAMMATE_IDLE,
        run_id=run_id,
        agent_id=teammate_id,
        payload={
            "teammate_id": teammate_id,
            "session_id": raw.get(_PAYLOAD_SESSION_ID),
        },
    )
