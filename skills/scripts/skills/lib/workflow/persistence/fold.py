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
    EVENT_TASK_CREATED,
    EVENT_TASK_COMPLETED,
    EVENT_TEAMMATE_IDLE,
    EVENT_TEAM_MEMBERS,
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
        "tasks": {},
        "teammates": {},
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
    # Rebind to the working copy: the input is never mutated (C-005); all
    # mutations below land on this deep copy.
    projection = copy.deepcopy(projection)
    etype = event.get("type")

    if etype == EVENT_RUN_STARTED:
        projection["run_id"] = event.get("run_id") or projection["run_id"]
        projection["status"] = "running"
        payload = event.get("payload") or {}
        if "skill" in payload:
            projection["skill"] = payload["skill"]

    elif etype == EVENT_RUN_COMPLETED:
        projection["status"] = "completed"

    elif etype == EVENT_RUN_FAILED:
        projection["status"] = "failed"
        payload = event.get("payload") or {}
        if "error" in payload:
            projection["error"] = payload["error"]

    elif etype == EVENT_PHASE_STARTED:
        payload = event.get("payload") or {}
        phase_id = payload.get("phase_id") or payload.get("phase")
        if phase_id:
            entry = projection["phases"].get(phase_id, {})
            entry["status"] = "running"
            if "started_at" not in entry:
                entry["started_at"] = event.get("ts")
            projection["phases"][phase_id] = entry

    elif etype == EVENT_PHASE_COMPLETED:
        payload = event.get("payload") or {}
        phase_id = payload.get("phase_id") or payload.get("phase")
        if phase_id:
            entry = projection["phases"].get(phase_id, {})
            entry["status"] = "completed"
            entry["completed_at"] = event.get("ts")
            if "result" in payload:
                entry["result"] = payload["result"]
            projection["phases"][phase_id] = entry

    elif etype == EVENT_MILESTONE_STATUS:
        payload = event.get("payload") or {}
        milestone_id = payload.get("milestone_id") or payload.get("milestone")
        if milestone_id:
            entry = projection["milestones"].get(milestone_id, {})
            if "status" in payload:
                entry["status"] = payload["status"]
            if "ts" not in entry:
                entry["ts"] = event.get("ts")
            projection["milestones"][milestone_id] = entry

    elif etype == EVENT_RESUME_CURSOR:
        payload = event.get("payload") or {}
        projection["resume_cursor"] = payload.get("cursor")

    elif etype == EVENT_SUBAGENT_SPAWNED:
        # NAMESPACE NOTE (I3): for subagent events the envelope's ``agent_id`` IS
        # the NATIVE Claude Code agent id (hook_adapter sets agent_id ==
        # native_agent_id).  The ``subagents`` map is therefore keyed by the
        # native id, and ``native_agent_id`` is also stored explicitly in the
        # entry so a consumer never has to infer which namespace the key holds.
        agent_id = event.get("agent_id")
        if agent_id:
            entry = projection["subagents"].get(agent_id, {})
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
            for key, value in payload.items():
                entry.setdefault(key, value)

            projection["subagents"][agent_id] = entry

    elif etype == EVENT_SUBAGENT_COMPLETED:
        # See the namespace note on EVENT_SUBAGENT_SPAWNED (I3): the key is the
        # native agent id, and the native id is never written back over a
        # different namespace — it stays in ``native_agent_id``.
        agent_id = event.get("agent_id")
        if agent_id:
            entry = projection["subagents"].get(agent_id, {})
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
            projection["subagents"][agent_id] = entry

    elif etype == EVENT_TASK_CREATED:
        # Agent Teams task graph: record task as pending/in_progress.
        # Field names are ASSUMED (unverified) — see hook_adapter._PAYLOAD_TASK_ID.
        payload = event.get("payload") or {}
        task_id = payload.get("task_id")  # ASSUMED (unverified)
        if task_id:
            entry = projection["tasks"].get(task_id, {})
            entry["status"] = "in_progress"
            entry.setdefault("title", payload.get("title") or "")  # ASSUMED (unverified)
            entry.setdefault("created_at", event.get("ts"))
            projection["tasks"][task_id] = entry

    elif etype == EVENT_TASK_COMPLETED:
        # Agent Teams task graph: transition task to completed.
        payload = event.get("payload") or {}
        task_id = payload.get("task_id")  # ASSUMED (unverified)
        if task_id:
            entry = projection["tasks"].get(task_id, {})
            entry["status"] = "completed"
            entry["completed_at"] = event.get("ts")
            projection["tasks"][task_id] = entry

    elif etype == EVENT_TEAMMATE_IDLE:
        # Agent Teams: record teammate idle state.
        # Field names are ASSUMED (unverified) — see hook_adapter._PAYLOAD_TEAMMATE_ID.
        payload = event.get("payload") or {}
        teammate_id = payload.get("teammate_id")  # ASSUMED (unverified)
        if teammate_id:
            entry = projection["teammates"].get(teammate_id, {})
            entry["status"] = "idle"
            entry["idle_at"] = event.get("ts")
            for key, value in payload.items():
                entry.setdefault(key, value)
            projection["teammates"][teammate_id] = entry

    elif etype == EVENT_TEAM_MEMBERS:
        # Authoritative team membership from ~/.claude/teams/<name>/config.json
        # (C1 fix). Keyed by the REAL member name; identity fields (name,
        # agent_type, agent_id, lead) are authoritative and overwrite any prior
        # guess, while best-effort state (e.g. idle_at from TeammateIdle) is
        # preserved via the existing entry.
        payload = event.get("payload") or {}
        members = payload.get("members") or []
        lead_agent_id = payload.get("lead_agent_id")
        for member in members:
            if not isinstance(member, dict):
                continue
            name = member.get("name") or member.get("agent_id") or member.get("agentId")
            if not name:
                continue
            entry = projection["teammates"].get(name, {})
            entry["name"] = name
            entry["agent_type"] = member.get("agentType") or member.get("agent_type")
            entry["agent_id"] = member.get("agentId") or member.get("agent_id")
            entry["source"] = "config"
            agent_id = entry["agent_id"]
            entry["is_lead"] = bool(lead_agent_id) and agent_id == lead_agent_id
            entry.setdefault("status", "active")
            projection["teammates"][name] = entry

    # Unknown event types: return projection unchanged (C-005, forward-compat).
    return projection
