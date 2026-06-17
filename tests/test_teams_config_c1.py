#!/usr/bin/env python3
"""C1: authoritative team membership from the runtime-written config.json.

These tests build against a REAL captured ``~/.claude/teams/<name>/config.json``
schema (see tests/fixtures/real_team_config_*.json), per the hard-won S1-S5
lesson: never assert against an invented schema. The lead-only fixture is a
verbatim capture from this machine; the multi-member fixture extends it with two
teammates using only confirmed member keys (plus the optional prompt/model that
teammates carry).

Validates:
  C1-1. read_team_config parses a present config (read-only, via teams_base).
  C1-2. read_team_config returns None for absent / malformed / non-object JSON.
  C1-3. read_team_config NEVER creates the runtime-owned teams dir/file.
  C1-4. record_team_event populates projection.teammates with REAL name+agentType
        keyed by member name, with the lead flagged.
  C1-5. team_members emission is idempotent (unchanged roster -> no duplicate).
  C1-6. A roster change (teammate joins) emits a fresh team_members event.
  C1-7. ensure_team_run records lead_session_id / lead_agent_id from config.
  C1-8. The verbatim real lead-only capture parses to a lead-only roster.
  C1-9. Absent config is a no-op: no team_members event, prior behavior intact.
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
from skills.lib.workflow.persistence.fold import fold, empty_projection
from skills.lib.workflow.persistence.events import EVENT_TEAM_MEMBERS
from skills.lib.workflow.persistence.teams_bridge import (
    ensure_team_run,
    read_team_config,
    emit_team_members,
    record_team_event,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_TEAM_NAME = "session-abcd1234"  # matches both fixtures' "name"
_SESSION_ID = "abcd1234-efgh-5678-ijkl-mnopqrstuvwx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_config(teams_base: Path, team_name: str, fixture: str) -> Path:
    """Copy a fixture config.json into <teams_base>/<team_name>/config.json."""
    dst = teams_base / team_name / "config.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((_FIXTURES / fixture).read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _project(handle) -> dict:
    """Fold a run's event log into a projection."""
    proj = empty_projection()
    for ev in read_events(handle.as_run_dir()):
        proj = fold(proj, ev)
    return proj


def _team_members_events(handle) -> list[dict]:
    return [e for e in read_events(handle.as_run_dir()) if e.get("type") == EVENT_TEAM_MEMBERS]


def _task_created_payload(team_name: str = _TEAM_NAME, session_id: str = _SESSION_ID) -> dict:
    return {
        "hook_event_name": "TaskCreated",
        "team_name": team_name,
        "task_id": "task-001",
        "title": "analyze",
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# C1-1 / C1-2 / C1-3: read_team_config
# ---------------------------------------------------------------------------


class TestReadTeamConfig:
    def test_parses_present_config(self, tmp_path: Path) -> None:
        """C1-1: a present config.json parses to its real fields."""
        teams_base = tmp_path / "teams"
        _install_config(teams_base, _TEAM_NAME, "real_team_config_multi.json")

        cfg = read_team_config(_TEAM_NAME, teams_base=teams_base)
        assert cfg is not None
        assert cfg["name"] == _TEAM_NAME
        assert cfg["leadAgentId"] == "team-lead@session-abcd1234"
        names = [m["name"] for m in cfg["members"]]
        assert names == ["team-lead", "challenger", "verifier"]

    def test_absent_returns_none(self, tmp_path: Path) -> None:
        """C1-2: absent config.json -> None (not an error)."""
        assert read_team_config(_TEAM_NAME, teams_base=tmp_path / "teams") is None

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        """C1-2: invalid JSON -> None (tolerant, never raises)."""
        teams_base = tmp_path / "teams"
        p = teams_base / _TEAM_NAME / "config.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ this is not json", encoding="utf-8")
        assert read_team_config(_TEAM_NAME, teams_base=teams_base) is None

    def test_non_object_json_returns_none(self, tmp_path: Path) -> None:
        """C1-2: a JSON array (not an object) -> None."""
        teams_base = tmp_path / "teams"
        p = teams_base / _TEAM_NAME / "config.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("[1, 2, 3]", encoding="utf-8")
        assert read_team_config(_TEAM_NAME, teams_base=teams_base) is None

    def test_empty_team_name_returns_none(self, tmp_path: Path) -> None:
        """C1-2: empty team name -> None."""
        assert read_team_config("", teams_base=tmp_path / "teams") is None

    def test_read_is_read_only(self, tmp_path: Path) -> None:
        """C1-3: reading an absent config NEVER creates the runtime-owned dir."""
        teams_base = tmp_path / "teams"
        read_team_config(_TEAM_NAME, teams_base=teams_base)
        assert not teams_base.exists(), "read_team_config must not create the teams dir"


