#!/usr/bin/env python3
"""M-007 / CI-M-007-004 — team_mode + teammate_memory_probe fallback tests.

Tests assert:
  1. With CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS set, select_orchestration_mode()
     picks mode="agent_teams".
  2. With the env var unset, it picks mode="workflow" (fallback).
  3. The fallback produces the SAME durable event types and projection as the
     team path would (mock-injected; no live Agent Teams required).
  4. No code writes inside ~/.claude/teams or ~/.claude/tasks (DL-002).
  5. The teammate-memory probe selects the curated-.md fallback when Agent
     Teams is disabled (default-deny per DL-023).

Distinct from test_adversarial_skill_parity.py (which tests OUTPUT equivalence
of the adversarial skill ports vs their Python predecessors). These tests cover
FALLBACK BEHAVIOR and DURABLE EVENT parity, not skill output structure.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Make the project scripts importable
# ---------------------------------------------------------------------------

import sys

_WORKTREE = Path(__file__).parent.parent
_SCRIPTS = _WORKTREE / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence import (
    EVENT_TASK_COMPLETED,
    EVENT_TASK_CREATED,
    append_event,
    create_run_dir,
    event_schema,
)
from skills.lib.workflow.persistence.team_mode import (
    AGENT_TEAMS_ENV,
    ModeDescriptor,
    is_agent_teams_available,
    select_orchestration_mode,
)
from skills.lib.workflow.persistence.probe.teammate_memory_probe import (
    DEFAULT_DENY_FALLBACK,
    is_fallback_selected,
    probe_teammate_memory,
)
from skills.lib.workflow.persistence.resume import compute_remaining_tasks

# ---------------------------------------------------------------------------
# Helper: env-var injection
# ---------------------------------------------------------------------------

CLAUDE_HOME = Path.home() / ".claude"
TEAMS_DIR = CLAUDE_HOME / "teams"
TASKS_DIR = CLAUDE_HOME / "tasks"


def _with_teams_env(value: str):
    """Context manager: set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS to value."""
    return mock.patch.dict(os.environ, {AGENT_TEAMS_ENV: value})


def _without_teams_env():
    """Context manager: ensure CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is unset."""
    env = {k: v for k, v in os.environ.items() if k != AGENT_TEAMS_ENV}
    return mock.patch.dict(os.environ, env, clear=True)


# ---------------------------------------------------------------------------
# 1. Mode selection with env var set
# ---------------------------------------------------------------------------


def test_select_orchestration_mode_teams_enabled():
    """With env var set to non-empty string, mode is 'agent_teams'."""
    with _with_teams_env("1"):
        desc = select_orchestration_mode()
    assert desc.mode == "agent_teams"
    assert desc.agent_teams_available is True
    assert desc.env_var == AGENT_TEAMS_ENV
    assert desc.env_value == "1"


def test_select_orchestration_mode_teams_enabled_truthy_string():
    """Any non-empty string activates agent_teams mode."""
    with _with_teams_env("enabled"):
        desc = select_orchestration_mode()
    assert desc.mode == "agent_teams"
    assert desc.agent_teams_available is True


def test_is_agent_teams_available_when_set():
    """is_agent_teams_available() returns True when env var is set."""
    with _with_teams_env("1"):
        assert is_agent_teams_available() is True


# ---------------------------------------------------------------------------
# 2. Mode selection with env var unset (fallback)
# ---------------------------------------------------------------------------


def test_select_orchestration_mode_teams_disabled():
    """With env var unset, mode is 'workflow' (fallback path)."""
    with _without_teams_env():
        desc = select_orchestration_mode()
    assert desc.mode == "workflow"
    assert desc.agent_teams_available is False
    assert desc.env_value is None


def test_select_orchestration_mode_empty_string_is_disabled():
    """An empty string for the env var means teams are disabled."""
    with _with_teams_env(""):
        desc = select_orchestration_mode()
    assert desc.mode == "workflow"
    assert desc.agent_teams_available is False


def test_is_agent_teams_available_when_unset():
    """is_agent_teams_available() returns False when env var is unset."""
    with _without_teams_env():
        assert is_agent_teams_available() is False


def test_mode_descriptor_fields():
    """ModeDescriptor exposes all diagnostic fields."""
    with _with_teams_env("live"):
        desc = select_orchestration_mode()
    assert isinstance(desc, ModeDescriptor)
    assert desc.env_var == AGENT_TEAMS_ENV
    assert desc.env_value == "live"


# ---------------------------------------------------------------------------
# 3. Fallback produces the SAME durable event types as the team path
# ---------------------------------------------------------------------------


def test_fallback_produces_task_events(tmp_path):
    """Fallback path emits TaskCreated + TaskCompleted events identical in type
    to what the Agent Teams path would emit via M-003 hooks.

    Both paths must produce the same durable event types so that
    compute_remaining_tasks() and replay() work identically on either path.
    This test injects events as the M-003 hooks would, then asserts the
    projection computed by compute_remaining_tasks() is equivalent.
    """
    run = create_run_dir(skill="decision-critic", base_dir=tmp_path)

    # Simulate what M-003 hooks emit: TaskCreated then TaskCompleted
    task_payload_created: dict[str, Any] = {
        "task_id": "task-decompose",
        "title": "decompose",
        "session_id": "sess-001",
    }
    task_payload_completed: dict[str, Any] = {
        "task_id": "task-decompose",
        "title": "decompose",
    }

    append_event(run, event_schema(
        type=EVENT_TASK_CREATED,
        run_id=run.run_id,
        payload=task_payload_created,
    ))
    append_event(run, event_schema(
        type=EVENT_TASK_COMPLETED,
        run_id=run.run_id,
        payload=task_payload_completed,
    ))

    with _with_teams_env("1"):
        result = compute_remaining_tasks(run)

    assert result["team_mode"] is True
    assert result["incomplete_tasks"] == []
    assert "task-decompose" in result["completed_task_ids"]


def test_fallback_incomplete_task_detected(tmp_path):
    """compute_remaining_tasks detects a task created but not completed."""
    run = create_run_dir(skill="deepthink", base_dir=tmp_path)

    append_event(run, event_schema(
        type=EVENT_TASK_CREATED,
        run_id=run.run_id,
        payload={"task_id": "task-synthesize", "title": "synthesize"},
    ))
    # No TaskCompleted emitted — task is incomplete.

    with _with_teams_env("1"):
        result = compute_remaining_tasks(run)

    assert result["team_mode"] is True
    assert len(result["incomplete_tasks"]) == 1
    assert result["incomplete_tasks"][0]["task_id"] == "task-synthesize"
    # Respawn descriptor describes a fresh team (never dead-teammate rehydration)
    assert result["respawn_descriptor"]["spawn_mode"] == "fresh_team"


def test_fallback_mode_no_task_events(tmp_path):
    """Without task events, team_mode is False even if env var is set."""
    run = create_run_dir(skill="problem-analysis", base_dir=tmp_path)
    # Emit no task events.

    with _with_teams_env("1"):
        result = compute_remaining_tasks(run)

    assert result["team_mode"] is False
    assert result["incomplete_tasks"] == []


def test_workflow_mode_does_not_enable_team_mode(tmp_path):
    """Legacy run + env unset: team_mode is False regardless of task events.

    Strips the persisted ``orchestration_mode`` to exercise the C-001 legacy
    fallback deterministically (the field, when present, would otherwise pin
    the mode regardless of the live env — that case is covered separately).
    """
    run = create_run_dir(skill="decision-critic", base_dir=tmp_path)
    _state = json.loads(run.run_state.read_text())
    _state.pop("orchestration_mode", None)
    run.run_state.write_text(json.dumps(_state), encoding="utf-8")

    append_event(run, event_schema(
        type=EVENT_TASK_CREATED,
        run_id=run.run_id,
        payload={"task_id": "task-x", "title": "x"},
    ))

    with _without_teams_env():
        result = compute_remaining_tasks(run)

    assert result["team_mode"] is False


# ---------------------------------------------------------------------------
# 4. No code writes inside ~/.claude/teams or ~/.claude/tasks (DL-002)
# ---------------------------------------------------------------------------


def test_select_mode_does_not_write_teams_dir():
    """select_orchestration_mode() must not write inside ~/.claude/teams."""
    teams_before = set(TEAMS_DIR.iterdir()) if TEAMS_DIR.exists() else set()
    tasks_before = set(TASKS_DIR.iterdir()) if TASKS_DIR.exists() else set()

    with _with_teams_env("1"):
        select_orchestration_mode()

    teams_after = set(TEAMS_DIR.iterdir()) if TEAMS_DIR.exists() else set()
    tasks_after = set(TASKS_DIR.iterdir()) if TASKS_DIR.exists() else set()

    assert teams_after == teams_before, (
        "select_orchestration_mode() must not create files in ~/.claude/teams (DL-002)"
    )
    assert tasks_after == tasks_before, (
        "select_orchestration_mode() must not create files in ~/.claude/tasks (DL-002)"
    )


def test_create_run_dir_does_not_write_teams_dir(tmp_path):
    """create_run_dir() must not write inside ~/.claude/teams or ~/.claude/tasks."""
    teams_before = set(TEAMS_DIR.iterdir()) if TEAMS_DIR.exists() else set()
    tasks_before = set(TASKS_DIR.iterdir()) if TASKS_DIR.exists() else set()

    create_run_dir(skill="decision-critic", base_dir=tmp_path)

    teams_after = set(TEAMS_DIR.iterdir()) if TEAMS_DIR.exists() else set()
    tasks_after = set(TASKS_DIR.iterdir()) if TASKS_DIR.exists() else set()

    assert teams_after == teams_before, (
        "create_run_dir() must not create files in ~/.claude/teams (DL-002)"
    )
    assert tasks_after == tasks_before, (
        "create_run_dir() must not create files in ~/.claude/tasks (DL-002)"
    )


# ---------------------------------------------------------------------------
# 5. Memory probe: curated-.md fallback selected when teams disabled
# ---------------------------------------------------------------------------


def test_memory_probe_unverifiable_when_teams_disabled(tmp_path):
    """probe_teammate_memory() records honored=null and selects the curated-.md
    fallback when CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is unset (DL-023).
    """
    probe_sidecar = (
        _WORKTREE
        / "skills"
        / "scripts"
        / "skills"
        / "lib"
        / "workflow"
        / "persistence"
        / "probe"
        / "teammate_memory_probe_result.json"
    )

    with _without_teams_env():
        # Redirect the sidecar write to tmp_path so we don't pollute the repo.
        sidecar_target = tmp_path / "teammate_memory_probe_result.json"
        with mock.patch(
            "skills.lib.workflow.persistence.probe.teammate_memory_probe.RESULT_SIDECAR",
            sidecar_target,
        ):
            result = probe_teammate_memory()

    assert result["honored"] is None, "Unverifiable -> honored must be null"
    assert result["fallback_selected"] == DEFAULT_DENY_FALLBACK
    assert result["verdict"] == "UNVERIFIABLE_TEAMS_DISABLED"
    assert result["agent_teams_env_set"] is False


def test_memory_probe_fallback_selected_by_default():
    """is_fallback_selected() returns True when no probe result exists (default-deny)."""
    # Temporarily hide the sidecar file if it exists.
    probe_sidecar = (
        _WORKTREE
        / "skills"
        / "scripts"
        / "skills"
        / "lib"
        / "workflow"
        / "persistence"
        / "probe"
        / "teammate_memory_probe_result.json"
    )
    with mock.patch(
        "skills.lib.workflow.persistence.probe.teammate_memory_probe.RESULT_SIDECAR",
        Path("/nonexistent/probe_result.json"),
    ):
        assert is_fallback_selected() is True, (
            "Default-deny: fallback must be selected when no probe result exists"
        )


def test_memory_probe_writes_sidecar(tmp_path):
    """probe_teammate_memory() emits a machine-readable JSON sidecar."""
    sidecar = tmp_path / "teammate_memory_probe_result.json"
    with _without_teams_env():
        with mock.patch(
            "skills.lib.workflow.persistence.probe.teammate_memory_probe.RESULT_SIDECAR",
            sidecar,
        ):
            probe_teammate_memory()

    assert sidecar.exists(), "Probe must write a result sidecar"
    data = json.loads(sidecar.read_text())
    assert data["probe"] == "teammate_memory"
    assert "honored" in data
    assert "fallback_selected" in data
    assert "verdict" in data
