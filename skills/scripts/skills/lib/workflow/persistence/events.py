#!/usr/bin/env python3
"""Stable WORKFLOW-LEVEL event envelope and event-type constants.

Design notes
------------
* The envelope carries only WORKFLOW-LEVEL information (phase transitions,
  milestone status, resume cursor, subagent spawn/stop correlation).  It
  does NOT duplicate per-subagent turns — those live in the native
  transcripts (DL-015, DL-016).
* Native-correlation fields (``native_agent_id``, ``native_session_id``,
  ``parent_agent_id``, ``depth``) are DEFINED here but populated by the
  M-003 SubagentStart hook adapter.  M-001 never populates them (DL-022).
* The envelope is a tolerant container: extra payload keys are preserved
  and unknown event types are silently accepted (C-005).
"""
from __future__ import annotations

import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Event-type constants
# ---------------------------------------------------------------------------

EVENT_SUBAGENT_SPAWNED: str = "subagent_spawned"
EVENT_SUBAGENT_COMPLETED: str = "subagent_completed"
EVENT_PHASE_STARTED: str = "phase_started"
EVENT_PHASE_COMPLETED: str = "phase_completed"
EVENT_MILESTONE_STATUS: str = "milestone_status"
EVENT_RUN_STARTED: str = "run_started"
EVENT_RUN_COMPLETED: str = "run_completed"
EVENT_RUN_FAILED: str = "run_failed"
EVENT_RESUME_CURSOR: str = "resume_cursor"

# ---------------------------------------------------------------------------
# Envelope builder
# ---------------------------------------------------------------------------

_SENTINEL = object()


def event_schema(
    type: str,  # noqa: A002 — mirrors the envelope field name
    run_id: str,
    payload: dict[str, Any] | None = None,
    agent_id: str | None = None,
    ts: float | None = None,
    # Native-correlation fields — DEFINED here, POPULATED by M-003 only (DL-022).
    native_agent_id: str | None = None,
    native_session_id: str | None = None,
    parent_agent_id: str | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    """Build a WORKFLOW-LEVEL event envelope.

    Args:
        type: One of the EVENT_* constants (or any string — forward-compat).
        run_id: The durable run identifier this event belongs to.
        payload: Arbitrary extra data.  Extra keys are preserved by the fold.
        agent_id: Optional skill-internal agent identifier (not the native id).
        ts: Unix timestamp; defaults to ``time.time()``.
        native_agent_id: Native Claude Code agentId — M-003 ONLY (DL-022).
        native_session_id: Native Claude Code sessionId — M-003 ONLY (DL-022).
        parent_agent_id: Native agentId of the spawning parent — M-003 ONLY.
        depth: Nesting depth in the subagent tree — M-003 ONLY.

    Returns:
        A dict conforming to the stable envelope schema.  The ``id`` field
        is a random UUID so each event can be uniquely identified.
    """
    return {
        "id": str(uuid.uuid4()),
        "type": type,
        "ts": ts if ts is not None else time.time(),
        "run_id": run_id,
        "agent_id": agent_id,
        # Native-correlation fields (M-003 populates; None until then).
        "native_agent_id": native_agent_id,
        "native_session_id": native_session_id,
        "parent_agent_id": parent_agent_id,
        "depth": depth,
        # Payload is a tolerant bag — extra keys pass through fold unchanged.
        "payload": payload or {},
    }
