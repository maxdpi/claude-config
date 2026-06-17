#!/usr/bin/env python3
"""Durable substrate — persistence core (M-001).

Public API
----------
All WORKFLOW-LEVEL event-sourcing primitives for skill runs:

    from skills.lib.workflow.persistence import (
        write_atomic,
        event_schema,
        EVENT_SUBAGENT_SPAWNED, EVENT_SUBAGENT_COMPLETED,
        EVENT_PHASE_STARTED, EVENT_PHASE_COMPLETED,
        EVENT_MILESTONE_STATUS,
        EVENT_RUN_STARTED, EVENT_RUN_COMPLETED, EVENT_RUN_FAILED,
        EVENT_RESUME_CURSOR,
        empty_projection, fold,
        create_run_dir, RunDir,
        append_event,
        replay, verify_projection,
        write_phase_manifest, read_manifest,
    )

Design invariants (C-004, C-005, DL-003, DL-004, DL-016)
---------------------------------------------------------
* LLM-facing agents write ``.md``; this layer is the sole writer of ``.json``.
* All ``.json`` writes are atomic (tmp + os.rename via ``write_atomic``).
* ``fold`` is pure and tolerant of unknown event types / fields.
* ``events.jsonl`` is append-only, never rewritten.
* WORKFLOW-LEVEL events only — no duplication of native per-subagent transcripts.
"""
from __future__ import annotations

from .atomic import write_atomic
from .eventlog import append_event, read_events
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
    event_schema,
)
from .fold import empty_projection, fold
from .manifest import read_manifest, write_phase_manifest
from .projection import replay, verify_projection
from .rundir import RunDir, create_run_dir
from .teams_bridge import (
    ensure_team_run,
    extract_team_name,
    mark_team_runs_completed,
    record_team_event,
    team_name_from_session,
)

__all__ = [
    # atomic
    "write_atomic",
    # events
    "event_schema",
    "EVENT_SUBAGENT_SPAWNED",
    "EVENT_SUBAGENT_COMPLETED",
    "EVENT_TASK_CREATED",
    "EVENT_TASK_COMPLETED",
    "EVENT_TEAMMATE_IDLE",
    "EVENT_PHASE_STARTED",
    "EVENT_PHASE_COMPLETED",
    "EVENT_MILESTONE_STATUS",
    "EVENT_RUN_STARTED",
    "EVENT_RUN_COMPLETED",
    "EVENT_RUN_FAILED",
    "EVENT_RESUME_CURSOR",
    # fold
    "empty_projection",
    "fold",
    # rundir
    "RunDir",
    "create_run_dir",
    # eventlog
    "append_event",
    "read_events",
    # projection
    "replay",
    "verify_projection",
    # manifest
    "write_phase_manifest",
    "read_manifest",
    # teams_bridge
    "team_name_from_session",
    "extract_team_name",
    "ensure_team_run",
    "record_team_event",
    "mark_team_runs_completed",
]