# ---------------------------------------------------------------------------
# C1-4 / C1-7: projection enrichment + run-state lead identity
# ---------------------------------------------------------------------------


class TestProjectionEnrichment:
    def test_teammates_populated_with_real_identity(self, tmp_path: Path) -> None:
        """C1-4: projection.teammates carries real name + agentType, keyed by name."""
        teams_base = tmp_path / "teams"
        skill_runs_base = tmp_path / "skill-runs"
        _install_config(teams_base, _TEAM_NAME, "real_team_config_multi.json")

        run_id = record_team_event(
            _task_created_payload(), skill_runs_base=skill_runs_base, teams_base=teams_base
        )
        handle = find_run(run_id, base_dir=skill_runs_base)
        proj = _project(handle)

        teammates = proj["teammates"]
        assert set(teammates) == {"team-lead", "challenger", "verifier"}
        assert teammates["challenger"]["agent_type"] == "researcher"
        assert teammates["verifier"]["agent_type"] == "quality-reviewer"
        assert teammates["challenger"]["agent_id"] == "challenger@session-abcd1234"
        assert teammates["challenger"]["source"] == "config"

    def test_lead_flagged(self, tmp_path: Path) -> None:
        """C1-4: the lead member is flagged is_lead; teammates are not."""
        teams_base = tmp_path / "teams"
        skill_runs_base = tmp_path / "skill-runs"
        _install_config(teams_base, _TEAM_NAME, "real_team_config_multi.json")

        run_id = record_team_event(
            _task_created_payload(), skill_runs_base=skill_runs_base, teams_base=teams_base
        )
        proj = _project(find_run(run_id, base_dir=skill_runs_base))
        assert proj["teammates"]["team-lead"]["is_lead"] is True
        assert proj["teammates"]["challenger"]["is_lead"] is False

    def test_run_state_records_lead_identity(self, tmp_path: Path) -> None:
        """C1-7: ensure_team_run records lead_session_id / lead_agent_id from config."""
        teams_base = tmp_path / "teams"
        skill_runs_base = tmp_path / "skill-runs"
        _install_config(teams_base, _TEAM_NAME, "real_team_config_multi.json")

        run_dir = ensure_team_run(
            _TEAM_NAME, skill_runs_base=skill_runs_base, teams_base=teams_base
        )
        state = json.loads(run_dir.run_state.read_text(encoding="utf-8"))
        assert state["lead_agent_id"] == "team-lead@session-abcd1234"
        assert state["lead_session_id"] == _SESSION_ID


# ---------------------------------------------------------------------------
# C1-5 / C1-6: idempotency + roster change
# ---------------------------------------------------------------------------


