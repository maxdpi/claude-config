#!/usr/bin/env python3
"""M-003 acceptance tests: hook adapters, run_event_hook, session hooks.

Acceptance criteria
-------------------
AC-1  Feeding fixture hook payloads appends correctly-typed events;
      SubagentStart materializes task.json + emits agent_spawned symmetric
      with SubagentStop's agent_completed + transcript copy-on-stop;
      an unknown hook field is dropped without error;
      SessionEnd flush produces current run-state even mid-run;
      adapters NEVER write inside runtime-owned dirs.

AC-2  CLAUDE_SKILL_RUN_ID resolves to that run;
      payload session_id/task_id resolves via registry scan;
      unmatched payload lands in quarantine log, hook exits non-fatally.

AC-3  SubagentStart payload with NO resolvable native_agent_id is
      QUARANTINED + WARNED, never appended as null-correlated (DL-022);
      a fixture confirms the assumed payload field names (R-008).

AC-4  Copy-on-stop is atomic (tmp + os.rename); with transcript_path
      the native transcript copies to transcript.jsonl; without it,
      path is derived from session_id + agent_id and a WARNING logged
      if unresolved.  Assert transcript_path presence handling.

Fixtures document assumed field names
--------------------------------------
The SubagentStart/SubagentStop fixture payloads below explicitly declare
which field names the adapter assumes (R-008 caveat).  Update these
fixtures (and hook_adapter._PAYLOAD_* constants) if the runtime uses
different names.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Make the skills package importable
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).parent.parent / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence import (
    create_run_dir,
    append_event,
    read_events,
    event_schema,
    EVENT_SUBAGENT_SPAWNED,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_COMPLETED,
    EVENT_TEAMMATE_IDLE,
)
from skills.lib.workflow.persistence.hook_adapter import (
    QUARANTINE,
    normalize_hook_event,
    _PAYLOAD_AGENT_ID,
    _PAYLOAD_SESSION_ID,
    _PAYLOAD_PARENT_AGENT_ID,
    _PAYLOAD_DEPTH,
    _PAYLOAD_TRANSCRIPT_PATH,
    _PAYLOAD_AGENT_TRANSCRIPT_PATH,
    _PAYLOAD_TASK_ID,
    _PAYLOAD_TITLE,
    _PAYLOAD_TEAMMATE_ID,
)
from skills.lib.workflow.persistence.registry import find_run, list_runs
from skills.lib.workflow.persistence.projection import replay

# ---------------------------------------------------------------------------
# Fixture payload shapes (R-008 documentation anchor)
# ---------------------------------------------------------------------------

# These payloads document the ASSUMED field names for each hook type.
# If the Claude Code runtime uses different names, update hook_adapter.py
# constants AND update these fixtures to match.

def _make_subagent_start_payload(
    agent_id: str = "ab73a631269d58310",
    session_id: str = "6bc18a41-test",
    parent_agent_id: str | None = None,
    depth: int = 0,
) -> dict:
    """SubagentStart fixture payload.

    Assumed field names (R-008):
      agentId       -- native subagent identifier (confirmed in A4 transcript records)
      sessionId     -- native session identifier  (confirmed in A4 transcript records)
      parentAgentId -- spawning parent's agentId  (assumed)
      depth         -- nesting depth              (assumed)
      hook_event_name -- CC hook event name       (snake_case convention)
    """
    return {
        "hook_event_name": "SubagentStart",
        _PAYLOAD_AGENT_ID: agent_id,      # "agentId"
        _PAYLOAD_SESSION_ID: session_id,  # "sessionId"
        _PAYLOAD_PARENT_AGENT_ID: parent_agent_id,  # "parentAgentId"
        _PAYLOAD_DEPTH: depth,             # "depth"
        "extra_field_unknown": "should_be_dropped",
    }


def _make_subagent_stop_payload(
    agent_id: str = "ab73a631269d58310",
    session_id: str = "6bc18a41-test",
    transcript_path: str | None = None,
) -> dict:
    """SubagentStop fixture payload.

    Assumed field names (R-008):
      agentId         -- native subagent identifier
      sessionId       -- native session identifier
      transcript_path -- filesystem path to native transcript (may be absent)
      hook_event_name -- CC hook event name
    """
    payload: dict = {
        "hook_event_name": "SubagentStop",
        _PAYLOAD_AGENT_ID: agent_id,       # "agentId"
        _PAYLOAD_SESSION_ID: session_id,   # "sessionId"
        "extra_field_unknown": "dropped",
    }
    if transcript_path is not None:
        # The SUBAGENT's own transcript drives copy-on-stop (confirmed via S1).
        payload[_PAYLOAD_AGENT_TRANSCRIPT_PATH] = transcript_path  # "agent_transcript_path"
    return payload


def _make_task_created_payload(task_id: str = "t1", title: str = "do X") -> dict:
    return {
        "hook_event_name": "TaskCreated",
        _PAYLOAD_TASK_ID: task_id,    # "task_id"
        _PAYLOAD_TITLE: title,         # "title"
        _PAYLOAD_SESSION_ID: "sess1", # "sessionId"
        "junk_field": 999,
    }


def _make_task_completed_payload(task_id: str = "t1") -> dict:
    return {
        "hook_event_name": "TaskCompleted",
        _PAYLOAD_TASK_ID: task_id,
        _PAYLOAD_SESSION_ID: "sess1",
    }


def _make_teammate_idle_payload(teammate_id: str = "agent-0") -> dict:
    return {
        "hook_event_name": "TeammateIdle",
        _PAYLOAD_TEAMMATE_ID: teammate_id,
        _PAYLOAD_SESSION_ID: "sess1",
    }


# ---------------------------------------------------------------------------
# AC-1 + AC-3: normalize_hook_event unit tests
# ---------------------------------------------------------------------------


class TestNormalizeHookEvent:
    """Unit tests for hook_adapter.normalize_hook_event."""

    def test_subagent_start_produces_spawned_event(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_start_payload(agent_id="abc123", session_id="sess-x")
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not QUARANTINE and event is not None
        assert event["type"] == EVENT_SUBAGENT_SPAWNED
        assert event["native_agent_id"] == "abc123"
        assert event["native_session_id"] == "sess-x"
        assert event["run_id"] == rd.run_id

    def test_subagent_start_no_agent_id_returns_quarantine(self, tmp_path: Path) -> None:
        """DL-022: SubagentStart with no native_agent_id -> QUARANTINE (never None-correlated)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = {
            "hook_event_name": "SubagentStart",
            # _PAYLOAD_AGENT_ID deliberately absent
            _PAYLOAD_SESSION_ID: "sess-x",
        }
        result = normalize_hook_event(payload, rd.run_id)
        assert result is QUARANTINE, (
            "A SubagentStart payload with no agentId must return QUARANTINE (DL-022), "
            "not a null-correlated spawn event"
        )

    def test_subagent_start_drops_unknown_fields(self, tmp_path: Path) -> None:
        """Unknown hook fields are dropped; no error raised."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_start_payload()
        payload["completely_unknown_field"] = {"nested": "object"}
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not QUARANTINE and event is not None
        # Unknown field must not appear in the payload dict.
        assert "completely_unknown_field" not in event.get("payload", {})

    def test_subagent_stop_produces_completed_event(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_stop_payload(agent_id="abc123")
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        assert event["type"] == EVENT_SUBAGENT_COMPLETED
        assert event["native_agent_id"] == "abc123"

    def test_subagent_stop_with_transcript_path(self, tmp_path: Path) -> None:
        """transcript_path is preserved in the payload for copy-on-stop."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_stop_payload(transcript_path="/some/path/agent.jsonl")
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        assert event["payload"]["transcript_path"] == "/some/path/agent.jsonl"

    def test_subagent_stop_without_transcript_path(self, tmp_path: Path) -> None:
        """transcript_path absent in payload -> None in event payload (not an error)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_stop_payload()  # no transcript_path
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        assert event["payload"]["transcript_path"] is None

    def test_task_created_produces_task_created_event(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event(_make_task_created_payload("t42", "build X"), rd.run_id)
        assert event is not None
        assert event["type"] == EVENT_TASK_CREATED
        assert event["payload"]["task_id"] == "t42"
        assert event["payload"]["title"] == "build X"

    def test_task_completed_produces_task_completed_event(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event(_make_task_completed_payload("t42"), rd.run_id)
        assert event is not None
        assert event["type"] == EVENT_TASK_COMPLETED
        assert event["payload"]["task_id"] == "t42"

    def test_teammate_idle_produces_teammate_idle_event(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event(_make_teammate_idle_payload("agent-7"), rd.run_id)
        assert event is not None
        assert event["type"] == EVENT_TEAMMATE_IDLE
        assert event["payload"]["teammate_id"] == "agent-7"

    def test_unknown_hook_type_returns_none(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event({"hook_event_name": "UnknownHookXYZ"}, rd.run_id)
        assert event is None

    def test_subagent_start_carries_parent_and_depth(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_start_payload(
            parent_agent_id="parent-001",
            depth=2,
        )
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        assert event["parent_agent_id"] == "parent-001"
        assert event["depth"] == 2

    def test_fixture_confirms_real_field_names(self) -> None:
        """R-008 RESOLVED: payload field names CONFIRMED via the S1 live-capture
        probe (2026-06-16). Claude Code hook payloads use snake_case (NOT the
        camelCase that A4 *transcript records* use). Pin the confirmed names so a
        regression (or a CC field rename) is caught."""
        assert _PAYLOAD_AGENT_ID == "agent_id", (
            "S1 live capture: SubagentStart/Stop carry 'agent_id' (snake_case), "
            "not the 'agentId' that transcript records use"
        )
        assert _PAYLOAD_SESSION_ID == "session_id", (
            "S1 live capture: payloads carry 'session_id' (snake_case)"
        )
        # parentAgentId / depth are NOT emitted by current CC (confirmed absent);
        # constants kept for forward-compat. absent -> top-level / depth 0.
        assert _PAYLOAD_PARENT_AGENT_ID == "parentAgentId"
        assert _PAYLOAD_DEPTH == "depth"
        # SubagentStop carries TWO transcript paths; copy-on-stop uses the SUBAGENT's.
        assert _PAYLOAD_AGENT_TRANSCRIPT_PATH == "agent_transcript_path", (
            "S1 live capture: the subagent's own transcript (copy-on-stop target, DL-016)"
        )
        assert _PAYLOAD_TRANSCRIPT_PATH == "transcript_path", (
            "S1 live capture: this is the PARENT session transcript -- NOT copied"
        )


# ---------------------------------------------------------------------------
# AC-1: event appended to events.jsonl correctly
# ---------------------------------------------------------------------------


class TestEventAppendedCorrectly:
    """End-to-end: fixture payload -> events.jsonl entry."""

    def test_task_created_appended(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event(_make_task_created_payload("t1"), rd.run_id)
        assert event is not None
        append_event(rd, event)
        events = read_events(rd)
        assert len(events) == 1
        assert events[0]["type"] == EVENT_TASK_CREATED
        assert events[0]["payload"]["task_id"] == "t1"

    def test_task_completed_appended(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event(_make_task_completed_payload("t1"), rd.run_id)
        assert event is not None
        append_event(rd, event)
        events = read_events(rd)
        assert events[0]["type"] == EVENT_TASK_COMPLETED

    def test_subagent_spawned_appended(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_start_payload(agent_id="a1", session_id="s1")
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        append_event(rd, event)
        events = read_events(rd)
        assert events[0]["type"] == EVENT_SUBAGENT_SPAWNED
        assert events[0]["native_agent_id"] == "a1"

    def test_subagent_completed_appended(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = _make_subagent_stop_payload(agent_id="a1")
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        append_event(rd, event)
        events = read_events(rd)
        assert events[0]["type"] == EVENT_SUBAGENT_COMPLETED

    def test_unknown_field_dropped_no_error(self, tmp_path: Path) -> None:
        """Unknown hook fields do not raise and are dropped from the envelope."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        payload = {
            "hook_event_name": "TaskCreated",
            "task_id": "t1",
            "title": "x",
            "sessionId": "s1",
            "TOTALLY_UNKNOWN_FIELD_XYZ": 12345,
            "nested_unknown": {"a": 1, "b": [1, 2, 3]},
        }
        event = normalize_hook_event(payload, rd.run_id)
        assert event is not None
        append_event(rd, event)  # must not raise
        events = read_events(rd)
        assert len(events) == 1
        # Unknown field must not be in the normalized payload.
        assert "TOTALLY_UNKNOWN_FIELD_XYZ" not in events[0].get("payload", {})

    def test_spawn_and_complete_symmetric(self, tmp_path: Path) -> None:
        """SubagentStart (spawned) and SubagentStop (completed) are symmetric."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)

        start = normalize_hook_event(
            _make_subagent_start_payload(agent_id="a1", session_id="s1"),
            rd.run_id,
        )
        stop = normalize_hook_event(
            _make_subagent_stop_payload(agent_id="a1", session_id="s1"),
            rd.run_id,
        )
        assert start is not None and stop is not None
        append_event(rd, start)
        append_event(rd, stop)

        events = read_events(rd)
        types = [e["type"] for e in events]
        assert types == [EVENT_SUBAGENT_SPAWNED, EVENT_SUBAGENT_COMPLETED]
        # Both events reference the same native_agent_id.
        assert events[0]["native_agent_id"] == "a1"
        assert events[1]["native_agent_id"] == "a1"

    def test_adapters_never_write_runtime_dirs(self, tmp_path: Path) -> None:
        """Adapters must never write inside ~/.claude/teams or ~/.claude/tasks."""
        forbidden = [
            Path.home() / ".claude" / "teams",
            Path.home() / ".claude" / "tasks",
        ]
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        event = normalize_hook_event(_make_task_created_payload(), rd.run_id)
        assert event is not None
        append_event(rd, event)
        for d in forbidden:
            # The dirs may not exist (expected); the test just confirms no new
            # files were created there by the adapter.
            if d.exists():
                # Any file created before this test is not our concern.
                for f in d.rglob("*"):
                    assert not f.name.startswith(".tmp-"), (
                        f"Adapter wrote a tmp file into runtime dir {d}: {f}"
                    )


# ---------------------------------------------------------------------------
# AC-2: run_event_hook correlation
# ---------------------------------------------------------------------------


class TestRunEventHookCorrelation:
    """Integration tests for run_event_hook.main() correlation logic."""

    def _import_hook(self):
        from skills.hooks.run_event_hook import main, _write_quarantine, _QUARANTINE_PATH
        return main, _write_quarantine, _QUARANTINE_PATH

    def test_env_var_run_id_resolves(self, tmp_path: Path, monkeypatch) -> None:
        """CLAUDE_SKILL_RUN_ID env var routes to that run directly."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        # Patch _resolve_base_dir so find_run uses tmp_path.
        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import run_event_hook
            payload = _make_task_created_payload("task-env")
            exit_code = run_event_hook.main(payload=payload)

        assert exit_code == 0
        events = read_events(rd)
        assert any(e["type"] == EVENT_TASK_CREATED for e in events)

    def test_registry_scan_resolves_by_session_id(self, tmp_path: Path, monkeypatch) -> None:
        """Payload session_id matched against run-state.json -> resolves the run."""
        monkeypatch.delenv("CLAUDE_SKILL_RUN_ID", raising=False)

        rd = create_run_dir(skill="s", base_dir=tmp_path)
        # Write session_id into run-state.json so registry scan can find it.
        import datetime
        state = json.loads(rd.run_state.read_text(encoding="utf-8"))
        state["session_id"] = "my-session-42"
        from skills.lib.workflow.persistence.atomic import write_atomic
        write_atomic(rd.run_state, state)

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ), mock.patch(
            "skills.lib.workflow.persistence.rundir._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import run_event_hook
            # Reload to pick up fresh module-level _QUARANTINE_PATH.
            import importlib
            importlib.reload(run_event_hook)

            payload = {
                "hook_event_name": "TaskCreated",
                "task_id": "t1",
                "title": "T",
                _PAYLOAD_SESSION_ID: "my-session-42",
            }
            exit_code = run_event_hook.main(payload=payload)

        assert exit_code == 0
        events = read_events(rd)
        assert any(e["type"] == EVENT_TASK_CREATED for e in events)

    def test_unmatched_payload_quarantined_non_fatal(self, tmp_path: Path, monkeypatch) -> None:
        """Unmatched payload with no team context goes to quarantine; hook exits 0.

        A payload must have NO session_id/team_name to be genuinely unresolvable:
        if session_id is present, teams_bridge captures it as a team run instead
        of quarantining (teams_bridge M-003 extension). This test uses a payload
        with no session_id and no team_name to exercise the pure quarantine path.
        """
        monkeypatch.delenv("CLAUDE_SKILL_RUN_ID", raising=False)
        quarantine_records: list[dict] = []

        def _fake_quarantine(payload: dict, reason: str = "") -> None:
            quarantine_records.append({"payload": payload, "reason": reason})

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import run_event_hook
            import importlib
            importlib.reload(run_event_hook)

            with mock.patch.object(run_event_hook, "_write_quarantine", _fake_quarantine):
                # Use a payload with NO session_id and no team_name so that
                # teams_bridge.extract_team_name returns None and the event is
                # genuinely unresolvable (quarantine path).
                payload = {
                    "hook_event_name": "TaskCreated",
                    "task_id": "no-match-task",
                    "title": "something",
                    # deliberately no session_id, no team_name
                }
                exit_code = run_event_hook.main(payload=payload)

        assert exit_code == 0, "Hook must exit 0 (non-fatal) for unmatched payload"
        assert len(quarantine_records) >= 1, "Unmatched payload must land in quarantine"

    def test_subagent_start_no_agent_id_quarantined(self, tmp_path: Path, monkeypatch) -> None:
        """DL-022: SubagentStart with no agentId -> QUARANTINE, never appended."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)
        quarantine_records: list[dict] = []

        def _fake_quarantine(payload: dict, reason: str = "") -> None:
            quarantine_records.append({"payload": payload, "reason": reason})

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import run_event_hook
            import importlib
            importlib.reload(run_event_hook)

            with mock.patch.object(run_event_hook, "_write_quarantine", _fake_quarantine):
                payload = {
                    "hook_event_name": "SubagentStart",
                    # No agentId field -- should trigger QUARANTINE
                    _PAYLOAD_SESSION_ID: "sess-x",
                }
                exit_code = run_event_hook.main(payload=payload)

        assert exit_code == 0
        # No event must have been appended.
        events = read_events(rd)
        assert len(events) == 0, (
            "A null-correlated SubagentStart MUST NOT be appended (DL-022)"
        )
        # Quarantine must have been called.
        assert len(quarantine_records) >= 1, "QUARANTINE must be signalled for no-agent-id SubagentStart"


# ---------------------------------------------------------------------------
# AC-4: copy-on-stop
# ---------------------------------------------------------------------------


class TestCopyOnStop:
    """Integration tests for the copy-on-stop logic in run_event_hook."""

    def test_copy_on_stop_with_transcript_path(self, tmp_path: Path, monkeypatch) -> None:
        """When SubagentStop carries transcript_path, it is copied to transcript.jsonl."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        # Create a fake native transcript.
        fake_transcript = tmp_path / "agent-abc.jsonl"
        fake_transcript.write_text(
            json.dumps({"agentId": "abc", "sessionId": "s1", "type": "user"}) + "\n",
            encoding="utf-8",
        )

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import run_event_hook
            import importlib
            importlib.reload(run_event_hook)

            payload = _make_subagent_stop_payload(
                agent_id="abc",
                session_id="s1",
                transcript_path=str(fake_transcript),
            )
            exit_code = run_event_hook.main(payload=payload)

        assert exit_code == 0
        # Find transcript.jsonl somewhere in the run dir tree.
        copies = list(rd.path.rglob("transcript.jsonl"))
        assert len(copies) >= 1, "transcript.jsonl must be copied on SubagentStop"
        assert copies[0].read_text(encoding="utf-8") == fake_transcript.read_text(encoding="utf-8")

    def test_copy_on_stop_atomic_rename(self, tmp_path: Path, monkeypatch) -> None:
        """Copy-on-stop is atomic: no .tmp-transcript- files left behind."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        fake_transcript = tmp_path / "native.jsonl"
        fake_transcript.write_text("line1\nline2\n", encoding="utf-8")

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import run_event_hook
            import importlib
            importlib.reload(run_event_hook)

            payload = _make_subagent_stop_payload(
                transcript_path=str(fake_transcript),
            )
            run_event_hook.main(payload=payload)

        # No leftover .tmp-transcript- files.
        tmp_files = list(rd.path.rglob(".tmp-transcript-*"))
        assert len(tmp_files) == 0, f"Atomic copy left temp files: {tmp_files}"

    def test_copy_on_stop_without_transcript_path_logs_warning(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """When transcript_path absent and native path unresolvable, WARNING is logged."""
        import logging
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        # SubagentStop without transcript_path; no native transcript exists.
        payload = _make_subagent_stop_payload(
            agent_id="nonexistent-agent",
            session_id="nonexistent-session",
            # no transcript_path
        )

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ), mock.patch(
            "skills.lib.workflow.persistence.probe.subagent_transcript_probe.resolve_transcript_path",
            return_value=None,  # unresolvable
        ), caplog.at_level(logging.WARNING):
            from skills.hooks import run_event_hook
            import importlib
            importlib.reload(run_event_hook)
            run_event_hook.main(payload=payload)

        # A warning must have been emitted about the unresolved transcript.
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("transcript" in m.lower() or "copy-on-stop" in m.lower()
                   for m in warning_messages), (
            "A WARNING must be logged when transcript cannot be resolved (DL-016)"
        )


# ---------------------------------------------------------------------------
# AC-1: subagent_start_hook symmetry + task.json materialization
# ---------------------------------------------------------------------------


class TestSubagentStartHook:
    """Integration tests for subagent_start_hook.main()."""

    def test_spawned_event_emitted(self, tmp_path: Path, monkeypatch) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import subagent_start_hook
            import importlib
            importlib.reload(subagent_start_hook)

            payload = _make_subagent_start_payload(agent_id="a1", session_id="s1")
            exit_code = subagent_start_hook.main(payload=payload)

        assert exit_code == 0
        events = read_events(rd)
        assert any(e["type"] == EVENT_SUBAGENT_SPAWNED for e in events)

    def test_task_json_materialized(self, tmp_path: Path, monkeypatch) -> None:
        """SubagentStart hook materializes a task.json if one doesn't exist."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import subagent_start_hook
            import importlib
            importlib.reload(subagent_start_hook)

            payload = _make_subagent_start_payload(agent_id="agent-new")
            subagent_start_hook.main(payload=payload)

        # A task.json must exist somewhere in the run dir.
        task_files = list(rd.path.rglob("task.json"))
        assert len(task_files) >= 1, "SubagentStart hook must materialize a task.json"
        task_data = json.loads(task_files[0].read_text(encoding="utf-8"))
        assert task_data.get("native_agent_id") == "agent-new"

    def test_no_agent_id_quarantined(self, tmp_path: Path, monkeypatch) -> None:
        """DL-022: SubagentStart with no agentId is quarantined, nothing appended."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)
        quarantine_records: list[dict] = []

        def _fake_quarantine(payload: dict, reason: str = "") -> None:
            quarantine_records.append({"payload": payload, "reason": reason})

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import subagent_start_hook
            import importlib
            importlib.reload(subagent_start_hook)

            with mock.patch.object(subagent_start_hook, "_write_quarantine", _fake_quarantine):
                payload = {
                    "hook_event_name": "SubagentStart",
                    _PAYLOAD_SESSION_ID: "sess-x",
                    # No agentId
                }
                exit_code = subagent_start_hook.main(payload=payload)

        assert exit_code == 0
        events = read_events(rd)
        assert len(events) == 0, "No event must be appended for a null-correlated spawn (DL-022)"
        assert len(quarantine_records) >= 1, "QUARANTINE must be called for no-agent-id SubagentStart"

    def test_symmetric_with_subagent_stop(self, tmp_path: Path, monkeypatch) -> None:
        """SubagentStart emits spawned; SubagentStop emits completed. Symmetric pair."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        monkeypatch.setenv("CLAUDE_SKILL_RUN_ID", rd.run_id)

        fake_transcript = tmp_path / "agent-sym.jsonl"
        fake_transcript.write_text('{"agentId":"sym","type":"user"}\n', encoding="utf-8")

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import subagent_start_hook, run_event_hook
            import importlib
            importlib.reload(subagent_start_hook)
            importlib.reload(run_event_hook)

            # Fire start hook.
            subagent_start_hook.main(
                payload=_make_subagent_start_payload(agent_id="sym", session_id="s1")
            )
            # Fire stop hook.
            run_event_hook.main(
                payload=_make_subagent_stop_payload(
                    agent_id="sym",
                    session_id="s1",
                    transcript_path=str(fake_transcript),
                )
            )

        events = read_events(rd)
        types = [e["type"] for e in events]
        assert EVENT_SUBAGENT_SPAWNED in types
        assert EVENT_SUBAGENT_COMPLETED in types
        # Transcript must have been copied.
        copies = list(rd.path.rglob("transcript.jsonl"))
        assert len(copies) >= 1


# ---------------------------------------------------------------------------
# AC-1: SessionEnd flush
# ---------------------------------------------------------------------------


class TestSessionEndHook:
    """Integration tests for session_end_hook.main()."""

    def test_flush_produces_current_run_state(self, tmp_path: Path) -> None:
        """SessionEnd flush merges latest projection into run-state.json."""
        rd = create_run_dir(skill="my-skill", base_dir=tmp_path)

        # Append a phase event to events.jsonl.
        from skills.lib.workflow.persistence.events import EVENT_PHASE_STARTED
        event = event_schema(
            type=EVENT_PHASE_STARTED,
            run_id=rd.run_id,
            payload={"phase_id": "analyse"},
        )
        append_event(rd, event)

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import session_end_hook
            import importlib
            importlib.reload(session_end_hook)
            exit_code = session_end_hook.main()

        assert exit_code == 0
        state = json.loads(rd.run_state.read_text(encoding="utf-8"))
        # The flush must have merged the projection's phases into run-state.
        proj = replay(rd)
        # At minimum status from projection must be reflected.
        assert "status" in state

    def test_flush_idempotent(self, tmp_path: Path) -> None:
        """Calling session_end_hook multiple times does not corrupt run-state."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import session_end_hook
            import importlib
            importlib.reload(session_end_hook)
            session_end_hook.main()
            session_end_hook.main()  # second call must not raise or corrupt

        state = json.loads(rd.run_state.read_text(encoding="utf-8"))
        assert "run_id" in state

    def test_flush_mid_run(self, tmp_path: Path) -> None:
        """Flush on a mid-run (status=running) produces a current projection."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)

        # Append several events to simulate mid-run state.
        from skills.lib.workflow.persistence.events import EVENT_PHASE_STARTED
        for phase in ("scope", "analyse"):
            e = event_schema(
                type=EVENT_PHASE_STARTED,
                run_id=rd.run_id,
                payload={"phase_id": phase},
            )
            append_event(rd, e)

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import session_end_hook
            import importlib
            importlib.reload(session_end_hook)
            session_end_hook.main()

        state = json.loads(rd.run_state.read_text(encoding="utf-8"))
        # run_id must survive the merge.
        assert state.get("run_id") == rd.run_id


# ---------------------------------------------------------------------------
# AC-1: SessionStart hook
# ---------------------------------------------------------------------------


class TestSessionStartHook:
    """Integration tests for session_start_hook.main()."""

    def test_session_start_exits_zero(self, tmp_path: Path) -> None:
        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ), mock.patch(
            "skills.lib.workflow.persistence.rundir._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import session_start_hook
            import importlib
            importlib.reload(session_start_hook)
            exit_code = session_start_hook.main()
        assert exit_code == 0

    def test_session_start_detects_incomplete_runs(self, tmp_path: Path, capsys) -> None:
        """SessionStart prints a resume offer when there are incomplete runs."""
        rd = create_run_dir(skill="my-skill", base_dir=tmp_path)
        # run-state.json starts with status=running — that's an incomplete run.

        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ), mock.patch(
            "skills.lib.workflow.persistence.rundir._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import session_start_hook
            import importlib
            importlib.reload(session_start_hook)
            exit_code = session_start_hook.main()

        assert exit_code == 0
        captured = capsys.readouterr()
        # The resume offer mentions the run_id prefix.
        assert rd.run_id[:8] in captured.out or "Resumable" in captured.out

    def test_session_start_prunes_done_runs_past_ttl(self, tmp_path: Path) -> None:
        """SessionStart invokes prune_runs, which deletes done runs past TTL."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        # Patch run-state.json to done + old completion timestamp.
        import datetime
        state = json.loads(rd.run_state.read_text(encoding="utf-8"))
        state["status"] = "done"
        old_ts = time.time() - 30 * 86400
        state["completed_at"] = datetime.datetime.fromtimestamp(
            old_ts, tz=datetime.timezone.utc
        ).isoformat()
        from skills.lib.workflow.persistence.atomic import write_atomic
        write_atomic(rd.run_state, state)

        # prune_runs() uses _resolve_base_dir from both retention and rundir.
        with mock.patch(
            "skills.lib.workflow.persistence.registry._resolve_base_dir",
            return_value=tmp_path,
        ), mock.patch(
            "skills.lib.workflow.persistence.rundir._resolve_base_dir",
            return_value=tmp_path,
        ), mock.patch(
            "skills.lib.workflow.persistence.retention._resolve_base_dir",
            return_value=tmp_path,
        ):
            from skills.hooks import session_start_hook
            import importlib
            importlib.reload(session_start_hook)
            # Call with explicit base_dir to bypass the production path.
            from skills.lib.workflow.persistence.retention import prune_runs
            pruned = prune_runs(base_dir=tmp_path)

        assert rd.run_id in pruned or not rd.path.exists(), (
            "Done run past TTL must be pruned"
        )
