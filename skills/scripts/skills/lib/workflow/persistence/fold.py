#!/usr/bin/env python3
"""Pure WORKFLOW-LEVEL projection fold.

Design constraints
------------------
* PURE: no I/O, no mutation of inputs, no side effects (C-005).
* TOLERANT: unknown event types and unknown payload fields return the
  projection UNCHANGED — forward-compatible with evolving hook payloads
  (C-005, R-001).
* WORKFLOW-LEVEL ONLY: fold tracks phases, milestones, a resume cursor,
  and subagent spawn/stop correlation (native transcript pointer + parent/
  depth edges).  It does NOT fold per-subagent turns (DL-015, DL-016).

Native-correlation handling (DL-022)
--------------------------------------
``subagent_spawned`` events carry ``native_agent_id`` / ``native_session_id``
populated by the M-003 hook.  If ``native_agent_id`` is ``None`` the event is
still accepted but a ``_warnings`` list is appended to the projection entry
to signal that the correlation is incomplete.  M-001 defines the field;
M-003 is the sole producer.
"""
from __future__ import annotations

import copy
from typing import Any

from .events import (
    EVENT_MILESTONE_STATUS,
    EVENT_PHASE_COMPLETED,
    EVENT_PHASE_STARTED,
    EVENT_RESUME_CURSOR,
    EVENT_RUN_COMPLETED,
    EVENT_RUN_FAILED,
    EVENT_RUN_STARTED,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_SUBAGENT_SPAWNED,
)

# ---------------------------------------------------------------------------
# Empty projection factory
# ---------------------------------------------------------------------------


def empty_projection() -> dict[str, Any]:
    """Return the zero-state projection that ``fold`` reduces into."""
    return {
        "run_id": None,
        "status": "pending",
        "phases": {},
        "milestones": {},
        "resume_cursor": None,
        "subagents": {},
    }


# ---------------------------------------------------------------------------
# Fold
# ---------------------------------------------------------------------------


def fold(projection: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Reduce *projection* by one *event*, returning a new projection.

    The input projection is NEVER mutated; a deep-copy is taken at the start.
    Unknown event ``type`` values and unknown fields are silently ignored so
    the fold remains forward-compatible as new event types are added (C-005).

    Args:
        projection: Current projection dict (use ``empty_projection()`` to
            start a fresh reduction chain).
        event: A single event envelope as produced by ``event_schema()``.

    Returns:
        A new projection dict reflecting the event.
    """
    p = copy.deepcopy(projection)
    etype = event.get("type")

    if etype == EVENT_RUN_STARTED:
        p["run_id"] = event.get("run_id") or p["run_id"]
        p["status"] = "running"
        payload = event.get("payload") or {}
        if "skill" in payload:
            p["skill"] = payload["skill"]

    elif etype == EVENT_RUN_COMPLETED:
        p["status"] = "completed"

    elif etype == EVENT_RUN_FAILED:
        p["status"] = "failed"
        payload = event.get("payload") or {}
        if "error" in payload:
            p["error"] = payload["error"]

    elif etype == EVENT_PHASE_STARTED:
        payload = event.get("payload") or {}
        phase_id = payload.get("phase_id") or payload.get("phase")
        if phase_id:
            entry = p["phases"].get(phase_id, {})
            entry["status"] = "running"
            if "started_at" not in entry:
                entry["started_at"] = event.get("ts")
            p["phases"][phase_id] = entry

    elif etype == EVENT_PHASE_COMPLETED:
        payload = event.get("payload") or {}
        phase_id = payload.get("phase_id") or payload.get("phase")
        if phase_id:
            entry = p["phases"].get(phase_id, {})
            entry["status"] = "completed"
            entry["completed_at"] = event.get("ts")
            if "result" in payload:
                entry["result"] = payload["result"]
            p["phases"][phase_id] = entry

    elif etype == EVENT_MILESTONE_STATUS:
        payload = event.get("payload") or {}
        mid = payload.get("milestone_id") or payload.get("milestone")
        if mid:
            entry = p["milestones"].get(mid, {})
            if "status" in payload:
                entry["status"] = payload["status"]
            if "ts" not in entry:
                entry["ts"] = event.get("ts")
            p["milestones"][mid] = entry

    elif etype == EVENT_RESUME_CURSOR:
        payload = event.get("payload") or {}
        p["resume_cursor"] = payload.get("cursor")

    elif etype == EVENT_SUBAGENT_SPAWNED:
        aid = event.get("agent_id")
        if aid:
            entry = p["subagents"].get(aid, {})
            entry["status"] = "spawned"
            entry["spawned_at"] = event.get("ts")

            native_agent_id = event.get("native_agent_id")
            native_session_id = event.get("native_session_id")
            parent_agent_id = event.get("parent_agent_id")
            depth = event.get("depth")

            # Correlation fields — populated by M-003; may be None in M-001.
            entry["native_agent_id"] = native_agent_id
            entry["native_session_id"] = native_session_id
            entry["parent_agent_id"] = parent_agent_id
            entry["depth"] = depth

            if native_agent_id is None:
                # DL-022: quarantine marker — correlation incomplete; M-003 must populate.
                warnings = entry.get("_warnings", [])
                warnings.append(
                    "native_agent_id is None — correlation incomplete; "
                    "M-003 SubagentStart hook must populate this field (DL-022)."
                )
                entry["_warnings"] = warnings

            payload = event.get("payload") or {}
            for k, v in payload.items():
                entry.setdefault(k, v)

            p["subagents"][aid] = entry

    elif etype == EVENT_SUBAGENT_COMPLETED:
        aid = event.get("agent_id")
        if aid:
            entry = p["subagents"].get(aid, {})
            entry["status"] = "completed"
            entry["completed_at"] = event.get("ts")
            payload = event.get("payload") or {}
            if "result" in payload:
                entry["result"] = payload["result"]
            # Preserve native-transcript pointer if supplied at completion.
            if "native_agent_id" in payload:
                entry["native_agent_id"] = payload["native_agent_id"]
            if "native_session_id" in payload:
                entry["native_session_id"] = payload["native_session_id"]
            p["subagents"][aid] = entry

    # Unknown event types: return projection unchanged (C-005, forward-compat).
    return p
