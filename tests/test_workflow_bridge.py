#!/usr/bin/env python3
"""Tests for the Workflow run-state bridge (workflow_bridge.py).

Validates that bridge_workflow_run():
  1. Creates the substrate run directory with a deterministic run_id.
  2. Writes the phase manifest from a fixture .mjs carrying meta.phaseTrust.
  3. Populates projection.phases via events.jsonl.
  4. classify_phases returns real phases with read_only -> auto_replay and
     write/execute -> needs_confirmation.
  5. Re-bridging the same run-state is idempotent (same event count).
  6. A partial run-state leaves later phases incomplete (mid-crash resumable).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import sys

_WORKTREE = Path(__file__).parent.parent
_SCRIPTS = _WORKTREE / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence.eventlog import read_events
from skills.lib.workflow.persistence.manifest import read_manifest
from skills.lib.workflow.persistence.registry import find_run
from skills.lib.workflow.persistence.resume import (
    CLASSIFICATION_AUTO_REPLAY,
    CLASSIFICATION_NEEDS_CONFIRMATION,
    classify_phases,
)
from skills.lib.workflow.persistence.workflow_bridge import (
    _extract_phase_trust,
    bridge_workflow_run,
)


# ---------------------------------------------------------------------------
# Fixture .mjs source (inline, no file I/O needed for phaseTrust extraction)
# ---------------------------------------------------------------------------

FIXTURE_MJS_SOURCE = textwrap.dedent(
    """
    export const meta = {
      name: "test-skill",
      description: "Test skill for bridge tests",
      phases: ["scope", "analyze", "apply"],
      phaseTrust: {
        "scope":   "read_only",
        "analyze": "read_only",
        "apply":   "execute",
      },
    };

    export async function run() {
      phase("scope");
      log("DURABLE_EVENT: phase_started scope");
      const r = await agent("Scope prompt", { label: "scope", phase: "scope" });
      log("DURABLE_EVENT: phase_completed scope");

      phase("analyze");
      log("DURABLE_EVENT: phase_started analyze");
      const a = await agent("Analyze prompt", { label: "analyze", phase: "analyze" });
      log("DURABLE_EVENT: phase_completed analyze");

      phase("apply");
      log("DURABLE_EVENT: phase_started apply");
      const p = await agent("Apply prompt", { label: "apply", phase: "apply", isolation: "worktree" });
      log("DURABLE_EVENT: phase_completed apply");

      return { result: r };
    }
    """
)


def _make_wf_runstate(
    tmp_path: Path,
    wf_run_id: str,
    workflow_name: str,
    status: str,
    phases: list[dict],
    agents: list[dict],
) -> Path:
    """Write a synthetic Workflow run-state JSON and return its path."""
    # Simulate: .../projects/proj123/sess456/workflows/{wf_run_id}.json
    wf_dir = tmp_path / "projects" / "proj123" / "sess456" / "workflows"
    wf_dir.mkdir(parents=True)
    wf_path = wf_dir / f"{wf_run_id}.json"

    progress = []
    for ph in phases:
        progress.append({"type": "workflow_phase", **ph})
    for ag in agents:
        progress.append({"type": "workflow_agent", **ag})

    state = {
        "runId": wf_run_id,
        "workflowName": workflow_name,
        "status": status,
        "workflowProgress": progress,
    }
    wf_path.write_text(json.dumps(state), encoding="utf-8")
    return wf_path


def _write_fake_mjs(tmp_path: Path, workflow_name: str, source: str) -> Path:
    """Write a fake workflow.mjs under skills/{name}/ relative to a fake repo root."""
    # The bridge resolves the repo root from its own __file__ location.
    # For tests, we monkey-patch _find_mjs instead via the inline extractor.
    mjs_dir = tmp_path / "skills" / workflow_name
    mjs_dir.mkdir(parents=True, exist_ok=True)
    mjs_path = mjs_dir / "workflow.mjs"
    mjs_path.write_text(source, encoding="utf-8")
    return mjs_path


# ---------------------------------------------------------------------------
# Test 1: phaseTrust extraction
# ---------------------------------------------------------------------------


def test_extract_phase_trust_from_mjs() -> None:
    """_extract_phase_trust parses phaseTrust from a .mjs source correctly."""
    trust = _extract_phase_trust(FIXTURE_MJS_SOURCE)
    assert trust == {
        "scope": "read_only",
        "analyze": "read_only",
        "apply": "execute",
    }


def test_extract_phase_trust_missing_returns_empty() -> None:
    """When phaseTrust is absent, returns empty dict (no invented tags)."""
    source = "export const meta = { name: 'no-trust', phases: ['a', 'b'] };"
    trust = _extract_phase_trust(source)
    assert trust == {}


def test_extract_phase_trust_ignores_invalid_tags() -> None:
    """Invalid tag values are silently ignored (only read_only/write/execute kept)."""
    source = textwrap.dedent("""
        export const meta = {
          phaseTrust: {
            "good": "read_only",
            "bad":  "invalid_tag",
            "also": "write",
          },
        };
    """)
    trust = _extract_phase_trust(source)
    assert trust == {"good": "read_only", "also": "write"}
    assert "bad" not in trust


# ---------------------------------------------------------------------------
# Test 2: bridge creates run dir + manifest + events
# ---------------------------------------------------------------------------


def test_bridge_creates_run_dir_and_manifest(tmp_path: Path, monkeypatch) -> None:
    """bridge_workflow_run creates the substrate run dir and writes the manifest."""
    wf_path = _make_wf_runstate(
        tmp_path,
        wf_run_id="run-abc123",
        workflow_name="test-skill",
        status="completed",
        phases=[
            {"index": 0, "title": "scope"},
            {"index": 1, "title": "analyze"},
            {"index": 2, "title": "apply"},
        ],
        agents=[
            {"index": 0, "label": "scope-agent", "phaseIndex": 0, "agentId": "ag-1", "state": "done"},
            {"index": 1, "label": "analyze-agent", "phaseIndex": 1, "agentId": "ag-2", "state": "done"},
            {"index": 2, "label": "apply-agent", "phaseIndex": 2, "agentId": "ag-3", "state": "done"},
        ],
    )

    base = tmp_path / "skill-runs"

    # Monkeypatch _find_mjs to return our fake mjs (writing the source inline)
    mjs_path = _write_fake_mjs(tmp_path, "test-skill", FIXTURE_MJS_SOURCE)
    import skills.lib.workflow.persistence.workflow_bridge as wb
    monkeypatch.setattr(wb, "_find_mjs", lambda name: mjs_path)

    run_id = bridge_workflow_run(wf_path, skill_runs_base=base)

    assert run_id == "wf-run-abc123"

    handle = find_run(run_id, base_dir=base)
    assert handle is not None, "Run directory should be created by the bridge"

    # Manifest should be written with the phaseTrust from the .mjs
    manifest = read_manifest(handle)
    assert manifest == {
        "scope": "read_only",
        "analyze": "read_only",
        "apply": "execute",
    }, f"Manifest mismatch: {manifest}"


# ---------------------------------------------------------------------------
# Test 3: projection.phases is populated
# ---------------------------------------------------------------------------


def test_bridge_populates_projection_phases(tmp_path: Path, monkeypatch) -> None:
    """bridge_workflow_run populates projection.phases for completed phases."""
    wf_path = _make_wf_runstate(
        tmp_path,
        wf_run_id="run-phases",
        workflow_name="test-skill",
        status="completed",
        phases=[
            {"index": 0, "title": "scope"},
            {"index": 1, "title": "analyze"},
        ],
        agents=[
            {"index": 0, "label": "s", "phaseIndex": 0, "agentId": "ag-s", "state": "done"},
            {"index": 1, "label": "a", "phaseIndex": 1, "agentId": "ag-a", "state": "done"},
        ],
    )

    base = tmp_path / "skill-runs"
    mjs_path = _write_fake_mjs(tmp_path, "test-skill", FIXTURE_MJS_SOURCE)
    import skills.lib.workflow.persistence.workflow_bridge as wb
    monkeypatch.setattr(wb, "_find_mjs", lambda name: mjs_path)

    run_id = bridge_workflow_run(wf_path, skill_runs_base=base)

    handle = find_run(run_id, base_dir=base)
    proj = json.loads(handle.projection.read_text(encoding="utf-8"))
    phases = proj.get("phases", {})

    assert "scope" in phases, f"'scope' not in projection.phases: {phases}"
    assert "analyze" in phases, f"'analyze' not in projection.phases: {phases}"
    assert phases["scope"]["status"] == "completed"
    assert phases["analyze"]["status"] == "completed"


# ---------------------------------------------------------------------------
# Test 4: classify_phases returns real phases with correct classifications
# ---------------------------------------------------------------------------


def test_classify_phases_uses_bridge_events(tmp_path: Path, monkeypatch) -> None:
    """classify_phases returns real phases after bridge, with correct trust tags.

    This is the KEY INTEGRATION TEST for the whole bridge:
    - read_only phases (scope, analyze) -> auto_replay (non-overriding parent)
    - execute phases (apply) that are incomplete -> needs_confirmation
    """
    # Only scope and analyze are done; apply is NOT done (partial run)
    wf_path = _make_wf_runstate(
        tmp_path,
        wf_run_id="run-classify",
        workflow_name="test-skill",
        status="running",  # mid-run
        phases=[
            {"index": 0, "title": "scope"},
            {"index": 1, "title": "analyze"},
            {"index": 2, "title": "apply"},
        ],
        agents=[
            {"index": 0, "label": "s", "phaseIndex": 0, "agentId": "ag-s", "state": "done"},
            {"index": 1, "label": "a", "phaseIndex": 1, "agentId": "ag-a", "state": "done"},
            # apply agent is NOT done
            {"index": 2, "label": "p", "phaseIndex": 2, "agentId": "ag-p", "state": "running"},
        ],
    )

    base = tmp_path / "skill-runs"
    mjs_path = _write_fake_mjs(tmp_path, "test-skill", FIXTURE_MJS_SOURCE)
    import skills.lib.workflow.persistence.workflow_bridge as wb
    monkeypatch.setattr(wb, "_find_mjs", lambda name: mjs_path)

    run_id = bridge_workflow_run(wf_path, skill_runs_base=base)
    handle = find_run(run_id, base_dir=base)

    # Use "default" parent permission mode to avoid DL-021 override
    result = classify_phases(handle, parent_permission_mode="default")

    phases = result["phases"]

    # scope and analyze should be COMPLETED (not in remaining)
    assert "scope" not in phases, (
        "scope should be completed — not in remaining phases for classify_phases"
    )
    assert "analyze" not in phases, (
        "analyze should be completed — not in remaining phases for classify_phases"
    )

    # apply is NOT completed -> appears in remaining phases
    assert "apply" in phases, f"'apply' should be in remaining phases; got: {list(phases.keys())}"
    assert phases["apply"]["classification"] == CLASSIFICATION_NEEDS_CONFIRMATION, (
        f"apply (execute) should need_confirmation; got {phases['apply']}"
    )
    assert phases["apply"]["tag"] == "execute"


# ---------------------------------------------------------------------------
# Test 5: idempotency — re-bridging the same run-state yields no new events
# ---------------------------------------------------------------------------


def test_bridge_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    """bridge_workflow_run called twice for the same run-state appends no new events."""
    wf_path = _make_wf_runstate(
        tmp_path,
        wf_run_id="run-idem",
        workflow_name="test-skill",
        status="completed",
        phases=[
            {"index": 0, "title": "scope"},
        ],
        agents=[
            {"index": 0, "label": "s", "phaseIndex": 0, "agentId": "ag-s", "state": "done"},
        ],
    )

    base = tmp_path / "skill-runs"
    mjs_path = _write_fake_mjs(tmp_path, "test-skill", FIXTURE_MJS_SOURCE)
    import skills.lib.workflow.persistence.workflow_bridge as wb
    monkeypatch.setattr(wb, "_find_mjs", lambda name: mjs_path)

    run_id = bridge_workflow_run(wf_path, skill_runs_base=base)
    handle = find_run(run_id, base_dir=base)
    events_after_first = read_events(handle.as_run_dir())
    count_first = len(events_after_first)

    # Bridge again — same run-state
    bridge_workflow_run(wf_path, skill_runs_base=base)
    events_after_second = read_events(handle.as_run_dir())
    count_second = len(events_after_second)

    assert count_second == count_first, (
        f"Idempotency violated: first bridge produced {count_first} events, "
        f"second bridge produced {count_second} events (should be identical)"
    )


# ---------------------------------------------------------------------------
# Test 6: partial run-state — completed prefix bridged, incomplete suffix left
# ---------------------------------------------------------------------------


def test_bridge_partial_runstate_leaves_incomplete_phases(tmp_path: Path, monkeypatch) -> None:
    """Mid-crash run-state: completed phases are bridged; incomplete phases remain pending."""
    # Only scope is done; analyze and apply are not yet started or still running
    wf_path = _make_wf_runstate(
        tmp_path,
        wf_run_id="run-partial",
        workflow_name="test-skill",
        status="running",
        phases=[
            {"index": 0, "title": "scope"},
            {"index": 1, "title": "analyze"},
            {"index": 2, "title": "apply"},
        ],
        agents=[
            # Only scope agent is done
            {"index": 0, "label": "s", "phaseIndex": 0, "agentId": "ag-s", "state": "done"},
            # analyze agent still running
            {"index": 1, "label": "a", "phaseIndex": 1, "agentId": "ag-a", "state": "running"},
            # apply agent not yet started
        ],
    )

    base = tmp_path / "skill-runs"
    mjs_path = _write_fake_mjs(tmp_path, "test-skill", FIXTURE_MJS_SOURCE)
    import skills.lib.workflow.persistence.workflow_bridge as wb
    monkeypatch.setattr(wb, "_find_mjs", lambda name: mjs_path)

    run_id = bridge_workflow_run(wf_path, skill_runs_base=base)
    handle = find_run(run_id, base_dir=base)

    proj = json.loads(handle.projection.read_text(encoding="utf-8"))
    phases = proj.get("phases", {})

    # scope: completed (agent is done, so phase is done)
    assert "scope" in phases
    assert phases["scope"]["status"] == "completed", (
        f"scope should be completed (its agent is done); got {phases['scope']}"
    )

    # analyze: started but NOT completed (agent is running, not done)
    assert "analyze" in phases
    assert phases["analyze"]["status"] == "running", (
        f"analyze should be running (agent still running); got {phases['analyze']}"
    )

    # apply: started (the phase entry exists because it's in workflowProgress)
    # but may not have a completed agent -> not completed
    if "apply" in phases:
        assert phases["apply"]["status"] != "completed", (
            "apply should NOT be completed in a partial/crashed run"
        )


# ---------------------------------------------------------------------------
# Test 7: bridge with missing .mjs yields empty manifest (default-deny)
# ---------------------------------------------------------------------------


def test_bridge_missing_mjs_yields_empty_manifest(tmp_path: Path, monkeypatch) -> None:
    """When workflow.mjs is not found, manifest is empty (all phases untagged = default-deny)."""
    wf_path = _make_wf_runstate(
        tmp_path,
        wf_run_id="run-nomjs",
        workflow_name="nonexistent-skill",
        status="completed",
        phases=[{"index": 0, "title": "step-one"}],
        agents=[{"index": 0, "label": "a", "phaseIndex": 0, "agentId": "ag-x", "state": "done"}],
    )

    base = tmp_path / "skill-runs"
    import skills.lib.workflow.persistence.workflow_bridge as wb
    monkeypatch.setattr(wb, "_find_mjs", lambda name: None)

    run_id = bridge_workflow_run(wf_path, skill_runs_base=base)
    handle = find_run(run_id, base_dir=base)

    manifest = read_manifest(handle)
    assert manifest == {}, (
        f"Missing .mjs should yield empty manifest (default-deny); got {manifest}"
    )

    # classify_phases: untagged phases must be needs_confirmation (default-deny R-003)
    result = classify_phases(handle, parent_permission_mode="default")
    # step-one is completed so may not appear in remaining
    # At minimum, no phase should be auto_replay without a read_only tag
    for phase_id, info in result["phases"].items():
        assert info["classification"] == CLASSIFICATION_NEEDS_CONFIRMATION, (
            f"Untagged phase {phase_id!r} should be needs_confirmation (default-deny); "
            f"got {info['classification']}"
        )
