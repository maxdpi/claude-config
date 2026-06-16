#!/usr/bin/env python3
"""M-000 / CI-M-000-003 -- runtime-dir ephemerality probe (assumption A3).

A3 (as originally stated): ``~/.claude/teams`` and ``~/.claude/tasks`` are deleted
at session end, so they cannot be the durable store (drives DL-002, R-002).

What this probe does
--------------------
1. Records the current state of ``~/.claude/teams`` and ``~/.claude/tasks``.
2. Writes a uniquely-named marker file into each dir that exists.
3. Emits a machine-readable result and instructions: a human (or a follow-up
   session-end hook) ENDS the session, then re-runs ``--check`` to assert the
   markers were reaped.

Because a single live session cannot drive its own ``SessionEnd`` synchronously,
the probe is two-phase (``--plant`` then ``--check``). The result also captures the
ALREADY-OBSERVED state, which on 2026-06-16 in this environment was:

* ``CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`` UNSET -> Agent Teams disabled ->
  ``~/.claude/teams`` does **not exist** at all (A3's teams half is unobservable
  here: there is nothing to reap).
* ``~/.claude/tasks`` **persists** across many past sessions (subdirs dated days
  before the probe, each holding ``.lock`` + ``.highwatermark``). It is therefore
  NOT reaped at session end in this configuration.

=> A3's *literal* claim ("reaped at session end") is only partially supported.
   The load-bearing conclusion C-003 ("the durable store MUST live outside these
   dirs") STILL HOLDS, but for a stronger reason than reaping: these dirs are
   runtime-OWNED and clobbered-while-live (C-007), so authoring state into them is
   unsafe regardless of whether they are eventually reaped. DL-002/DL-005 should be
   re-read with "runtime-owned / clobbered-while-live" as the primary justification
   and "reaped at session end" as a secondary, environment-dependent observation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CLAUDE = Path.home() / ".claude"
TEAMS = CLAUDE / "teams"
TASKS = CLAUDE / "tasks"
MARKER_NAME = "m000_ephemerality_marker.txt"


def _snapshot(p: Path) -> dict:
    exists = p.exists()
    children = sorted(c.name for c in p.iterdir()) if exists and p.is_dir() else []
    return {
        "path": str(p).replace(str(Path.home()), "~"),
        "exists": exists,
        "child_count": len(children),
        "children_sample": children[:10],
        "marker_present": (p / MARKER_NAME).exists() if exists else False,
    }


def probe_teams_dir_ephemerality(mode: str = "observe") -> dict:
    """Probe ephemerality of the runtime-owned ~/.claude/{teams,tasks} dirs.

    mode="observe": just record current state (no writes).
    mode="plant":   record state, then write a marker into each existing dir.
    mode="check":   record state, report whether a previously-planted marker survived.
    """
    result: dict = {
        "probe": "teams_dir_ephemerality",
        "assumption": "A3",
        "mode": mode,
        "agent_teams_env_gate": os.environ.get(
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "<unset>"
        ),
        "teams": _snapshot(TEAMS),
        "tasks": _snapshot(TASKS),
    }

    if mode == "plant":
        planted = []
        for p in (TEAMS, TASKS):
            if p.exists() and p.is_dir():
                (p / MARKER_NAME).write_text(
                    "m000 ephemerality probe marker; safe to delete\n", encoding="utf-8"
                )
                planted.append(str(p).replace(str(Path.home()), "~"))
        result["planted_markers_in"] = planted
        result["next_step"] = (
            "End the Claude Code session, then run `teams_dir_probe.py --check`. "
            "If the markers (and dirs) are gone -> reaped (A3 teams/tasks half holds). "
            "If they survive -> NOT reaped (revisit DL-002/DL-005)."
        )

    if mode == "check":
        result["teams_marker_survived"] = result["teams"]["marker_present"]
        result["tasks_marker_survived"] = result["tasks"]["marker_present"]
        result["reaped"] = not (
            result["teams"]["marker_present"] or result["tasks"]["marker_present"]
        )

    # The standing empirical conclusion, independent of the plant/check cycle.
    teams_exists = result["teams"]["exists"]
    tasks_persists = result["tasks"]["exists"] and result["tasks"]["child_count"] > 0
    result["observed_conclusion"] = {
        "teams_dir_exists": teams_exists,
        "tasks_dir_persists_across_sessions": tasks_persists,
        "a3_literal_reaping_supported": False if tasks_persists else None,
        "c003_durable_store_outside_these_dirs_still_required": True,
        "primary_reason": (
            "runtime-owned and clobbered-while-live (C-007) -- safer justification "
            "than 'reaped at session end', which is environment-dependent and was "
            "NOT observed for ~/.claude/tasks here."
        ),
        "action": "revisit DL-002/DL-005 wording" if tasks_persists else "A3 holds as stated",
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="A3 runtime-dir ephemerality probe")
    ap.add_argument(
        "--mode", choices=["observe", "plant", "check"], default="observe"
    )
    ap.add_argument("--plant", action="store_const", const="plant", dest="mode")
    ap.add_argument("--check", action="store_const", const="check", dest="mode")
    args = ap.parse_args()
    result = probe_teams_dir_ephemerality(args.mode)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
