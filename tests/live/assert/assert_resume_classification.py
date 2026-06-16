#!/usr/bin/env python3
"""Assert: classify_phases on a real (crashed/interrupted) run + DL-021 override check.

PURPOSE (Scenario S3):
    After the user has started a multi-phase Workflow skill and interrupted it
    mid-run (exiting the session before it completed), this script calls
    resume.classify_phases on the resulting run and prints:

    1. The classification of each remaining phase (auto_replay vs needs_confirmation)
    2. Whether the DL-021 override fired (parent session runs defaultMode=auto,
       so in this environment ALL phases should be needs_confirmation)
    3. The warning string that /resume must surface to the user

    Expected behavior in this environment (defaultMode=auto → overriding):
        - permission_mode_overridden = True
        - ALL phases → needs_confirmation
        - Warning: "permissionMode enforcement is OVERRIDDEN..."

USAGE:
    python3 tests/live/assert/assert_resume_classification.py <run_id>

    run_id: the id of a crashed/interrupted run in ~/.claude/skill-runs/
            (use the first 8 chars shown by the session_start resume offer,
             or list all runs with `python3 -c "from skills.lib.workflow.persistence.registry import list_runs; import json; print(json.dumps(list_runs(), indent=2))"`)

PREREQUISITES:
    - A Workflow skill must have been started and interrupted (Scenario S3 step 2).
    - The run must exist in ~/.claude/skill-runs/ with status 'running' or 'crashed'.
    - The repo must be synced/available at the paths listed below.

OUTPUTS:
    PASS/FAIL lines to stdout. Exits 0 always.

WHAT IT READS:
    ~/.claude/skill-runs/<run_id>/{run-state.json, projection.json, manifest.json}
    ~/.claude/settings.json  (to detect parent permission mode)

WHAT IT NEVER WRITES:
    Nothing. Read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Substrate import
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
            from skills.lib.workflow.persistence.registry import find_run, list_runs  # type: ignore[import]
            from skills.lib.workflow.persistence.resume import (  # type: ignore[import]
                classify_phases,
                detect_parent_permission_mode,
                OVERRIDING_MODES,
                CLASSIFICATION_AUTO_REPLAY,
                CLASSIFICATION_NEEDS_CONFIRMATION,
            )
            _substrate_loaded = True
            break
        except ImportError:
            continue

if not _substrate_loaded:
    print("ERROR: cannot import substrate from any candidate path:")
    for c in _REPO_CANDIDATES:
        print(f"  {c}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 assert_resume_classification.py <run_id>")
        print()
        print("Available runs:")
        runs = list_runs()
        if not runs:
            print("  (none — no runs in skill-runs base)")
        for r in runs:
            print(f"  {r['run_id']}  status={r['status']}  skill={r.get('skill')}  started={r.get('started_at')}")
        return

    run_id: str = sys.argv[1]

    print("=" * 72)
    print(f"DL-021 CLASSIFICATION TEST: run_id={run_id}")
    print("=" * 72)

    handle = find_run(run_id)
    if handle is None:
        print(f"FAIL: run_id={run_id!r} not found in skill-runs base.")
        print("Use --list or run assert_events_populated.py to find valid run IDs.")
        return

    # Show run state
    try:
        state = json.loads(handle.run_state.read_text(encoding="utf-8"))
        print(f"\nRun state: status={state.get('status')!r}, skill={state.get('skill')!r}, started={state.get('started_at')!r}")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: cannot read run-state.json: {exc}")

    # Show projection phases (for context)
    try:
        proj = json.loads(handle.projection.read_text(encoding="utf-8"))
        phases = proj.get("phases") or {}
        if phases:
            print(f"\nProjection phases ({len(phases)} total):")
            for pid, info in phases.items():
                if isinstance(info, dict):
                    print(f"  {pid}: status={info.get('status')!r}")
        else:
            print("\nProjection phases: empty (no bridge events yet, or non-Workflow run)")
    except (OSError, json.JSONDecodeError):
        print("\nProjection: missing or unreadable")

    # Detect parent permission mode
    parent_mode = detect_parent_permission_mode()
    print(f"\nDetected parent_permission_mode: {parent_mode!r}")
    is_overriding = parent_mode in OVERRIDING_MODES
    if is_overriding:
        print(
            f"  -> {parent_mode!r} is in OVERRIDING_MODES {set(OVERRIDING_MODES)}"
            f"\n     DL-021 override is ACTIVE in this environment."
        )
    else:
        print(
            f"  -> {parent_mode!r} is NOT in OVERRIDING_MODES."
            f" Phase-trust gating will apply (read_only phases may auto-replay)."
        )

    # Run classify_phases
    print("\nRunning classify_phases()...")
    try:
        result = classify_phases(handle, parent_permission_mode=parent_mode)
    except Exception as exc:
        print(f"FAIL: classify_phases raised: {exc}")
        return

    phase_classifications = result.get("phases") or {}
    permission_mode_overridden = result.get("permission_mode_overridden", False)
    warning = result.get("warning")

    print(f"\nClassification result ({len(phase_classifications)} remaining phase(s)):")
    if not phase_classifications:
        print("  (no remaining phases — run is complete, or manifest+projection are empty)")

    auto_replay_phases: list[str] = []
    needs_confirmation_phases: list[str] = []
    for pid, info in sorted(phase_classifications.items()):
        classification = info.get("classification")
        tag = info.get("tag")
        print(f"  {pid}: classification={classification!r}, manifest_tag={tag!r}")
        if classification == CLASSIFICATION_AUTO_REPLAY:
            auto_replay_phases.append(pid)
        else:
            needs_confirmation_phases.append(pid)

    # DL-021 assertion
    print("\n--- DL-021 Override Check ---")
    if is_overriding:
        # In this environment (defaultMode=auto), ALL phases must be needs_confirmation
        if permission_mode_overridden and not auto_replay_phases:
            print("  PASS  DL-021: permission_mode_overridden=True, 0 auto_replay phases.")
            print(f"        All {len(needs_confirmation_phases)} phase(s) -> needs_confirmation. Correct.")
        elif not permission_mode_overridden:
            print(
                f"  FAIL  DL-021: parent mode is {parent_mode!r} (overriding) but"
                f" permission_mode_overridden=False."
                f" classify_phases did not set the override flag."
            )
        elif auto_replay_phases:
            print(
                f"  FAIL  DL-021: parent mode is {parent_mode!r} (overriding) but"
                f" {len(auto_replay_phases)} phase(s) were classified as auto_replay:"
                f" {auto_replay_phases}"
            )
    else:
        print(f"  INFO  Parent mode {parent_mode!r} is not overriding — DL-021 path not active.")
        print(f"        auto_replay phases: {auto_replay_phases}")
        print(f"        needs_confirmation phases: {needs_confirmation_phases}")

    # Warning string check
    print("\n--- DL-021 Warning String ---")
    if permission_mode_overridden:
        if warning:
            print("  PASS  warning string is present (must be shown by /resume):")
            print(f"        {warning}")
        else:
            print("  FAIL  permission_mode_overridden=True but warning is None/empty.")
            print("        /resume cannot warn the user about the override.")
    else:
        print(f"  INFO  No override active; warning={warning!r}")

    # Summary
    print("\n" + "=" * 72)
    fail_conditions = []
    if is_overriding and not permission_mode_overridden:
        fail_conditions.append("DL-021 flag not set")
    if is_overriding and auto_replay_phases:
        fail_conditions.append(f"auto_replay phases present despite override: {auto_replay_phases}")
    if is_overriding and permission_mode_overridden and not warning:
        fail_conditions.append("override active but warning string is None")

    if fail_conditions:
        print(f"RESULT: FAIL — {len(fail_conditions)} issue(s):")
        for fc in fail_conditions:
            print(f"  {fc}")
    else:
        print("RESULT: PASS — classification and DL-021 override behave correctly.")
    print("=" * 72)


if __name__ == "__main__":
    main()
