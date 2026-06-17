#!/usr/bin/env python3
"""Tests for the Agent Teams durable-substrate bridge (teams_bridge.py).

FIELD NAME STATUS: UNVERIFIED pending a real teammate run
---------------------------------------------------------
All hook payload field names extracted in teams_bridge and hook_adapter are
ASSUMED (not confirmed by a live Agent Teams hook fire). The fixtures below
use those assumed names. When a real teammate run fires and
~/.claude/skill-runs-debug/team-payloads.jsonl is populated, compare the
captured field names against the constants in hook_adapter.py and
teams_bridge.py and update as needed (one-line fixes per constant).

Assumed names under test:
  team_name       -- direct team correlation key (teams_bridge._PAYLOAD_TEAM_NAME)
  teamName        -- camelCase fallback          (teams_bridge._PAYLOAD_TEAM_NAME_CAMEL)
  session_id      -- session id (confirmed S1)   (_PAYLOAD_SESSION_ID)
  sessionId       -- camelCase fallback           (teams_bridge._PAYLOAD_SESSION_ID_CAMEL)
  task_id         -- task identifier              (hook_adapter._PAYLOAD_TASK_ID)
  title           -- task title                   (hook_adapter._PAYLOAD_TITLE)
  teammate_id     -- teammate identifier          (hook_adapter._PAYLOAD_TEAMMATE_ID)

Validates:
  T1. team-<name> run dir is created by record_team_event.
  T2. events.jsonl has correctly-typed events.
  T3. projection["tasks"] reflects task graph (created->in_progress->completed).
  T4. projection["teammates"] populated by TeammateIdle.
  T5. Idempotent: re-feeding run_started is not duplicated.
  T6. mark_team_runs_completed flips status=completed + completed_at.
  T7. Payload with NO team_name returns None (caller quarantines).
  T8. Unknown/extra payload fields are tolerated (no raise).
  T9. SubagentStart/Stop payloads with a session_id are captured via derived team_name.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).parent.parent
_SCRIPTS = _WORKTREE / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence.eventlog import read_events
from skills.lib.workflow.persistence.registry import find_run
from skills.lib.workflow.persistence.teams_bridge import (
    ensure_team_run,
    extract_team_name,
    mark_team_runs_completed,
    record_team_event,
    team_name_from_session,
)
from skills.lib.workflow.persistence.events import (
    EVENT_RUN_STARTED,
    EVENT_TASK_CREATED,
    EVENT_TASK_COMPLETED,
    EVENT_TEAMMATE_IDLE,
    EVENT_SUBAGENT_SPAWNED,
    EVENT_SUBAGENT_COMPLETED,
)


# ---------------------------------------------------------------------------
# Fixture payload helpers
# All field names here are ASSUMED (unverified) — marked inline.
# ---------------------------------------------------------------------------

_TEAM_NAME = "session-abcd1234"  # ASSUMED team name format
_SESSION_ID = "abcd1234-efgh-5678-ijkl-mnopqrstuvwx"  # session id that derives _TEAM_NAME
_TASK_ID = "task-001"
_TEAMMATE_ID = "agent-verifier"


def _task_created_payload(
    team_name: str = _TEAM_NAME,
    task_id: str = _TASK_ID,
    title: str = "analyze codebase",
    session_id: str = _SESSION_ID,
) -> dict:
    """TaskCreated payload with ASSUMED field names."""
    return {
        "hook_event_name": "TaskCreated",
        "team_name": team_name,       # ASSUMED (unverified)
        "task_id": task_id,           # ASSUMED (unverified): hook_adapter._PAYLOAD_TASK_ID
        "title": title,               # ASSUMED (unverified): hook_adapter._PAYLOAD_TITLE
        "session_id": session_id,     # CONFIRMED via S1
    }


def _task_completed_payload(
    team_name: str = _TEAM_NAME,
    task_id: str = _TASK_ID,
    session_id: str = _SESSION_ID,
) -> dict:
    """TaskCompleted payload with ASSUMED field names."""
    return {
        "hook_event_name": "TaskCompleted",
        "team_name": team_name,       # ASSUMED (unverified)
        "task_id": task_id,           # ASSUMED (unverified)
        "session_id": session_id,     # CONFIRMED via S1
    }


def _teammate_idle_payload(
    team_name: str = _TEAM_NAME,
    teammate_id: str = _TEAMMATE_ID,
    session_id: str = _SESSION_ID,
) -> dict:
    """TeammateIdle payload with ASSUMED field names."""
    return {
        "hook_event_name": "TeammateIdle",
        "team_name": team_name,       # ASSUMED (unverified)
        "teammate_id": teammate_id,   # ASSUMED (unverified): hook_adapter._PAYLOAD_TEAMMATE_ID
        "session_id": session_id,     # CONFIRMED via S1
    }


def _subagent_start_payload(
    team_name: str = _TEAM_NAME,
    agent_id: str = "agent-abc",
    session_id: str = _SESSION_ID,
) -> dict:
    """SubagentStart payload with ASSUMED field names."""
    return {
        "hook_event_name": "SubagentStart",
        "team_name": team_name,       # ASSUMED (unverified)
        "agent_id": agent_id,         # CONFIRMED via S1
        "session_id": session_id,     # CONFIRMED via S1
    }


def _subagent_stop_payload(
    team_name: str = _TEAM_NAME,
    agent_id: str = "agent-abc",
    session_id: str = _SESSION_ID,
) -> dict:
    """SubagentStop payload with ASSUMED field names."""
    return {
        "hook_event_name": "SubagentStop",
        "team_name": team_name,       # ASSUMED (unverified)
        "agent_id": agent_id,         # CONFIRMED via S1
        "session_id": session_id,     # CONFIRMED via S1
    }


# ---------------------------------------------------------------------------
# T1 + T2: run dir created; events.jsonl has correctly-typed events
# ---------------------------------------------------------------------------

class TestRunDirCreated:
    """T1 + T2: record_team_event creates a team run dir with typed events."""

    def test_task_created_creates_run_dir(self, tmp_path: Path) -> None:
        """T1: TaskCreated payload creates team-<name> run directory."""
        payload = _task_created_payload()
        run_id = record_team_event(payload, skill_runs_base=tmp_path)

        assert run_id is not None, "record_team_event must return a run_id for a valid team payload"
        assert run_id == f"team-{_TEAM_NAME}"

        handle = find_run(run_id, base_dir=tmp_path)
        assert handle is not None, "Run directory must exist after record_team_event"
        assert handle.events_jsonl.exists()
        assert handle.run_state.exists()

    def test_events_jsonl_has_typed_events(self, tmp_path: Path) -> None:
        """T2: events.jsonl contains at least run_started + task_created events."""
        payload = _task_created_payload()
        run_id = record_team_event(payload, skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        assert handle is not None
        events = read_events(handle.as_run_dir())
        types = [e["type"] for e in events]

        assert EVENT_RUN_STARTED in types, "run_started must be emitted for a new team run"
        assert EVENT_TASK_CREATED in types, "task_created event must be appended"

    def test_task_completed_appended(self, tmp_path: Path) -> None:
        """T2: TaskCompleted produces a task_completed event in events.jsonl."""
        record_team_event(_task_created_payload(), skill_runs_base=tmp_path)
        run_id = record_team_event(_task_completed_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())
        types = [e["type"] for e in events]
        assert EVENT_TASK_COMPLETED in types

    def test_teammate_idle_appended(self, tmp_path: Path) -> None:
        """T2: TeammateIdle produces a teammate_idle event in events.jsonl."""
        run_id = record_team_event(_teammate_idle_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())
        types = [e["type"] for e in events]
        assert EVENT_TEAMMATE_IDLE in types

    def test_subagent_start_appended(self, tmp_path: Path) -> None:
        """T2: SubagentStart (with team_name) produces a subagent_spawned event."""
        run_id = record_team_event(_subagent_start_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())
        types = [e["type"] for e in events]
        assert EVENT_SUBAGENT_SPAWNED in types

    def test_subagent_stop_appended(self, tmp_path: Path) -> None:
        """T2: SubagentStop (with team_name) produces a subagent_completed event."""
        run_id = record_team_event(_subagent_stop_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())
        types = [e["type"] for e in events]
        assert EVENT_SUBAGENT_COMPLETED in types


# ---------------------------------------------------------------------------
# T3: projection["tasks"] reflects task graph
# ---------------------------------------------------------------------------

class TestProjectionTaskGraph:
    """T3: projection.tasks reflects task created->in_progress->completed."""

    def test_task_created_sets_in_progress(self, tmp_path: Path) -> None:
        """TaskCreated event sets task status to in_progress in projection."""
        run_id = record_team_event(_task_created_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        proj = json.loads(handle.projection.read_text(encoding="utf-8"))
        tasks = proj.get("tasks", {})

        assert _TASK_ID in tasks, f"task {_TASK_ID!r} must appear in projection.tasks"
        assert tasks[_TASK_ID]["status"] == "in_progress"
        assert tasks[_TASK_ID].get("title") == "analyze codebase"

    def test_task_completed_transitions_status(self, tmp_path: Path) -> None:
        """TaskCompleted transitions task from in_progress to completed."""
        record_team_event(_task_created_payload(), skill_runs_base=tmp_path)
        run_id = record_team_event(_task_completed_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        proj = json.loads(handle.projection.read_text(encoding="utf-8"))
        tasks = proj.get("tasks", {})

        assert tasks[_TASK_ID]["status"] == "completed"
        assert "completed_at" in tasks[_TASK_ID]

    def test_multiple_tasks_tracked(self, tmp_path: Path) -> None:
        """Multiple tasks are tracked independently in projection.tasks."""
        record_team_event(_task_created_payload(task_id="t1", title="task one"),
                          skill_runs_base=tmp_path)
        record_team_event(_task_created_payload(task_id="t2", title="task two"),
                          skill_runs_base=tmp_path)

        run_id = f"team-{_TEAM_NAME}"
        handle = find_run(run_id, base_dir=tmp_path)
        proj = json.loads(handle.projection.read_text(encoding="utf-8"))
        tasks = proj.get("tasks", {})

        assert "t1" in tasks
        assert "t2" in tasks
        assert tasks["t1"]["title"] == "task one"
        assert tasks["t2"]["title"] == "task two"


# ---------------------------------------------------------------------------
# T4: projection["teammates"] populated by TeammateIdle
# ---------------------------------------------------------------------------

class TestProjectionTeammates:
    """T4: projection.teammates is populated by TeammateIdle events."""

    def test_teammate_idle_populates_projection(self, tmp_path: Path) -> None:
        run_id = record_team_event(_teammate_idle_payload(), skill_runs_base=tmp_path)

        handle = find_run(run_id, base_dir=tmp_path)
        proj = json.loads(handle.projection.read_text(encoding="utf-8"))
        teammates = proj.get("teammates", {})

        assert _TEAMMATE_ID in teammates, f"{_TEAMMATE_ID!r} must appear in projection.teammates"
        assert teammates[_TEAMMATE_ID]["status"] == "idle"
        assert "idle_at" in teammates[_TEAMMATE_ID]


# ---------------------------------------------------------------------------
# T5: idempotency — run_started not duplicated
# ---------------------------------------------------------------------------

class TestIdempotency:
    """T5: Re-feeding the same team events does not duplicate run_started."""

    def test_run_started_emitted_once(self, tmp_path: Path) -> None:
        """run_started is emitted exactly once even when multiple events arrive."""
        record_team_event(_task_created_payload(), skill_runs_base=tmp_path)
        record_team_event(_task_completed_payload(), skill_runs_base=tmp_path)
        record_team_event(_teammate_idle_payload(), skill_runs_base=tmp_path)

        run_id = f"team-{_TEAM_NAME}"
        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())

        run_started_count = sum(1 for e in events if e["type"] == EVENT_RUN_STARTED)
        assert run_started_count == 1, (
            f"run_started must be emitted exactly once; got {run_started_count}"
        )

    def test_ensure_team_run_idempotent(self, tmp_path: Path) -> None:
        """ensure_team_run called multiple times does not create duplicate dirs."""
        rd1 = ensure_team_run(_TEAM_NAME, skill_runs_base=tmp_path)
        rd2 = ensure_team_run(_TEAM_NAME, skill_runs_base=tmp_path)
        assert rd1.run_id == rd2.run_id
        assert rd1.path == rd2.path

        # run_started emitted at first ensure; second call reuses existing run.
        events = read_events(rd1)
        run_started_count = sum(1 for e in events if e["type"] == EVENT_RUN_STARTED)
        assert run_started_count == 1


# ---------------------------------------------------------------------------
# T6: mark_team_runs_completed
# ---------------------------------------------------------------------------

class TestMarkTeamRunsCompleted:
    """T6: mark_team_runs_completed flips status to completed + sets completed_at."""

    def test_mark_completed_sets_status(self, tmp_path: Path) -> None:
        record_team_event(_task_created_payload(), skill_runs_base=tmp_path)
        run_id = f"team-{_TEAM_NAME}"

        handle = find_run(run_id, base_dir=tmp_path)
        state_before = json.loads(handle.run_state.read_text(encoding="utf-8"))
        assert state_before["status"] == "running"

        mark_team_runs_completed(_SESSION_ID, skill_runs_base=tmp_path)

        state_after = json.loads(handle.run_state.read_text(encoding="utf-8"))
        assert state_after["status"] == "completed"
        assert "completed_at" in state_after

    def test_mark_completed_idempotent(self, tmp_path: Path) -> None:
        """Calling mark_team_runs_completed twice does not raise or corrupt state."""
        record_team_event(_task_created_payload(), skill_runs_base=tmp_path)

        mark_team_runs_completed(_SESSION_ID, skill_runs_base=tmp_path)
        mark_team_runs_completed(_SESSION_ID, skill_runs_base=tmp_path)

        run_id = f"team-{_TEAM_NAME}"
        handle = find_run(run_id, base_dir=tmp_path)
        state = json.loads(handle.run_state.read_text(encoding="utf-8"))
        assert state["status"] == "completed"

    def test_mark_completed_no_run_is_noop(self, tmp_path: Path) -> None:
        """mark_team_runs_completed is a no-op when no team run exists (non-fatal)."""
        mark_team_runs_completed("no-such-session", skill_runs_base=tmp_path)
        # Must not raise


# ---------------------------------------------------------------------------
# T7: payload with no team_name returns None (caller quarantines)
# ---------------------------------------------------------------------------

class TestNoTeamName:
    """T7: Payload with no resolvable team_name returns None."""

    def test_returns_none_when_no_team_context(self, tmp_path: Path) -> None:
        """record_team_event returns None when payload has no team_name or session_id."""
        payload = {
            "hook_event_name": "TaskCreated",
            "task_id": "t1",
            "title": "something",
            # deliberately no team_name, teamName, session_id, or sessionId
        }
        result = record_team_event(payload, skill_runs_base=tmp_path)
        assert result is None, (
            "record_team_event must return None when no team context is resolvable "
            "(caller should quarantine)"
        )

    def test_returns_none_for_empty_payload(self, tmp_path: Path) -> None:
        result = record_team_event({}, skill_runs_base=tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# T8: unknown/extra payload fields are tolerated (no raise)
# ---------------------------------------------------------------------------

class TestUnknownFieldsToleratedHook:
    """T8: Unknown/extra fields in a team payload do not raise."""

    def test_extra_fields_tolerated(self, tmp_path: Path) -> None:
        """An unknown payload field must not raise and must not appear in events."""
        payload = {
            "hook_event_name": "TaskCreated",
            "team_name": _TEAM_NAME,        # ASSUMED (unverified)
            "task_id": _TASK_ID,            # ASSUMED (unverified)
            "title": "test task",
            "session_id": _SESSION_ID,
            "TOTALLY_UNKNOWN_FIELD_XYZ": 99999,
            "nested_unknown": {"a": 1, "b": [2, 3]},
            "another_future_field": None,
        }
        # Must not raise
        run_id = record_team_event(payload, skill_runs_base=tmp_path)
        assert run_id is not None

        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())
        task_events = [e for e in events if e["type"] == EVENT_TASK_CREATED]
        assert len(task_events) >= 1

        # Unknown field must not appear in the normalized event payload.
        for ev in task_events:
            assert "TOTALLY_UNKNOWN_FIELD_XYZ" not in ev.get("payload", {})

    def test_completely_alien_hook_type_with_team_name(self, tmp_path: Path) -> None:
        """An unknown hook type with a team_name still creates the run (no raise)."""
        payload = {
            "hook_event_name": "SomeFutureHookType",
            "team_name": _TEAM_NAME,        # ASSUMED (unverified)
            "session_id": _SESSION_ID,
            "unexpected_field": "value",
        }
        # record_team_event should not raise; it may or may not capture the event.
        try:
            result = record_team_event(payload, skill_runs_base=tmp_path)
        except Exception as exc:
            pytest.fail(f"record_team_event raised on unknown hook type: {exc}")


# ---------------------------------------------------------------------------
# T9: SubagentStart/Stop captured via derived team_name (from session_id only)
# ---------------------------------------------------------------------------

class TestDerivedTeamName:
    """T9: Session_id alone lets SubagentStart/Stop be captured for a team run."""

    def test_session_id_derives_team_name(self) -> None:
        """team_name_from_session returns the correct format."""
        assert team_name_from_session("abcd1234-efgh") == "session-abcd1234"
        assert team_name_from_session("short") == "session-short"  # <8 chars: use all

    def test_extract_team_name_from_direct_field(self) -> None:
        """extract_team_name returns direct team_name field when present."""
        result = extract_team_name({"team_name": "session-abc"})  # ASSUMED
        assert result == "session-abc"

    def test_extract_team_name_camel_fallback(self) -> None:
        """extract_team_name falls back to teamName (camelCase)."""  # ASSUMED
        result = extract_team_name({"teamName": "session-def"})  # ASSUMED
        assert result == "session-def"

    def test_extract_team_name_from_session_id(self) -> None:
        """extract_team_name derives from session_id when no direct field."""
        result = extract_team_name({"session_id": "abcd1234-rest"})
        assert result == "session-abcd1234"

    def test_extract_team_name_none_when_empty(self) -> None:
        """extract_team_name returns None for an empty payload."""
        assert extract_team_name({}) is None

    def test_subagent_captured_via_session_id(self, tmp_path: Path) -> None:
        """SubagentStart with only session_id (no explicit team_name) is captured."""
        payload = {
            "hook_event_name": "SubagentStart",
            # no team_name field — relies on session_id derivation
            "agent_id": "agent-xyz",  # CONFIRMED via S1
            "session_id": _SESSION_ID,  # CONFIRMED via S1
        }
        run_id = record_team_event(payload, skill_runs_base=tmp_path)
        assert run_id is not None
        assert run_id.startswith("team-session-")

        handle = find_run(run_id, base_dir=tmp_path)
        events = read_events(handle.as_run_dir())
        types = [e["type"] for e in events]
        assert EVENT_SUBAGENT_SPAWNED in types
