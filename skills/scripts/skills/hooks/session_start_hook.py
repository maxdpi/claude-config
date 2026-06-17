#!/usr/bin/env python3
"""SessionStart hook: surface crash-recovery offers and prune done runs.

Runs when Claude Code starts a new session (DL-002/DL-005).  Actions:
1. Prune done/tombstoned runs past the configured retention TTL.
2. Detect incomplete (crashed/running) runs and print a resume offer to
   stdout so the user sees it in their first session message.

Never reads or writes ~/.claude/teams or ~/.claude/tasks (DL-002).
Exit code must be 0; output on stdout is presented to the user by Claude Code.

Testability
-----------
``main()`` accepts an injected ``payload`` dict (unused by SessionStart, but
present for API symmetry with other hooks).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence.registry import list_runs
from skills.lib.workflow.persistence.retention import prune_runs
from skills.lib.workflow.persistence.team_mode import select_orchestration_mode
from skills.lib.workflow.persistence.workflow_bridge import bridge_session_workflows

_INCOMPLETE_STATUSES: frozenset[str] = frozenset({"running", "crashed"})


def _format_age(started_at: str | None) -> str:
    """Return a human-readable age string from an ISO timestamp."""
    if not started_at:
        return "unknown age"
    try:
        import datetime
        import time
        dt = datetime.datetime.fromisoformat(started_at)
        seconds = time.time() - dt.timestamp()
        if seconds < 120:
            return f"{int(seconds)}s ago"
        if seconds < 7200:
            return f"{int(seconds / 60)}m ago"
        return f"{int(seconds / 3600)}h ago"
    except (ValueError, TypeError, OSError):
        return "unknown age"


def main(payload: dict | None = None) -> int:
    """SessionStart hook entrypoint.

    Args:
        payload: Injected payload dict (unused by SessionStart; for API symmetry).

    Returns:
        Always 0.
    """
    # Surface the active orchestration mode first, before any early return.
    # SessionStart stdout IS added to the context Claude sees (hooks.md:513), so
    # this resolves the committed-vs-live env incoherence at a point a human and
    # the model can both observe it. printenv-equivalent: reads the live process
    # env, not settings.json's committed value (DL-T1-05).
    if select_orchestration_mode().mode == "agent_teams":
        print("[skill-runs] mode: agent_teams")
    else:
        print("[skill-runs] mode: workflow (subagent fallback)")

    # Step 0: bridge any Workflow run-states from previous sessions before checking
    # for incomplete runs. This feeds the resume offer with real phase data.
    session_id: str | None = None
    if payload:
        session_id = (
            payload.get("session_id")
            or payload.get("sessionId")
        )
    if session_id:
        try:
            bridge_session_workflows(session_id)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "session_start_hook: workflow bridge failed", exc_info=True
            )

    # Step 1: prune done/tombstoned runs past retention TTL.
    pruned = prune_runs()
    if pruned:
        print(
            f"[skill-runs] Pruned {len(pruned)} completed run(s) past retention TTL.",
            file=sys.stderr,
        )

    # Step 2: detect incomplete runs and surface a resume offer.
    runs = list_runs()
    incomplete = [r for r in runs if r.get("status") in _INCOMPLETE_STATUSES]
    if not incomplete:
        return 0

    lines = ["Resumable skill runs detected:"]
    for run in incomplete:
        run_id: str = run["run_id"]
        skill: str = run.get("skill") or "unknown"
        phase: str | None = run.get("active_phase")
        age: str = _format_age(run.get("started_at"))
        phase_str = f"  phase={phase}" if phase else ""
        lines.append(f"  {run_id[:8]}  {skill}{phase_str}  {age}")
    lines.append("Use /resume <id> to continue or /runs to list all.")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}
    sys.exit(main(payload))
