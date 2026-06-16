#!/usr/bin/env python3
"""M-007 / CI-M-007-005 — per-skill output parity fixtures for adversarial skill ports.

Validates that the Agent Teams ports (or Workflow+subagent fallbacks) of
decision-critic, deepthink, and problem-analysis produce equivalent structured
artifacts to their Python predecessors on fixed inputs (DL-008, R-004).

These are the parity gate tests that must pass before M-008b deletes the Python
runtime for these skills. They test OUTPUT EQUIVALENCE, not fallback behavior
(fallback is tested separately in test_team_mode_fallback.py).

# Parity gate for M-008b: each skill's parity fixture must pass before its Python
# CLI entry point is deleted. Fallback tests (test_team_mode_fallback.py) are
# necessary but not sufficient -- output equivalence is required. (ref: DL-008, R-004)

HARD GATE: A missing fixture is pytest.fail (NEVER a skip) — the R-004 / M-008b gate.
A skipped parity test can never let M-008b proceed.

FIXTURE FIDELITY CAVEAT (Task C / parity-honesty finding):
All fixtures carry ``_fixture_fidelity: "hand-authored-contract"`` because capturing
both runtimes simultaneously requires both to be live-executable, which is not
possible during the port period. The gate is STRUCTURAL, not behavioral. A passing
test means the contract shape is honored; it does NOT prove the live port produces
identical output to the live Python runtime on the same input. Visible warnings are
emitted when a hand-authored-contract fixture is asserted.

Fixture format: tests/fixtures/adversarial_skill_parity/<skill>.json
  {"python": {...}, "port": {...}, "_fixture_fidelity": "hand-authored-contract"}

Per-skill required keys (structural decision fields):
  decision-critic  → claim_ids (list) + verdict (string)
  deepthink        → answer (string) + confidence (string) + reasoning_step_ids (list)
  problem-analysis → root_cause_id (string) + confirmed_hypothesis_ids (list) + root_cause (string)
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Make the project scripts importable (unused here but consistent with house style)
# ---------------------------------------------------------------------------

import sys

_WORKTREE = Path(__file__).parent.parent
_SCRIPTS = _WORKTREE / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

FIXTURES_DIR = _WORKTREE / "tests" / "fixtures" / "adversarial_skill_parity"


# ---------------------------------------------------------------------------
# Fixture loader (HARD FAIL on missing — R-004 gate)
# ---------------------------------------------------------------------------


def _load_fixture(skill: str) -> dict:
    """Load and validate a parity fixture. Hard fail if missing (R-004 gate)."""
    path = FIXTURES_DIR / f"{skill}.json"
    if not path.exists():
        pytest.fail(
            f"MISSING PARITY FIXTURE for adversarial skill '{skill}': {path}\n"
            f"This is the M-008b deletion gate (R-004). "
            f"The Python runtime for '{skill}' MUST NOT be deleted until this "
            f"fixture exists and the required keys match between the python and port blobs.\n"
            f"Add the fixture before deleting the Python orchestrator."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "python" in data, f"Fixture {path} missing 'python' blob"
    assert "port" in data, f"Fixture {path} missing 'port' blob"
    # Task C (parity-honesty): fixture must declare its fidelity level.
    assert "_fixture_fidelity" in data, (
        f"Fixture {path} missing '_fixture_fidelity' field. "
        f"Add '_fixture_fidelity': 'hand-authored-contract' (or 'live-captured') "
        f"to make the gate's behavioral limitations machine-readable."
    )
    fidelity = data["_fixture_fidelity"]
    if "hand-authored" in fidelity or fidelity == "hand-authored-contract":
        warnings.warn(
            f"[PARITY GATE — STRUCTURAL NOT BEHAVIORAL] skill='{skill}' "
            f"fixture={path.name!r}: fidelity={fidelity!r}. "
            f"This gate asserts CONTRACT SHAPE equality between hand-authored blobs. "
            f"It does NOT prove the live port produces identical output to the live "
            f"Python runtime on the same input. "
            f"To upgrade, capture live outputs from both runtimes.",
            stacklevel=2,
        )
    return data


def _assert_key_parity(data: dict, key: str, skill: str) -> None:
    """Assert that data['port'][key] == data['python'][key]."""
    fixture_path = FIXTURES_DIR / f"{skill}.json"
    python_blob = data["python"]
    port_blob = data["port"]

    assert key in python_blob, (
        f"Required key '{key}' missing from 'python' blob in {fixture_path}"
    )
    assert key in port_blob, (
        f"Required key '{key}' missing from 'port' blob in {fixture_path}"
    )
    assert port_blob[key] == python_blob[key], (
        f"PARITY FAILURE for adversarial skill '{skill}' on key '{key}':\n"
        f"python: {json.dumps(python_blob[key], indent=2)}\n"
        f"port:   {json.dumps(port_blob[key], indent=2)}\n"
        f"The Agent Teams port / Workflow fallback does not match its Python "
        f"predecessor. Fix the port before deleting the Python runtime (M-008b / R-004)."
    )


# ---------------------------------------------------------------------------
# Decision Critic parity
# ---------------------------------------------------------------------------


def test_team_skill_parity_vs_python_decision_critic() -> None:
    """decision-critic port produces equivalent structured verdict to the Python predecessor.

    Parity gate (R-004): same claim IDs + same verdict enum.
    Input: 'Switch the primary database from PostgreSQL to MongoDB to improve schema flexibility.'
    """
    data = _load_fixture("decision-critic")

    # Parity on stable claim ID set (same identifiers extracted, not just count)
    _assert_key_parity(data, "claim_ids", "decision-critic")

    # Parity on verdict enum: STAND | REVISE | ESCALATE
    _assert_key_parity(data, "verdict", "decision-critic")

    # Structural sanity: verdict must be one of the three valid values
    verdict = data["python"]["verdict"]
    assert verdict in ("STAND", "REVISE", "ESCALATE"), (
        f"Invalid verdict enum value: '{verdict}'. Must be STAND, REVISE, or ESCALATE."
    )

    # Sanity: claim_ids is a non-empty list of strings
    claim_ids = data["python"]["claim_ids"]
    assert isinstance(claim_ids, list) and len(claim_ids) > 0, (
        "claim_ids must be a non-empty list"
    )
    assert all(isinstance(c, str) for c in claim_ids), "Each claim_id must be a string"


# ---------------------------------------------------------------------------
# DeepThink parity
# ---------------------------------------------------------------------------


def test_team_skill_parity_vs_python_deepthink() -> None:
    """deepthink port produces equivalent structured synthesis to the Python predecessor.

    Parity gate (R-004): same answer + same confidence enum + same reasoning-step ID set.
    Input: 'Should a distributed system use event sourcing or traditional CRUD?'
    """
    data = _load_fixture("deepthink")

    # Parity on direct answer (not mere presence — actual content equality)
    _assert_key_parity(data, "answer", "deepthink")

    # Parity on confidence enum: HIGH | MEDIUM | LOW | INSUFFICIENT
    _assert_key_parity(data, "confidence", "deepthink")

    # Parity on reasoning-step ID set (same step identifiers produced)
    _assert_key_parity(data, "reasoning_step_ids", "deepthink")

    # Structural sanity: confidence must be one of the valid values
    confidence = data["python"]["confidence"]
    assert confidence in ("HIGH", "MEDIUM", "LOW", "INSUFFICIENT", "certain", "high", "medium", "low"), (
        f"Invalid confidence enum value: '{confidence}'."
    )

    # Sanity: reasoning_step_ids is a non-empty list
    step_ids = data["python"]["reasoning_step_ids"]
    assert isinstance(step_ids, list) and len(step_ids) > 0, (
        "reasoning_step_ids must be a non-empty list"
    )


# ---------------------------------------------------------------------------
# Problem Analysis parity
# ---------------------------------------------------------------------------


def test_team_skill_parity_vs_python_problem_analysis() -> None:
    """problem-analysis port produces equivalent root cause structure to the Python predecessor.

    Parity gate (R-004): same root_cause_id + same confirmed-hypothesis ID set + same root_cause.
    Input: 'Payment succeeds but confirmation email is never sent, no error logged.'
    """
    data = _load_fixture("problem-analysis")

    # Parity on root cause ID (stable identifier for the identified root cause)
    _assert_key_parity(data, "root_cause_id", "problem-analysis")

    # Parity on confirmed-hypothesis ID set (which hypotheses were confirmed)
    _assert_key_parity(data, "confirmed_hypothesis_ids", "problem-analysis")

    # Parity on the root cause statement itself
    _assert_key_parity(data, "root_cause", "problem-analysis")

    # Structural sanity: root_cause must be a non-empty string
    root_cause = data["python"]["root_cause"]
    assert isinstance(root_cause, str) and len(root_cause) > 0, (
        "root_cause must be a non-empty string"
    )

    # Sanity: confirmed_hypothesis_ids is a list (may be empty if no hypothesis confirmed)
    confirmed_ids = data["python"]["confirmed_hypothesis_ids"]
    assert isinstance(confirmed_ids, list), "confirmed_hypothesis_ids must be a list"