class TestIdempotencyAndRosterChange:
    def test_unchanged_roster_not_duplicated(self, tmp_path: Path) -> None:
        """C1-5: re-feeding events with an unchanged roster emits team_members once."""
        teams_base = tmp_path / "teams"
        skill_runs_base = tmp_path / "skill-runs"
        _install_config(teams_base, _TEAM_NAME, "real_team_config_multi.json")

        record_team_event(_task_created_payload(), skill_runs_base=skill_runs_base, teams_base=teams_base)
        run_id = record_team_event(
            {**_task_created_payload(), "hook_event_name": "TaskCompleted"},
            skill_runs_base=skill_runs_base,
            teams_base=teams_base,
        )
        handle = find_run(run_id, base_dir=skill_runs_base)
        assert len(_team_members_events(handle)) == 1, "unchanged roster must not re-emit"

    def test_roster_change_emits_new_event(self, tmp_path: Path) -> None:
        """C1-6: a teammate joining (config grows) emits a fresh team_members event."""
        teams_base = tmp_path / "teams"
        skill_runs_base = tmp_path / "skill-runs"
        # Start lead-only (rename real capture's team to match our session).
        lead_only = json.loads((_FIXTURES / "real_team_config_lead_only.json").read_text())
        lead_only["name"] = _TEAM_NAME
        lead_only["leadAgentId"] = "team-lead@" + _TEAM_NAME
        lead_only["leadSessionId"] = _SESSION_ID
        lead_only["members"][0]["agentId"] = "team-lead@" + _TEAM_NAME
        cfg_path = teams_base / _TEAM_NAME / "config.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(lead_only), encoding="utf-8")

        run_id = record_team_event(
            _task_created_payload(), skill_runs_base=skill_runs_base, teams_base=teams_base
        )
        handle = find_run(run_id, base_dir=skill_runs_base)
        assert len(_team_members_events(handle)) == 1
        proj = _project(handle)
        assert set(proj["teammates"]) == {"team-lead"}

        # A teammate joins: runtime rewrites config.json with an extra member.
        _install_config(teams_base, _TEAM_NAME, "real_team_config_multi.json")
        record_team_event(
            {**_task_created_payload(), "hook_event_name": "TaskCompleted"},
            skill_runs_base=skill_runs_base,
            teams_base=teams_base,
        )
        assert len(_team_members_events(handle)) == 2, "roster growth must emit a new event"
        proj2 = _project(handle)
        assert set(proj2["teammates"]) == {"team-lead", "challenger", "verifier"}


# ---------------------------------------------------------------------------
# C1-8 / C1-9: real capture + absent-config no-op
# ---------------------------------------------------------------------------


class TestRealCaptureAndNoOp:
    def test_real_lead_only_capture_parses(self, tmp_path: Path) -> None:
        """C1-8: the verbatim real lead-only capture parses to a lead-only roster."""
        cfg = json.loads((_FIXTURES / "real_team_config_lead_only.json").read_text())
        team_name = cfg["name"]  # "session-a4810f8d"
        teams_base = tmp_path / "teams"
        dst = teams_base / team_name / "config.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(cfg), encoding="utf-8")
        skill_runs_base = tmp_path / "skill-runs"

        run_dir = ensure_team_run(team_name, skill_runs_base=skill_runs_base, teams_base=teams_base)
        proj = _project(find_run(run_dir.run_id, base_dir=skill_runs_base))
        assert list(proj["teammates"]) == ["team-lead"]
        assert proj["teammates"]["team-lead"]["agent_type"] == "team-lead"

    def test_absent_config_is_noop(self, tmp_path: Path) -> None:
        """C1-9: with no config.json, no team_members event; prior behavior intact."""
        teams_base = tmp_path / "teams"  # never populated
        skill_runs_base = tmp_path / "skill-runs"

        run_id = record_team_event(
            _task_created_payload(), skill_runs_base=skill_runs_base, teams_base=teams_base
        )
        handle = find_run(run_id, base_dir=skill_runs_base)
        assert _team_members_events(handle) == []
        assert _project(handle)["teammates"] == {}

    def test_emit_team_members_returns_false_when_absent(self, tmp_path: Path) -> None:
        """C1-9: emit_team_members reports False (nothing appended) when no config."""
        teams_base = tmp_path / "teams"
        skill_runs_base = tmp_path / "skill-runs"
        run_dir = ensure_team_run(_TEAM_NAME, skill_runs_base=skill_runs_base, teams_base=teams_base)
        assert emit_team_members(_TEAM_NAME, run_dir, skill_runs_base=skill_runs_base, teams_base=teams_base) is False
