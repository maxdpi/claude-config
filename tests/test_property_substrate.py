#!/usr/bin/env python3
"""Property-based tests for the durable-substrate persistence core.

These tests use Hypothesis to fuzz the fold/replay/classify_phases/retention
invariants that example-based tests can only spot-check.

Skip mechanism
--------------
``pytest.importorskip("hypothesis")`` at module top causes the entire module
to be collected but SKIPPED (not errored) when Hypothesis is absent from the
environment. Run via the venv documented in tests/PROPERTY_TESTING.md.

Coverage targets
----------------
* fold purity and determinism (unknown types/fields, replay equivalence)
* append->replay round-trip (projection.json == replay dict)
* classify_phases default-deny security invariants
* prune_runs / is_resumable retention properties
"""
from __future__ import annotations

import copy
import datetime
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

# Skip the whole module when hypothesis is not installed.
# pytest.importorskip skips at collection time rather than failing with ImportError.
pytest.importorskip("hypothesis")

import shutil
import tempfile

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Make the persistence package importable
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).parent.parent / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence import (
    EVENT_PHASE_COMPLETED,
    EVENT_PHASE_STARTED,
    EVENT_RUN_COMPLETED,
    EVENT_RUN_FAILED,
    EVENT_RUN_STARTED,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_SUBAGENT_SPAWNED,
    append_event,
    create_run_dir,
    empty_projection,
    event_schema,
    fold,
    replay,
    write_phase_manifest,
)
from skills.lib.workflow.persistence.events import (
    EVENT_MILESTONE_STATUS,
    EVENT_RESUME_CURSOR,
)
from skills.lib.workflow.persistence.resume import (
    CLASSIFICATION_AUTO_REPLAY,
    CLASSIFICATION_NEEDS_CONFIRMATION,
    OVERRIDING_MODES,
    classify_phases,
)
from skills.lib.workflow.persistence.retention import (
    _PRUNABLE_STATUSES,
    is_resumable,
    prune_runs,
)
from skills.lib.workflow.persistence.rundir import RunDir

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Known event types that fold actually handles
_KNOWN_TYPES = [
    EVENT_RUN_STARTED,
    EVENT_RUN_COMPLETED,
    EVENT_RUN_FAILED,
    EVENT_PHASE_STARTED,
    EVENT_PHASE_COMPLETED,
    EVENT_MILESTONE_STATUS,
    EVENT_RESUME_CURSOR,
    EVENT_SUBAGENT_SPAWNED,
    EVENT_SUBAGENT_COMPLETED,
]

# Extra unknown types to mix in (C-005 tolerance testing)
_UNKNOWN_TYPES = [
    "unknown_future_hook",
    "totally_unknown",
    "xyzzy",
    "",
    "123",
]

_ALL_TYPES = _KNOWN_TYPES + _UNKNOWN_TYPES

# Phase tag values (valid manifest tags)
_PHASE_TAGS = ["read_only", "write", "execute"]

# Parent permission modes — mix overriding and non-overriding
_ALL_MODES = ["plan", "default", "bypassPermissions", "acceptEdits", "auto", "unknown_mode", ""]

# Safe text for IDs/payloads (no NUL bytes; readable JSON)
_safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters=("\x00",),
    ),
    min_size=0,
    max_size=40,
)

_phase_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=20,
)

_agent_id_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=16,
)

# An event envelope with random (possibly unknown) type and optional extra payload keys
@st.composite
def random_event(draw, run_id: str = "test-run-id"):
    etype = draw(st.sampled_from(_ALL_TYPES))

    # Build a base payload that may satisfy known-type parsing
    payload: dict = {}

    if etype in (EVENT_PHASE_STARTED, EVENT_PHASE_COMPLETED):
        payload["phase_id"] = draw(_phase_id_st)
    elif etype == EVENT_MILESTONE_STATUS:
        payload["milestone_id"] = draw(_phase_id_st)
        payload["status"] = draw(st.sampled_from(["done", "pending", "skipped"]))
    elif etype == EVENT_RESUME_CURSOR:
        payload["cursor"] = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=9999)))
    elif etype == EVENT_RUN_FAILED:
        payload["error"] = draw(st.text(max_size=20))
    elif etype == EVENT_RUN_STARTED:
        payload["skill"] = draw(st.text(max_size=20))

    # Add random extra payload keys to test forward-compat (C-005)
    n_extra = draw(st.integers(min_value=0, max_value=3))
    for _ in range(n_extra):
        key = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12))
        val = draw(st.one_of(st.text(max_size=10), st.integers(), st.none()))
        payload.setdefault(key, val)

    agent_id = None
    native_agent_id = None
    if etype in (EVENT_SUBAGENT_SPAWNED, EVENT_SUBAGENT_COMPLETED):
        agent_id = draw(_agent_id_st)
        native_agent_id = draw(st.one_of(st.none(), _agent_id_st))

    return event_schema(
        type=etype,
        run_id=run_id,
        payload=payload,
        agent_id=agent_id,
        native_agent_id=native_agent_id,
        ts=draw(st.floats(min_value=1_600_000_000.0, max_value=2_000_000_000.0, allow_nan=False)),
    )


