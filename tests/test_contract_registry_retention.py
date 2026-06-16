#!/usr/bin/env python3
"""M-002 acceptance tests: directory-as-contract, run registry, retention TTL.

Acceptance criteria verified
-----------------------------
AC-1  Subagent dir created with task.json (input) + state.json; no custom
      events.jsonl; nested subagent dirs nest recursively with parent/depth.
AC-2  Registry lists all runs with run_id + status; derived by scanning
      run-state.json files, no separate index.
AC-3  Retention deletes a done run older than TTL; keeps a crashed run of
      any age; keeps a done run inside TTL.
AC-4  Resume NOT offered when native transcript age exceeds cleanupPeriodDays
      UNLESS a copy-on-stop transcript.jsonl exists (PRIMARY path).
AC-5  is_resumable(None) returns False.
AC-6  Age guard judged from native transcript mtime (resolved via session_id +
      native_agent_id), not started_at; unresolvable native path => False.
AC-7  BOTH paths covered without M-003:
        - seeded transcript.jsonl in subagent dir => resumable (PRIMARY).
        - no copy + task.json with unresolvable/expired native id => not resumable.

Tests do NOT depend on M-003 (hooks) running.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Make the skills package importable
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).parent.parent / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence import create_run_dir, write_atomic
from skills.lib.workflow.persistence.contract import (
    create_subagent_dir,
    subagent_dir_path,
)
from skills.lib.workflow.persistence.registry import RunHandle, find_run, list_runs
from skills.lib.workflow.persistence.retention import is_resumable, prune_runs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(tmp: Path, status: str = "running", started_at: str | None = None) -> Path:
    """Create a minimal run dir under *tmp* with run-state.json."""
    rd = create_run_dir(skill="test-skill", base_dir=tmp)
    # Patch status in run-state.json.
    state_path = rd.run_state
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["status"] = status
    if started_at is not None:
        data["started_at"] = started_at
    write_atomic(state_path, data)
    return rd.path


def _stamp_run_completed(run_path: Path, ts: float) -> None:
    """Write completed_at to run-state.json and projection.json."""
    import datetime

    state_path = run_path / "run-state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["completed_at"] = datetime.datetime.fromtimestamp(
        ts, tz=datetime.timezone.utc
    ).isoformat()
    write_atomic(state_path, data)

    # Inject a completed phase into projection.json for the secondary lookup.
    proj_path = run_path / "projection.json"
    proj = json.loads(proj_path.read_text(encoding="utf-8"))
    proj["phases"]["p1"] = {"status": "completed", "completed_at": ts}
    write_atomic(proj_path, proj)


# ---------------------------------------------------------------------------
# AC-1: create_subagent_dir — task.json + state.json; no events.jsonl
# ---------------------------------------------------------------------------


class TestCreateSubagentDir:
    def test_creates_task_json_and_state_json(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(
            rd,
            agent_id="a1",
            task={"prompt": "do something"},
        )
        assert (subdir / "task.json").exists(), "task.json must exist"
        assert (subdir / "state.json").exists(), "state.json must exist"

    def test_no_events_jsonl_created(self, tmp_path: Path) -> None:
        """Per-subagent output history is the native transcript, not a custom log."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={"prompt": "x"})
        assert not (subdir / "events.jsonl").exists(), (
            "No custom events.jsonl — per-subagent history is the native transcript (DL-016)"
        )

    def test_task_json_contains_input_and_metadata(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(
            rd,
            agent_id="a1",
            task={"prompt": "analyse codebase"},
            parent_agent_id="root",
            depth=1,
        )
        task = json.loads((subdir / "task.json").read_text(encoding="utf-8"))
        assert task["agent_id"] == "a1"
        assert task["run_id"] == rd.run_id
        assert task["parent_agent_id"] == "root"
        assert task["depth"] == 1
        assert task["task"] == {"prompt": "analyse codebase"}

    def test_state_json_written_atomically(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        audit_state = {"projection_snapshot": {"status": "running"}}
        subdir = create_subagent_dir(rd, agent_id="a1", task={}, state=audit_state)
        state = json.loads((subdir / "state.json").read_text(encoding="utf-8"))
        assert state == audit_state

    def test_subdir_under_run_path(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="agent-0", task={})
        assert subdir.parent == rd.path, "top-level subagent is a direct child of run dir"

    # ------------------------------------------------------------------
    # Nested subagents nest recursively (AC-1)
    # ------------------------------------------------------------------

    def test_nested_subagent_nests_recursively(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)

        # Level 0: top-level subagent.
        create_subagent_dir(rd, agent_id="root", task={"phase": "plan"})
        # Level 1: child of root.
        create_subagent_dir(
            rd,
            agent_id="child",
            task={"phase": "execute"},
            parent_agent_id="root",
            parent_chain=["root"],
            depth=1,
        )
        # Level 2: grandchild.
        create_subagent_dir(
            rd,
            agent_id="grandchild",
            task={"phase": "review"},
            parent_agent_id="child",
            parent_chain=["root", "child"],
            depth=2,
        )

        root_dir = rd.path / "root"
        child_dir = rd.path / "root" / "child"
        grandchild_dir = rd.path / "root" / "child" / "grandchild"

        assert root_dir.is_dir()
        assert child_dir.is_dir()
        assert grandchild_dir.is_dir()

        gc_task = json.loads((grandchild_dir / "task.json").read_text(encoding="utf-8"))
        assert gc_task["depth"] == 2
        assert gc_task["parent_agent_id"] == "child"

    def test_subagent_dir_path_helper(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        p = subagent_dir_path(rd, "a1")
        assert p == rd.path / "a1"

        nested = subagent_dir_path(rd, "leaf", parent_chain=["root", "mid"])
        assert nested == rd.path / "root" / "mid" / "leaf"


# ---------------------------------------------------------------------------
# AC-2: registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_list_runs_returns_all_runs(self, tmp_path: Path) -> None:
        for skill in ("alpha", "beta", "gamma"):
            create_run_dir(skill=skill, base_dir=tmp_path)
        runs = list_runs(tmp_path)
        assert len(runs) == 3
        skills = {r["skill"] for r in runs}
        assert skills == {"alpha", "beta", "gamma"}

    def test_list_runs_empty_base_dir(self, tmp_path: Path) -> None:
        assert list_runs(tmp_path) == []

    def test_list_runs_missing_base_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "no-such-dir"
        assert list_runs(nonexistent) == []

    def test_list_runs_includes_status(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        runs = list_runs(tmp_path)
        assert runs[0]["status"] == "running"
        assert runs[0]["run_id"] == rd.run_id

    def test_list_runs_no_separate_index_file(self, tmp_path: Path) -> None:
        create_run_dir(skill="s", base_dir=tmp_path)
        top_level_files = [f.name for f in tmp_path.iterdir() if f.is_file()]
        assert "index.json" not in top_level_files
        assert "registry.json" not in top_level_files

    def test_find_run_returns_handle(self, tmp_path: Path) -> None:
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        handle = find_run(rd.run_id, base_dir=tmp_path)
        assert handle is not None
        assert handle.run_id == rd.run_id
        assert handle.run_state.exists()

    def test_find_run_missing_returns_none(self, tmp_path: Path) -> None:
        handle = find_run("does-not-exist", base_dir=tmp_path)
        assert handle is None

    def test_list_runs_sorted_by_started_at(self, tmp_path: Path) -> None:
        ids = [create_run_dir(skill="s", base_dir=tmp_path).run_id for _ in range(3)]
        runs = list_runs(tmp_path)
        assert [r["run_id"] for r in runs] == ids  # chronological


# ---------------------------------------------------------------------------
# AC-3 + AC-5 + AC-6 + AC-7: retention + is_resumable
# ---------------------------------------------------------------------------


class TestPruneRuns:
    def test_prune_deletes_done_run_older_than_ttl(self, tmp_path: Path) -> None:
        run_path = _make_run(tmp_path, status="done")
        old_ts = time.time() - 10 * 86400  # 10 days ago
        _stamp_run_completed(run_path, old_ts)

        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert run_path.name in pruned
        assert not run_path.exists()

    def test_prune_keeps_crashed_run_of_any_age(self, tmp_path: Path) -> None:
        run_path = _make_run(tmp_path, status="crashed")
        old_ts = time.time() - 365 * 86400  # 1 year ago
        _stamp_run_completed(run_path, old_ts)

        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert run_path.name not in pruned
        assert run_path.exists()

    def test_prune_keeps_running_run(self, tmp_path: Path) -> None:
        run_path = _make_run(tmp_path, status="running")
        old_ts = time.time() - 100 * 86400
        _stamp_run_completed(run_path, old_ts)

        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert run_path.name not in pruned
        assert run_path.exists()

    def test_prune_keeps_done_run_inside_ttl(self, tmp_path: Path) -> None:
        run_path = _make_run(tmp_path, status="done")
        recent_ts = time.time() - 2 * 86400  # 2 days ago
        _stamp_run_completed(run_path, recent_ts)

        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert run_path.name not in pruned
        assert run_path.exists()

    def test_prune_deletes_tombstoned_run_older_than_ttl(self, tmp_path: Path) -> None:
        run_path = _make_run(tmp_path, status="tombstoned")
        old_ts = time.time() - 30 * 86400
        _stamp_run_completed(run_path, old_ts)

        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert run_path.name in pruned

    def test_prune_also_deletes_completed_status(self, tmp_path: Path) -> None:
        run_path = _make_run(tmp_path, status="completed")
        old_ts = time.time() - 10 * 86400
        _stamp_run_completed(run_path, old_ts)

        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert run_path.name in pruned

    def test_prune_empty_base(self, tmp_path: Path) -> None:
        pruned = prune_runs(base_dir=tmp_path, retention_days=7)
        assert pruned == []


# ---------------------------------------------------------------------------
# AC-5: is_resumable(None) -> False
# ---------------------------------------------------------------------------


class TestIsResumableNone:
    def test_none_returns_false(self) -> None:
        assert is_resumable(None) is False


# ---------------------------------------------------------------------------
# AC-4 + AC-6 + AC-7: is_resumable paths
# ---------------------------------------------------------------------------


class TestIsResumable:
    # ------------------------------------------------------------------
    # PRIMARY path: copy-on-stop transcript.jsonl exists (AC-7a)
    # ------------------------------------------------------------------

    def test_copy_on_stop_transcript_returns_true(self, tmp_path: Path) -> None:
        """Seeded transcript.jsonl in subagent dir => resumable (PRIMARY)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})
        # Simulate M-003 SubagentStop hook writing transcript.jsonl.
        transcript = subdir / "transcript.jsonl"
        transcript.write_text(
            json.dumps({"agentId": "native-123", "type": "user", "text": "go"}) + "\n",
            encoding="utf-8",
        )
        handle = RunHandle(run_id=rd.run_id, base=tmp_path)
        assert is_resumable(handle) is True

    def test_transcript_in_nested_subdir_returns_true(self, tmp_path: Path) -> None:
        """transcript.jsonl anywhere in the subtree satisfies PRIMARY."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        # Nest two levels.
        create_subagent_dir(rd, agent_id="root", task={})
        nested = create_subagent_dir(
            rd, agent_id="leaf", task={}, parent_chain=["root"], depth=1
        )
        transcript = nested / "transcript.jsonl"
        transcript.write_text('{"type":"user"}\n', encoding="utf-8")

        handle = RunHandle(run_id=rd.run_id, base=tmp_path)
        assert is_resumable(handle) is True

    # ------------------------------------------------------------------
    # FALLBACK path: no copy + native transcript resolution (AC-7b)
    # ------------------------------------------------------------------

    def test_no_copy_no_native_id_returns_false(self, tmp_path: Path) -> None:
        """No transcript.jsonl + task.json with no native ids => False (DL-020)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        # create_subagent_dir does NOT store native_session_id/native_agent_id
        # unless M-003 populates them.  Default task.json has no native ids.
        create_subagent_dir(rd, agent_id="a1", task={"prompt": "x"})
        handle = RunHandle(run_id=rd.run_id, base=tmp_path)
        assert is_resumable(handle) is False

    def test_no_copy_unresolvable_native_path_returns_false(self, tmp_path: Path) -> None:
        """No copy + task.json with unresolvable native ids => False (DL-020 AC-7b)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})
        # Inject native ids that cannot be resolved (session/agent do not exist).
        task_doc = json.loads((subdir / "task.json").read_text(encoding="utf-8"))
        task_doc["native_session_id"] = "nonexistent-session-abc123"
        task_doc["native_agent_id"] = "nonexistent-agent-xyz789"
        write_atomic(subdir / "task.json", task_doc)

        handle = RunHandle(run_id=rd.run_id, base=tmp_path)
        # resolve_transcript_path will fail to find the file => False.
        assert is_resumable(handle) is False

    def test_no_copy_expired_native_transcript_returns_false(self, tmp_path: Path) -> None:
        """No copy + native transcript mtime older than cleanupPeriodDays => False.

        Simulates the age-guard FALLBACK (DL-020) by creating a *real*
        transcript.jsonl file at a known path (mocking resolve_transcript_path
        is not needed — we write the file and backdate it).
        """
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})

        # Create a fake "native" transcript outside the run dir (under tmp_path).
        native_session = "fake-session-001"
        native_agent = "fake-agent-001"
        native_dir = tmp_path / "projects" / "proj" / native_session / "subagents"
        native_dir.mkdir(parents=True)
        native_transcript = native_dir / f"agent-{native_agent}.jsonl"
        native_transcript.write_text('{"agentId":"fake-agent-001"}\n', encoding="utf-8")

        # Backdate the mtime to 60 days ago (beyond cleanupPeriodDays=30).
        old_mtime = time.time() - 60 * 86400
        os.utime(native_transcript, (old_mtime, old_mtime))

        # Point task.json at the native ids.
        task_doc = json.loads((subdir / "task.json").read_text(encoding="utf-8"))
        task_doc["native_session_id"] = native_session
        task_doc["native_agent_id"] = native_agent
        write_atomic(subdir / "task.json", task_doc)

        # Patch resolve_transcript_path to find our fake transcript.
        import skills.lib.workflow.persistence.retention as ret_mod
        original = ret_mod.resolve_transcript_path

        def _fake_resolve(session_id: str, agent_id: str, cwd: str | None = None):
            if session_id == native_session and agent_id == native_agent:
                return native_transcript
            return None

        ret_mod.resolve_transcript_path = _fake_resolve
        try:
            handle = RunHandle(run_id=rd.run_id, base=tmp_path)
            # Expired transcript => not resumable; cleanupPeriodDays default 30.
            result = is_resumable(handle)
        finally:
            ret_mod.resolve_transcript_path = original

        assert result is False

    def test_no_copy_fresh_native_transcript_returns_true(self, tmp_path: Path) -> None:
        """No copy + native transcript mtime within cleanupPeriodDays => True (FALLBACK)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})

        native_session = "fake-session-002"
        native_agent = "fake-agent-002"
        native_dir = tmp_path / "projects" / "proj2" / native_session / "subagents"
        native_dir.mkdir(parents=True)
        native_transcript = native_dir / f"agent-{native_agent}.jsonl"
        native_transcript.write_text('{"agentId":"fake-agent-002"}\n', encoding="utf-8")
        # Fresh mtime — just written (default).

        task_doc = json.loads((subdir / "task.json").read_text(encoding="utf-8"))
        task_doc["native_session_id"] = native_session
        task_doc["native_agent_id"] = native_agent
        write_atomic(subdir / "task.json", task_doc)

        import skills.lib.workflow.persistence.retention as ret_mod
        original = ret_mod.resolve_transcript_path

        def _fake_resolve(session_id: str, agent_id: str, cwd: str | None = None):
            if session_id == native_session and agent_id == native_agent:
                return native_transcript
            return None

        ret_mod.resolve_transcript_path = _fake_resolve
        try:
            handle = RunHandle(run_id=rd.run_id, base=tmp_path)
            result = is_resumable(handle)
        finally:
            ret_mod.resolve_transcript_path = original

        assert result is True

    def test_copy_on_stop_overrides_expired_native(self, tmp_path: Path) -> None:
        """PRIMARY wins even when native transcript would be expired."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})

        # Seed copy-on-stop transcript.
        (subdir / "transcript.jsonl").write_text('{"type":"user"}\n', encoding="utf-8")

        # Also plant task.json pointing at an expired native transcript — but
        # PRIMARY should short-circuit before we ever check the native path.
        task_doc = json.loads((subdir / "task.json").read_text(encoding="utf-8"))
        task_doc["native_session_id"] = "expired-session"
        task_doc["native_agent_id"] = "expired-agent"
        write_atomic(subdir / "task.json", task_doc)

        handle = RunHandle(run_id=rd.run_id, base=tmp_path)
        assert is_resumable(handle) is True

    def test_is_resumable_with_run_dir_type(self, tmp_path: Path) -> None:
        """is_resumable also accepts RunDir (not just RunHandle)."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})
        (subdir / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
        # RunDir has the same .path attribute — should work.
        assert is_resumable(rd) is True

    # ------------------------------------------------------------------
    # AC-4: resume NOT offered when native transcript age > cleanupPeriodDays
    # UNLESS copy-on-stop exists.
    # ------------------------------------------------------------------

    def test_no_resume_without_transcript_or_fresh_native(self, tmp_path: Path) -> None:
        """Verifies AC-4: expired native + no copy => not resumable."""
        rd = create_run_dir(skill="s", base_dir=tmp_path)
        subdir = create_subagent_dir(rd, agent_id="a1", task={})

        native_session = "sess-ac4"
        native_agent = "agent-ac4"
        native_dir = tmp_path / "projects" / "p" / native_session / "subagents"
        native_dir.mkdir(parents=True)
        native_transcript = native_dir / f"agent-{native_agent}.jsonl"
        native_transcript.write_text("{}\n", encoding="utf-8")
        old_mtime = time.time() - 45 * 86400  # 45 days — beyond 30-day default
        os.utime(native_transcript, (old_mtime, old_mtime))

        task_doc = json.loads((subdir / "task.json").read_text(encoding="utf-8"))
        task_doc["native_session_id"] = native_session
        task_doc["native_agent_id"] = native_agent
        write_atomic(subdir / "task.json", task_doc)

        import skills.lib.workflow.persistence.retention as ret_mod
        original = ret_mod.resolve_transcript_path

        def _fake_resolve(session_id, agent_id, cwd=None):
            if session_id == native_session and agent_id == native_agent:
                return native_transcript
            return None

        ret_mod.resolve_transcript_path = _fake_resolve
        try:
            handle = RunHandle(run_id=rd.run_id, base=tmp_path)
            assert is_resumable(handle) is False
        finally:
            ret_mod.resolve_transcript_path = original
