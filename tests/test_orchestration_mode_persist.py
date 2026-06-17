"""Tier-1 items 1+2: persisted ``orchestration_mode`` and resume-side reading.

A run's orchestration mode is a historical fact fixed at creation (DL-T1-01).
These tests assert the field is recorded at every run-state creation site
(M-001) and that resume prefers the persisted value over the live env var,
falling back to the env only for legacy runs lacking the field (M-002, C-001).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# Make the package importable from the worktree scripts/ root.
_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence.rundir import create_run_dir
from skills.lib.workflow.persistence.team_mode import (
    AGENT_TEAMS_ENV,
    read_orchestration_mode,
)
from skills.lib.workflow.persistence.resume import compute_remaining_tasks
from skills.lib.workflow.persistence.eventlog import append_event
from skills.lib.workflow.persistence.events import EVENT_TASK_CREATED, event_schema
from skills.lib.workflow.persistence.registry import find_run
from skills.lib.workflow.persistence.teams_bridge import record_team_event
from skills.lib.workflow.persistence.workflow_bridge import bridge_workflow_run


def _teams_env(value: str):
    return mock.patch.dict("os.environ", {AGENT_TEAMS_ENV: value})


def _no_teams_env():
    import os
    env = {k: v for k, v in os.environ.items() if k != AGENT_TEAMS_ENV}
    return mock.patch.dict("os.environ", env, clear=True)


def _strip_mode(run) -> None:
    """Make a run's run-state look legacy (pre-orchestration_mode field)."""
    state = json.loads(run.run_state.read_text())
    state.pop("orchestration_mode", None)
    run.run_state.write_text(json.dumps(state), encoding="utf-8")


# ---------------------------------------------------------------------------
# M-001 — all three run-state creation sites record the field
# ---------------------------------------------------------------------------

def test_create_run_dir_records_workflow_when_env_unset(tmp_path):
    with _no_teams_env():
        rd = create_run_dir(skill="x", base_dir=tmp_path)
    assert json.loads(rd.run_state.read_text())["orchestration_mode"] == "workflow"


def test_create_run_dir_records_agent_teams_when_env_set(tmp_path):
    with _teams_env("1"):
        rd = create_run_dir(skill="x", base_dir=tmp_path)
    assert json.loads(rd.run_state.read_text())["orchestration_mode"] == "agent_teams"


def test_teams_bridge_records_agent_teams(tmp_path):
    """The teams capture path is agent_teams by definition (third site)."""
    payload = {
        "hook_event_name": "TaskCreated",
        "team_name": "session-deadbeef",
        "task_id": "task-1",
        "title": "t",
        "session_id": "deadbeef-0000-1111-2222-333344445555",
    }
    run_id = record_team_event(payload, skill_runs_base=tmp_path)
    handle = find_run(run_id, base_dir=tmp_path)
    assert handle is not None
    assert json.loads(handle.run_state.read_text())["orchestration_mode"] == "agent_teams"


def test_workflow_bridge_inline_path_records_mode(tmp_path):
    """The hand-rolled run_state_data in workflow_bridge records the field too."""
    wf_dir = tmp_path / "projects" / "p" / "s" / "workflows"
    wf_dir.mkdir(parents=True)
    wf_path = wf_dir / "run-mode.json"
    wf_path.write_text(json.dumps({
        "runId": "run-mode",
        "workflowName": "test-skill",
        "status": "running",
        "workflowProgress": [],
    }), encoding="utf-8")

    base = tmp_path / "skill-runs"
    with _no_teams_env():
        run_id = bridge_workflow_run(wf_path, skill_runs_base=base)
    handle = find_run(run_id, base_dir=base)
    assert handle is not None
    state = json.loads(handle.run_state.read_text())
    assert state["orchestration_mode"] in {"workflow", "agent_teams"}
    # M-009: the run-dir-init refactor must preserve the bridge-specific fields.
    assert state["wf_run_id"] == "run-mode"
    assert state["session_id"] == "s"


# ---------------------------------------------------------------------------
# M-002 — read_orchestration_mode helper
# ---------------------------------------------------------------------------

def test_read_orchestration_mode_returns_persisted(tmp_path):
    with _teams_env("1"):
        rd = create_run_dir(skill="x", base_dir=tmp_path)
    assert read_orchestration_mode(rd) == "agent_teams"


def test_read_orchestration_mode_none_when_field_absent(tmp_path):
    rd = create_run_dir(skill="x", base_dir=tmp_path)
    _strip_mode(rd)
    assert read_orchestration_mode(rd) is None


def test_read_orchestration_mode_none_when_file_missing(tmp_path):
    rd = create_run_dir(skill="x", base_dir=tmp_path)
    rd.run_state.unlink()
    assert read_orchestration_mode(rd) is None


# ---------------------------------------------------------------------------
# M-002 — compute_remaining_tasks prefers persisted mode over the live env
# ---------------------------------------------------------------------------

def _seed_task(run) -> None:
    append_event(run, event_schema(
        type=EVENT_TASK_CREATED,
        run_id=run.run_id,
        payload={"task_id": "t-1", "title": "t"},
    ))


def test_persisted_agent_teams_overrides_empty_env(tmp_path):
    with _teams_env("1"):
        rd = create_run_dir(skill="x", base_dir=tmp_path)
    _seed_task(rd)
    with _no_teams_env():
        result = compute_remaining_tasks(rd)
    assert result["team_mode"] is True


def test_persisted_workflow_overrides_env_set(tmp_path):
    with _no_teams_env():
        rd = create_run_dir(skill="x", base_dir=tmp_path)
    _seed_task(rd)
    with _teams_env("1"):
        result = compute_remaining_tasks(rd)
    assert result["team_mode"] is False


@pytest.mark.parametrize("env_value,expected", [("1", True), ("", False)])
def test_legacy_run_falls_back_to_env(tmp_path, env_value, expected):
    rd = create_run_dir(skill="x", base_dir=tmp_path)
    _strip_mode(rd)
    _seed_task(rd)
    with mock.patch.dict("os.environ", {AGENT_TEAMS_ENV: env_value}):
        result = compute_remaining_tasks(rd)
    assert result["team_mode"] is expected