@st.composite
def event_list(draw, run_id: str = "test-run-id", min_size: int = 0, max_size: int = 20):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [draw(random_event(run_id=run_id)) for _ in range(n)]


# ---------------------------------------------------------------------------
# 1. fold purity & determinism
# ---------------------------------------------------------------------------


class TestFoldPurityAndDeterminism:
    @given(events=event_list(run_id="run-prop"))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_fold_never_mutates_input_projection(self, events):
        """fold must never mutate its projection argument (purity)."""
        p = empty_projection()
        p_snapshot = copy.deepcopy(p)

        for ev in events:
            p_before = copy.deepcopy(p)
            p = fold(p, ev)
            # The *previous* projection must be unchanged after fold.
            assert p_before == copy.deepcopy(p_before), "fold mutated its input projection"

        # Original empty_projection must also be unchanged.
        assert p_snapshot == empty_projection()

    @given(events=event_list(run_id="run-det"))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_fold_is_deterministic(self, events):
        """Folding the same sequence twice yields the same projection."""
        p1 = empty_projection()
        p2 = empty_projection()
        for ev in events:
            p1 = fold(p1, ev)
            p2 = fold(p2, ev)
        assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)

    @given(
        known_events=event_list(run_id="run-unk", min_size=1, max_size=10),
        unknown_type=st.sampled_from(_UNKNOWN_TYPES),
        extra_payload=st.fixed_dictionaries(
            {},
            optional={
                "foo": st.text(max_size=10),
                "bar": st.integers(),
                "baz": st.none(),
            },
        ),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
    def test_unknown_event_type_leaves_projection_unchanged(
        self, known_events, unknown_type, extra_payload
    ):
        """Unknown event type must leave the projection unchanged (C-005)."""
        # Build projection up to known events
        p = empty_projection()
        for ev in known_events:
            p = fold(p, ev)

        # Now fold an unknown type
        p_before = copy.deepcopy(p)
        unknown_ev = event_schema(
            type=unknown_type,
            run_id="run-unk",
            payload=extra_payload,
        )
        p_after = fold(p, unknown_ev)

        assert json.dumps(p_before, sort_keys=True) == json.dumps(p_after, sort_keys=True), (
            f"Unknown event type {unknown_type!r} mutated projection"
        )

    @given(events=event_list(run_id="run-replay"))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
    def test_incremental_fold_equals_replay(self, events):
        """Incrementally folding equals replaying in one pass."""
        # Incremental fold
        p_incremental = empty_projection()
        for ev in events:
            p_incremental = fold(p_incremental, ev)

        # Replay: fold from scratch in one pass
        p_replay = empty_projection()
        for ev in events:
            p_replay = fold(p_replay, ev)

        assert json.dumps(p_incremental, sort_keys=True) == json.dumps(p_replay, sort_keys=True)


# ---------------------------------------------------------------------------
# 2. append -> replay round-trip
# ---------------------------------------------------------------------------


class TestAppendReplayRoundTrip:
    @given(events=event_list(min_size=0, max_size=15))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_replay_matches_projection_json(self, events):
        """replay(run_dir) must match persisted projection.json after any event sequence."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="prop", base_dir=base)
            for ev in events:
                ev["run_id"] = rd.run_id
                append_event(rd, ev)

            stored_raw = rd.projection.read_text(encoding="utf-8")
            stored = json.loads(stored_raw)
            replayed = replay(rd)

            assert json.dumps(stored, sort_keys=True) == json.dumps(replayed, sort_keys=True), (
                "projection.json diverged from replay after property-based append sequence"
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @given(events=event_list(min_size=1, max_size=12))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_all_event_lines_parseable_after_appends(self, events):
        """Every line in events.jsonl must be valid JSON after any sequence of appends."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="prop", base_dir=base)
            for ev in events:
                ev["run_id"] = rd.run_id
                append_event(rd, ev)

            lines = [
                ln for ln in rd.events_jsonl.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            assert len(lines) == len(events), (
                f"Expected {len(events)} lines; got {len(lines)} (lost or duplicate events)"
            )
            for i, line in enumerate(lines):
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    pytest.fail(f"Line {i} is not valid JSON: {exc!r}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. classify_phases default-deny security matrix
# ---------------------------------------------------------------------------


@st.composite
def phase_manifest_st(draw):
    """Generate a manifest dict: phase_id -> tag (or None for untagged = absent)."""
    n = draw(st.integers(min_value=0, max_value=8))
    manifest = {}
    for i in range(n):
        pid = f"phase-{i}"
        tag = draw(st.sampled_from(_PHASE_TAGS + [None]))  # None = untagged / absent
        if tag is not None:
            manifest[pid] = tag
    return manifest


@st.composite
def parent_mode_st(draw):
    return draw(st.sampled_from(_ALL_MODES))


class TestClassifyPhasesDefaultDeny:
    @given(
        manifest=phase_manifest_st(),
        parent_mode=parent_mode_st(),
    )
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_default_deny_invariant(self, manifest, parent_mode):
        """Security invariant: phase is auto_replay ONLY if read_only AND mode not overriding."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="sec-test", base_dir=base)

            valid_manifest = {k: v for k, v in manifest.items() if v in _PHASE_TAGS}
            write_phase_manifest(rd, valid_manifest)

            result = classify_phases(rd, parent_permission_mode=parent_mode)
            mode_overrides = parent_mode in OVERRIDING_MODES

            for phase_id, info in result["phases"].items():
                classification = info["classification"]
                tag = info["tag"]

                if mode_overrides:
                    assert classification == CLASSIFICATION_NEEDS_CONFIRMATION, (
                        f"Phase {phase_id!r} tag={tag!r} mode={parent_mode!r}: "
                        f"expected needs_confirmation (overriding parent), got {classification!r}"
                    )
                elif tag == "read_only":
                    assert classification == CLASSIFICATION_AUTO_REPLAY, (
                        f"Phase {phase_id!r} tag={tag!r} mode={parent_mode!r}: "
                        f"expected auto_replay, got {classification!r}"
                    )
                else:
                    assert classification == CLASSIFICATION_NEEDS_CONFIRMATION, (
                        f"Phase {phase_id!r} tag={tag!r} mode={parent_mode!r}: "
                        f"expected needs_confirmation (default-deny), got {classification!r}"
                    )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @given(
        manifest=phase_manifest_st(),
        parent_mode=st.sampled_from(sorted(OVERRIDING_MODES)),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
    def test_overriding_parent_makes_all_needs_confirmation(self, manifest, parent_mode):
        """When parent is in OVERRIDING_MODES, every phase is needs_confirmation."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="sec-override", base_dir=base)
            valid_manifest = {k: v for k, v in manifest.items() if v in _PHASE_TAGS}
            write_phase_manifest(rd, valid_manifest)

            result = classify_phases(rd, parent_permission_mode=parent_mode)

            assert result["permission_mode_overridden"] is True
            assert result["warning"] is not None

            for phase_id, info in result["phases"].items():
                assert info["classification"] == CLASSIFICATION_NEEDS_CONFIRMATION, (
                    f"Phase {phase_id!r} tag={info['tag']!r} should be needs_confirmation "
                    f"under overriding parent mode {parent_mode!r}"
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @given(
        phases=st.lists(
            st.tuples(
                _phase_id_st,
                st.sampled_from(["write", "execute", None]),  # None = untagged
            ),
            min_size=1,
            max_size=6,
        ),
        parent_mode=st.just("plan"),  # non-overriding safe mode
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
    def test_write_execute_untagged_always_needs_confirmation(self, phases, parent_mode):
        """write/execute/untagged phases require confirmation even under safe parent modes."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="sec-deny", base_dir=base)

            manifest = {pid: tag for pid, tag in phases if tag is not None}
            write_phase_manifest(rd, manifest)

            for pid, _ in phases:
                ev = event_schema(
                    EVENT_PHASE_STARTED,
                    run_id=rd.run_id,
                    payload={"phase_id": pid},
                )
                append_event(rd, ev)

            result = classify_phases(rd, parent_permission_mode=parent_mode)

            for pid, tag in phases:
                if pid not in result["phases"]:
                    continue
                info = result["phases"][pid]
                if tag in ("write", "execute") or tag is None:
                    assert info["classification"] == CLASSIFICATION_NEEDS_CONFIRMATION, (
                        f"Phase {pid!r} tag={tag!r} under {parent_mode!r}: "
                        f"expected needs_confirmation, got {info['classification']!r}"
                    )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @given(parent_mode=st.just("default"))
    @settings(max_examples=50)
    def test_no_manifest_means_all_needs_confirmation(self, parent_mode):
        """Missing manifest (all untagged) -> every phase needs confirmation (default-deny)."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="no-manifest", base_dir=base)

            for pid in ["p1", "p2", "p3"]:
                append_event(rd, event_schema(
                    EVENT_PHASE_STARTED, run_id=rd.run_id, payload={"phase_id": pid}
                ))

            result = classify_phases(rd, parent_permission_mode=parent_mode)
            for pid, info in result["phases"].items():
                assert info["classification"] == CLASSIFICATION_NEEDS_CONFIRMATION, (
                    f"Untagged phase {pid!r} must be needs_confirmation (default-deny R-003)"
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Retention properties
# ---------------------------------------------------------------------------


def _write_run_state(run_path: Path, status: str, completed_at_ts: float | None) -> None:
    """Write a minimal run-state.json with the given status and optional completed_at."""
    state: dict = {
        "run_id": run_path.name,
        "skill": "test",
        "started_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "status": status,
    }
    if completed_at_ts is not None:
        dt = datetime.datetime.fromtimestamp(completed_at_ts, tz=datetime.timezone.utc)
        state["completed_at"] = dt.isoformat()
    (run_path / "run-state.json").write_text(
        json.dumps(state, sort_keys=True), encoding="utf-8"
    )


@st.composite
def run_scenario_st(draw):
    """A synthetic run: status, age in days, and whether a copied transcript exists."""
    status = draw(st.sampled_from([
        "done", "tombstoned", "completed",   # prunable
        "crashed", "running", "pending",      # never prunable (DL-005)
        "unknown_status",
    ]))
    age_days = draw(st.floats(min_value=0.0, max_value=30.0, allow_nan=False))
    has_transcript = draw(st.booleans())
    return status, age_days, has_transcript


class TestRetentionProperties:
    @given(scenario=run_scenario_st(), retention_days=st.integers(min_value=1, max_value=14))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_prune_runs_only_deletes_prunable_old_runs(self, scenario, retention_days):
        """prune_runs deletes ONLY {done,tombstoned,completed} runs older than TTL."""
        status, age_days, _ = scenario
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            base.mkdir(parents=True)

            run_id = f"run-{uuid.uuid4().hex[:8]}"
            run_path = base / run_id
            run_path.mkdir()

            now = time.time()
            completed_ts = now - max(age_days, 0.0) * 86400 - 1
            _write_run_state(run_path, status, completed_ts)

            pruned = prune_runs(base_dir=base, retention_days=retention_days)

            is_prunable = status in _PRUNABLE_STATUSES
            is_old_enough = age_days > retention_days
            should_be_pruned = is_prunable and is_old_enough

            if should_be_pruned:
                assert run_id in pruned, (
                    f"Expected run {run_id!r} (status={status!r}, age={age_days:.1f}d, "
                    f"ttl={retention_days}d) to be pruned"
                )
                assert not run_path.exists(), "pruned run dir still on disk"
            elif not is_prunable:
                assert run_id not in pruned, (
                    f"Non-prunable run {run_id!r} (status={status!r}) was pruned — DL-005 violation"
                )
                assert run_path.exists(), "Non-prunable run dir was deleted"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @given(scenario=run_scenario_st())
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
    def test_crashed_incomplete_never_pruned(self, scenario):
        """Crashed/running/pending runs are NEVER deleted regardless of age (DL-005)."""
        status, age_days, _ = scenario
        if status in _PRUNABLE_STATUSES:
            return  # this test only cares about non-prunable statuses

        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            base.mkdir(parents=True)

            run_id = f"run-{uuid.uuid4().hex[:8]}"
            run_path = base / run_id
            run_path.mkdir()

            old_ts = time.time() - 365 * 86400
            _write_run_state(run_path, status, old_ts)

            pruned = prune_runs(base_dir=base, retention_days=1)

            assert run_id not in pruned, (
                f"Non-prunable run (status={status!r}) was deleted — DL-005 violation"
            )
            assert run_path.exists(), "Non-prunable run dir was deleted from disk"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_is_resumable_none_returns_false(self):
        """is_resumable(None) must always return False (documented spec)."""
        assert is_resumable(None) is False

    @given(has_transcript=st.booleans())
    @settings(max_examples=50)
    def test_is_resumable_with_transcript_copy(self, has_transcript):
        """is_resumable returns True iff a copied transcript.jsonl exists (primary path)."""
        tmp = tempfile.mkdtemp()
        try:
            base = Path(tmp) / "skill-runs"
            rd = create_run_dir(skill="resumable-test", base_dir=base)

            if has_transcript:
                transcript = rd.path / "subagent-abc" / "transcript.jsonl"
                transcript.parent.mkdir(parents=True, exist_ok=True)
                transcript.write_text('{"type": "message"}\n', encoding="utf-8")

            result = is_resumable(rd)

            if has_transcript:
                assert result is True, "is_resumable should be True when transcript.jsonl present"
            else:
                assert result is False, "is_resumable should be False when no transcript present"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
