#!/usr/bin/env python3
"""Assert: after a real skill run, the substrate event log is correctly populated.

PURPOSE (Scenario S2):
    After the user installs PRODUCTION hooks and runs a ported skill (e.g. /refactor
    or any workflow.mjs skill), this script inspects the most-recent run directory
    in ~/.claude/skill-runs/ and asserts:

    1. A run directory exists (run-state.json present).
    2. events.jsonl has at least one correctly-typed event (all lines parse as JSON
       and carry a 'type' field).
    3. A fresh replay() of events.jsonl produces the same result as the stored
       projection.json (within 1 second float tolerance).
    4. For Workflow skills, projection.phases is non-empty — proving the bridge fired.

USAGE:
    python3 tests/live/assert/assert_events_populated.py [run_id]

    run_id (optional): the specific run_id to inspect. If omitted, the most
    recently started run in ~/.claude/skill-runs/ is used.

PREREQUISITES:
    - Production hooks must be installed in ~/.claude/settings.json
      (using the wiring in the repo's settings.json).
    - The repo must be synced to one of:
        ~/.claude/skills/scripts        (production install)
        <repo_root>/skills/scripts      (worktree / dev)
    - A Workflow skill must have been run in this session.

OUTPUTS:
    PASS/FAIL lines to stdout. Exits 0 always.

WHAT IT READS:
    ~/.claude/skill-runs/<run_id>/{run-state.json, events.jsonl, projection.json}

WHAT IT NEVER WRITES:
    Nothing. Read-only inspection.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Substrate import (same two-candidate pattern as other assert scripts)
# ---------------------------------------------------------------------------

_REPO_CANDIDATES: list[Path] = [
    Path(__file__).parent.parent.parent.parent / "skills" / "scripts",
    Path.home() / ".claude" / "skills" / "scripts",
]

_substrate_loaded = False
for _candidate in _REPO_CANDIDATES:
    if _candidate.exists() and (_candidate / "skills").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        try:
            from skills.lib.workflow.persistence.registry import list_runs, find_run  # type: ignore[import]
            from skills.lib.workflow.persistence.projection import replay  # type: ignore[import]
            _substrate_loaded = True
            break
        except ImportError:
            continue

if not _substrate_loaded:
    print("ERROR: cannot import substrate from any candidate path:")
    for c in _REPO_CANDIDATES:
        print(f"  {c}")
    print("Ensure the repo is synced to one of the locations above.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KNOWN_EVENT_TYPES: frozenset[str] = frozenset({
    "run_started",
    "run_completed",
    "phase_started",
    "phase_completed",
    "subagent_spawned",
    "subagent_completed",
    "task_created",
    "task_completed",
    "teammate_idle",
})


def _canonical(d: dict) -> str:
    """Normalized JSON for comparison (sorted keys, no whitespace)."""
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _projection_close_enough(stored: dict, replayed: dict) -> tuple[bool, str]:
    """Compare projections; allow float timestamp drift up to 1 second."""
    # Normalize floats: round all float values to 0 decimal places for comparison
    def _normalize(obj):
        if isinstance(obj, float):
            return round(obj)
        if isinstance(obj, dict):
            return {k: _normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_normalize(v) for v in obj]
        return obj

    ns = _canonical(_normalize(stored))
    nr = _canonical(_normalize(replayed))
    if ns == nr:
        return True, ""
    return False, f"stored != replayed (after float normalization)\nstored:   {ns[:300]}\nreplayed: {nr[:300]}"


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def _assert_run_dir(run_id: str) -> tuple[bool, str]:
    """Assert: the run directory exists with a readable run-state.json."""
    handle = find_run(run_id)
    if handle is None:
        return False, f"run directory not found for run_id={run_id!r} in skill-runs base"
    state_path = handle.run_state
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return True, f"run-state.json exists; status={state.get('status')!r}, skill={state.get('skill')!r}"
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"run-state.json unreadable: {exc}"


def _assert_events_typed(run_id: str) -> tuple[bool, str]:
    """Assert: events.jsonl has parseable events each with a 'type' field."""
    handle = find_run(run_id)
    if handle is None:
        return False, "run not found"
    events_path = handle.events_jsonl
    if not events_path.exists():
        return False, f"events.jsonl missing at {events_path}"
    lines = [l for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return False, "events.jsonl is empty — no events recorded"
    events: list[dict] = []
    parse_errors: list[str] = []
    for i, line in enumerate(lines, 1):
        try:
            ev = json.loads(line)
            events.append(ev)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {i}: {exc}")
    if parse_errors:
        return False, f"{len(parse_errors)} JSON parse error(s) in events.jsonl: {parse_errors[:3]}"
    missing_type = [ev for ev in events if "type" not in ev]
    if missing_type:
        return False, f"{len(missing_type)} event(s) missing 'type' field"
    types_seen = sorted({ev["type"] for ev in events})
    unknown = [t for t in types_seen if t not in _KNOWN_EVENT_TYPES]
    msg = (
        f"{len(events)} event(s) all parseable with 'type' field. "
        f"Types: {types_seen}"
    )
    if unknown:
        msg += f"  (unknown types — may be new: {unknown})"
    return True, msg


def _assert_projection_matches_replay(run_id: str) -> tuple[bool, str]:
    """Assert: projection.json matches a fresh replay of events.jsonl."""
    handle = find_run(run_id)
    if handle is None:
        return False, "run not found"
    proj_path = handle.projection
    if not proj_path.exists():
        return False, f"projection.json missing at {proj_path}"
    try:
        stored = json.loads(proj_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"projection.json unreadable: {exc}"
    try:
        run_dir = handle.as_run_dir()
        replayed = replay(run_dir)
    except Exception as exc:
        return False, f"replay() raised: {exc}"
    ok, diff = _projection_close_enough(stored, replayed)
    if ok:
        return True, "projection.json matches replay() output"
    return False, f"projection.json DIVERGES from replay: {diff}"


def _assert_phases_non_empty(run_id: str) -> tuple[bool, str]:
    """Assert: projection.phases is non-empty (proves bridge fired for Workflow skills)."""
    handle = find_run(run_id)
    if handle is None:
        return False, "run not found"
    proj_path = handle.projection
    if not proj_path.exists():
        return False, "projection.json missing"
    try:
        proj = json.loads(proj_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"projection.json unreadable: {exc}"
    phases = proj.get("phases") or {}
    if not phases:
        return False, (
            "projection.phases is empty — bridge did not fire OR this is not a Workflow skill. "
            "If you ran a non-Workflow skill, this is expected. "
            "If you ran /refactor or another workflow.mjs skill, the bridge did not fire."
        )
    phase_summary = {pid: info.get("status") for pid, info in phases.items() if isinstance(info, dict)}
    return True, f"projection.phases non-empty: {phase_summary}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    run_id_arg: str | None = sys.argv[1] if len(sys.argv) > 1 else None

    if run_id_arg:
        run_id = run_id_arg
        print(f"Inspecting specified run: {run_id}")
    else:
        runs = list_runs()
        if not runs:
            print("FAIL: no runs found in skill-runs base directory.")
            print("Run a skill with production hooks installed first (Scenario S2).")
            return
        # Most recent started_at
        latest = max(runs, key=lambda r: r.get("started_at") or "")
        run_id = latest["run_id"]
        print(f"No run_id specified — using most recent: {run_id} (started={latest.get('started_at')})")

    print("=" * 72)
    print(f"Asserting run: {run_id}")
    print("=" * 72)

    checks: list[tuple[str, tuple[bool, str]]] = [
        ("1. Run directory exists", _assert_run_dir(run_id)),
        ("2. events.jsonl parseable + typed", _assert_events_typed(run_id)),
        ("3. projection.json matches replay()", _assert_projection_matches_replay(run_id)),
        ("4. projection.phases non-empty (Workflow bridge)", _assert_phases_non_empty(run_id)),
    ]

    all_pass = True
    for label, (ok, msg) in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"\n  {status}  {label}")
        print(f"        {msg}")

    print("\n" + "=" * 72)
    if all_pass:
        print("RESULT: PASS — substrate is correctly populated after a live run.")
    else:
        fails = [label for label, (ok, _) in checks if not ok]
        print(f"RESULT: FAIL — {len(fails)} check(s) failed: {fails}")
    print("=" * 72)


if __name__ == "__main__":
    main()
