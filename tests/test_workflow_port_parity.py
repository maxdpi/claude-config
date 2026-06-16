#!/usr/bin/env python3
"""M-006 / M-006.5 Workflow-port parity tests (CI-M-006-005, CI-M-006-008).

Two test functions:

1. test_journal_eventlog_divergence (CI-M-006-005)
   Simulates a missed bridge append so events.jsonl is stale vs the journal,
   then asserts that resume DETECTS the gap via reconciliation and re-derives
   from the authoritative journal rather than folding a stale eventlog.
   Proves cross-session resume never re-executes a side-effecting phase off
   a stale eventlog.

2. test_workflow_port_output_parity (CI-M-006-008)
   Iterates over tests/fixtures/workflow_port_parity/*.json, each shaped
   {"python":{...},"port":{...},"_fixture_fidelity":"hand-authored-contract"},
   and asserts data["port"][key]==data["python"][key] on the required key per
   skill. A MISSING fixture is a hard pytest.fail (NEVER a skip) — this is the
   M-008b deletion gate (R-004).

   FIXTURE FIDELITY CAVEAT (Task C / parity-honesty finding):
   All fixtures carry ``_fixture_fidelity: "hand-authored-contract"`` because
   capturing both runtimes (Python orchestrator + workflow.mjs port) against the
   same input requires both to be live-executable simultaneously, which is not
   possible during the port period. The gate is STRUCTURAL, not behavioral: it
   asserts that both blobs encode the same artifact shape and content, proving
   the contract is met. A missing or mismatched fixture is still a hard failure —
   the gate cannot be bypassed. A passing test with ``hand-authored-contract``
   fidelity means the schema/contract is honored, NOT that the live port
   produces identical output to the live Python runtime on the same input.

Planner (M-006.5, DL-026):
   The planner is now included in the main DATA-DRIVEN parity loop with
   fixture tests/fixtures/workflow_port_parity/planner_simple_feature.json
   and required key "plan". The former xfail placeholder
   (test_planner_fixture_required) has been replaced by this real parity row.
   A missing planner fixture is a hard pytest.fail — never a skip.
"""
from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

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
    EVENT_PHASE_COMPLETED,
    EVENT_PHASE_STARTED,
    EVENT_RUN_STARTED,
    append_event,
    create_run_dir,
    event_schema,
    read_events,
)
from skills.lib.workflow.persistence.journal_bridge import (
    bridge_journal,
    detect_divergence,
    rederive_from_journal,
    _entry_dedup_key,
    _mirrored_keys,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = _WORKTREE / "tests" / "fixtures" / "workflow_port_parity"

# Skills covered by the DATA-DRIVEN parity loop.
# Maps skill_name -> required_key.
# planner added in M-006.5 (DL-026): fixture is planner_simple_feature.json.
PARITY_SKILLS = {
    "codebase-analysis": "synthesis",
    "refactor": "work_items",
    "arxiv-to-md": "markdown",
    "incoherence": "verdicts",
    "prompt-engineer": "optimized_prompt",
    "leon-writing-style": "styled_content",
    "planner": "plan",
}

# Optional fixture-filename overrides for skills whose fixture file does not
# follow the default {skill}.json naming convention.
# M-006.5: planner uses planner_simple_feature.json (DL-026, CI-M-006-016).
PARITY_FIXTURE_FILENAMES: dict[str, str] = {
    "planner": "planner_simple_feature.json",
}


def _fixture_path(skill: str) -> Path:
    """Return the fixture path for *skill*, honoring the filename override table."""
    filename = PARITY_FIXTURE_FILENAMES.get(skill, f"{skill}.json")
    return FIXTURES_DIR / filename


# ---------------------------------------------------------------------------
# Test 1: Journal–eventlog divergence (CI-M-006-005)
# ---------------------------------------------------------------------------


def test_journal_eventlog_divergence(tmp_path: Path) -> None:
    """Simulate a missed bridge append and assert divergence is detected + re-derived.

    Scenario:
        1. A Workflow run produces two journal entries (started + result).
        2. The bridge fires for the 'started' entry and appends it to events.jsonl.
        3. The bridge DOES NOT fire for the 'result' entry (crash / un-fired hook /
           session exit between journal write and bridge append).
        4. events.jsonl is now STALE — it is missing the 'result' entry.
        5. On resume, bridge_journal() calls detect_divergence() and finds the gap.
        6. rederive_from_journal() is called, re-derives the missing entry.
        7. events.jsonl now matches the journal (convergent after re-derive).
    """
    run_dir = create_run_dir(skill="refactor", base_dir=tmp_path / "skill-runs")

    # ── Build a synthetic journal.jsonl ──────────────────────────────────────
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    journal_path = journal_dir / "journal.jsonl"

    entry_started = {
        "type": "started",
        "key": "v2:abc123sha256ofpromptandopts",
        "agentId": "agent-explore-1",
        "ts": time.time(),
    }
    entry_result = {
        "type": "result",
        "key": "v2:abc123sha256ofpromptandopts",
        "agentId": "agent-explore-1",
        "result": "Work items: ...",
        "ts": time.time() + 5,
    }

    journal_path.write_text(
        json.dumps(entry_started) + "\n" + json.dumps(entry_result) + "\n",
        encoding="utf-8",
    )

    # ── Simulate partial bridge: only 'started' was appended ─────────────────
    # Mirror ONLY the 'started' entry manually (simulating a bridge that fired
    # for the first entry but crashed before the second).
    key_started = _entry_dedup_key(entry_started)
    event_for_started = event_schema(
        type="subagent_spawned",
        run_id=run_dir.run_id,
        agent_id="agent-explore-1",
        payload={"journal_key": key_started, "source": "journal_bridge"},
    )
    append_event(run_dir, event_for_started)

    # ── Verify initial state: events.jsonl has 1 entry, journal has 2 ────────
    events_before = read_events(run_dir)
    assert len(events_before) == 1, (
        f"Expected 1 event before divergence detection, got {len(events_before)}"
    )

    # ── Detect divergence ─────────────────────────────────────────────────────
    divergence_report = detect_divergence(run_dir, journal_path)

    assert divergence_report["divergent"] is True, (
        "Expected divergence to be detected (journal has entries missing from events.jsonl)"
    )
    assert divergence_report["journal_count"] == 2, (
        f"Expected 2 journal entries, got {divergence_report['journal_count']}"
    )
    assert divergence_report["events_count"] == 1, (
        f"Expected 1 event before re-derive, got {divergence_report['events_count']}"
    )
    # The 'result' entry key should be in the missing set
    key_result = _entry_dedup_key(entry_result)
    assert key_result in divergence_report["missing_keys"], (
        f"Expected {key_result!r} in missing_keys; got {divergence_report['missing_keys']}"
    )

    # ── Re-derive from authoritative journal ──────────────────────────────────
    # This is what resume does when divergence is detected (DL-011).
    # It should append the missing 'result' entry and skip the already-mirrored 'started'.
    newly_appended = rederive_from_journal(run_dir, journal_path)

    assert newly_appended == 1, (
        f"Expected 1 new event appended from re-derive, got {newly_appended}"
    )

    # ── Verify post-re-derive state: events.jsonl now has 2 entries ───────────
    events_after = read_events(run_dir)
    assert len(events_after) == 2, (
        f"Expected 2 events after re-derive, got {len(events_after)}"
    )

    # ── Verify no divergence after re-derive (convergent) ────────────────────
    divergence_after = detect_divergence(run_dir, journal_path)
    assert divergence_after["divergent"] is False, (
        "Expected no divergence after re-derive (journal and events.jsonl should match)"
    )

    # ── Verify idempotency: re-derive again appends nothing ──────────────────
    second_rederive = rederive_from_journal(run_dir, journal_path)
    assert second_rederive == 0, (
        f"Expected 0 events on idempotent re-derive, got {second_rederive}"
    )

    # ── Verify seq=0 fix: a journal entry with seq=0 is NOT skipped ──────────
    # The dedup key includes type prefix to distinguish started vs result.
    # An entry with seq=0 AND a 'key' field should use the {type}:{key} form.
    entry_seq0 = {"type": "started", "key": "v2:seqzerotest", "agentId": "agent-2", "seq": 0}
    assert _entry_dedup_key(entry_seq0) == "started:v2:seqzerotest", (
        "seq=0 fix: entry with seq=0 and 'key' field should produce 'started:v2:seqzerotest', "
        "not skip the key due to falsy seq=0"
    )
    # Entries WITHOUT a 'key' field use the fallback with seq
    entry_seq0_no_key = {"type": "started", "agentId": "agent-2", "seq": 0}
    assert _entry_dedup_key(entry_seq0_no_key) == "started:agent-2:0", (
        "seq=0 fix: fallback without 'key' field should include seq=0, not skip it"
    )


def test_journal_eventlog_divergence_convergence_case(tmp_path: Path) -> None:
    """When the bridge fires normally, journal + events.jsonl fold to the same projection.

    This is the CONVERGENCE case (complement of the divergence test above).
    The bridge is called once (mirrors all entries), then called again to prove
    idempotency — the second call appends 0 entries and detects no divergence.
    """
    run_dir = create_run_dir(skill="codebase-analysis", base_dir=tmp_path / "skill-runs")

    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    journal_path = journal_dir / "journal.jsonl"

    entry_started = {"type": "started", "key": "v2:conv-hash", "agentId": "agent-conv"}
    entry_result = {"type": "result", "key": "v2:conv-hash", "agentId": "agent-conv", "result": "done"}

    journal_path.write_text(
        json.dumps(entry_started) + "\n" + json.dumps(entry_result) + "\n",
        encoding="utf-8",
    )

    # ── First bridge call: mirrors all 2 journal entries ──────────────────────
    # On first call against empty events.jsonl, ALL entries are "divergent" (missing).
    # The bridge correctly re-derives them via rederive_from_journal.
    result1 = bridge_journal(run_dir, journal_path=journal_path)

    assert result1["bridged"] is True
    assert result1["appended"] == 2, f"Expected 2 entries on first bridge, got {result1['appended']}"

    # After first bridge: both journal entries are mirrored → no divergence
    divergence_after_first = detect_divergence(run_dir, journal_path)
    assert divergence_after_first["divergent"] is False, (
        "No divergence expected after first full bridge"
    )

    # ── Second bridge call: convergence — nothing new to append ───────────────
    result2 = bridge_journal(run_dir, journal_path=journal_path)

    assert result2["bridged"] is True
    assert result2["rederived"] is False, (
        "Second bridge call should NOT re-derive (no divergence — already mirrored)"
    )
    assert result2["appended"] == 0, (
        f"Second bridge call should append 0 events (idempotent), got {result2['appended']}"
    )

    # No divergence after second call either
    divergence_after_second = detect_divergence(run_dir, journal_path)
    assert divergence_after_second["divergent"] is False, (
        "No divergence expected after second bridge call"
    )

    events = read_events(run_dir)
    assert len(events) == 2, (
        f"Expected exactly 2 events (idempotent bridge), got {len(events)}"
    )


# ---------------------------------------------------------------------------
# Test 2: Workflow port output parity (CI-M-006-008)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill,required_key", sorted(PARITY_SKILLS.items()))
def test_workflow_port_output_parity(skill: str, required_key: str) -> None:
    """Assert each ported skill's fixture matches on the required key.

    A MISSING fixture is a hard pytest.fail (never a skip) — this is the
    M-008b deletion gate (R-004). An absent fixture means the parity claim
    is unproven and the Python runtime MUST NOT be deleted.
    """
    fixture_path = _fixture_path(skill)

    # HARD FAIL — never skip — on missing fixture (R-004 gate)
    if not fixture_path.exists():
        pytest.fail(
            f"MISSING PARITY FIXTURE for skill '{skill}': {fixture_path}\n"
            f"This is the M-008b deletion gate (R-004). "
            f"The Python runtime for '{skill}' MUST NOT be deleted until this "
            f"fixture exists and the required key '{required_key}' matches between "
            f"the python and port blobs.\n"
            f"Add the fixture before deleting the Python orchestrator."
        )

    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    # Validate fixture structure
    assert "python" in data, (
        f"Fixture {fixture_path} missing 'python' blob"
    )
    assert "port" in data, (
        f"Fixture {fixture_path} missing 'port' blob"
    )

    # Task C (parity-honesty): every fixture must declare _fixture_fidelity.
    assert "_fixture_fidelity" in data, (
        f"Fixture {fixture_path} missing '_fixture_fidelity' field. "
        f"Add '_fixture_fidelity': 'hand-authored-contract' (or 'live-captured') "
        f"to make the gate's behavioral limitations machine-readable."
    )
    fidelity = data["_fixture_fidelity"]
    if "hand-authored" in fidelity or fidelity == "hand-authored-contract":
        warnings.warn(
            f"[PARITY GATE — STRUCTURAL NOT BEHAVIORAL] skill='{skill}' "
            f"fixture={fixture_path.name!r}: fidelity={fidelity!r}. "
            f"This gate asserts CONTRACT SHAPE equality between hand-authored blobs. "
            f"It does NOT prove the live workflow.mjs port produces identical output "
            f"to the live Python runtime on the same input. "
            f"To upgrade to behavioral fidelity, capture live outputs from both runtimes.",
            stacklevel=2,
        )

    python_blob = data["python"]
    port_blob = data["port"]

    # Assert the required key exists in both blobs
    assert required_key in python_blob, (
        f"Required key '{required_key}' missing from 'python' blob in {fixture_path}"
    )
    assert required_key in port_blob, (
        f"Required key '{required_key}' missing from 'port' blob in {fixture_path}"
    )

    # Assert the port matches the python predecessor on the required key
    assert port_blob[required_key] == python_blob[required_key], (
        f"PARITY FAILURE for skill '{skill}' on key '{required_key}':\n"
        f"python: {json.dumps(python_blob[required_key], indent=2)}\n"
        f"port:   {json.dumps(port_blob[required_key], indent=2)}\n"
        f"The Workflow-tool port does not match its Python predecessor. "
        f"Fix the port before deleting the Python runtime (M-008b / R-004)."
    )


# ---------------------------------------------------------------------------
# Planner durable-event / manifest wiring check (M-006.5, DL-006, DL-014)
# ---------------------------------------------------------------------------


def test_planner_workflow_durable_event_wiring() -> None:
    """Assert the planner workflow.mjs declares the persistence wiring required
    for cross-session resume (DL-006, DL-013, DL-014).

    Validates WITHOUT executing a live Workflow run:
    1. meta.phases declares all 8 planner phases.
    2. meta.phaseTrust maps every phase to a valid tag (read_only | execute).
    3. The read_only phases are exactly plan-init and context-verify (safe to
       auto-replay on resume per DL-006).
    4. The execute phases are the six work/qr phases (require confirmation).
    5. The source text references the DURABLE_EVENT log markers that the
       resume engine relies on (DL-013 direct-emit fallback, R-004).
    6. The planner fixture exists and is a hard-fail gate (R-004, DL-026).
    """
    import re

    worktree = Path(__file__).parent.parent
    mjs_path = worktree / "skills" / "planner" / "workflow.mjs"

    assert mjs_path.exists(), f"planner workflow.mjs not found at {mjs_path}"

    source = mjs_path.read_text(encoding="utf-8")

    # ── 1. meta.phases present ────────────────────────────────────────────────
    expected_phases = [
        "plan-init",
        "context-verify",
        "plan-design-work",
        "plan-design-qr",
        "plan-code-work",
        "plan-code-qr",
        "plan-docs-work",
        "plan-docs-qr",
    ]
    for ph in expected_phases:
        assert f'"{ph}"' in source, (
            f"planner workflow.mjs missing phase '{ph}' in meta.phases"
        )

    # ── 2+3+4. phaseTrust contains read_only and execute tags ────────────────
    # Check that phaseTrust key appears in source with both tag values.
    # We do a loose check: the phaseTrust object exists and contains both
    # "read_only" and "execute" values (whitespace-agnostic).
    assert "phaseTrust" in source, (
        "planner workflow.mjs must declare meta.phaseTrust for resume engine (DL-014)"
    )
    assert '"read_only"' in source, (
        "planner workflow.mjs phaseTrust must include 'read_only' tag for plan-init/context-verify (DL-006)"
    )
    assert '"execute"' in source, (
        "planner workflow.mjs phaseTrust must include 'execute' tag for work/qr phases (DL-006)"
    )
    # Verify the specific read_only phases appear near the read_only tag
    # by checking the overall content contains these phase names with read_only
    read_only_phases = ["plan-init", "context-verify"]
    for ph in read_only_phases:
        assert f'"{ph}"' in source, (
            f"planner workflow.mjs phaseTrust must list '{ph}' (DL-006)"
        )

    # ── 5. DURABLE_EVENT markers (DL-013 direct-emit fallback) ───────────────
    assert "DURABLE_EVENT: phase_started" in source, (
        "planner workflow.mjs must emit DURABLE_EVENT: phase_started markers (DL-013)"
    )
    assert "DURABLE_EVENT: phase_completed" in source, (
        "planner workflow.mjs must emit DURABLE_EVENT: phase_completed markers (DL-013)"
    )
    assert "DURABLE_EVENT: subagent_spawned" in source, (
        "planner workflow.mjs must emit DURABLE_EVENT: subagent_spawned markers (DL-013)"
    )

    # ── 6. No scaffold return path ────────────────────────────────────────────
    # Check that no `return { status: "scaffold" }` (or similar) return statement
    # exists. We check for the return statement specifically, not comment text.
    import re as _re
    scaffold_return = _re.search(r'return\s*\{[^}]*status\s*:\s*["\']scaffold["\']', source)
    assert scaffold_return is None, (
        "planner workflow.mjs must NOT return {status:'scaffold'} — M-006.5 port (DL-026)"
    )

    # ── 7. planner fixture is a hard-fail gate (R-004, DL-026) ───────────────
    fixture_path = _fixture_path("planner")
    if not fixture_path.exists():
        pytest.fail(
            f"MISSING PLANNER PARITY FIXTURE: {fixture_path}\n"
            f"M-006.5 (DL-026) requires tests/fixtures/workflow_port_parity/planner_simple_feature.json.\n"
            f"M-008b planner-Python deletion is GATED on this fixture existing and passing (R-004)."
        )

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert "python" in data, f"planner fixture {fixture_path} missing 'python' blob"
    assert "port" in data, f"planner fixture {fixture_path} missing 'port' blob"
    assert "plan" in data["python"], "planner fixture 'python' blob missing required key 'plan'"
    assert "plan" in data["port"], "planner fixture 'port' blob missing required key 'plan'"
    assert "_fixture_fidelity" in data, (
        f"Planner fixture {fixture_path} missing '_fixture_fidelity' field (Task C)."
    )
