#!/usr/bin/env python3
"""Stop/SessionEnd hook: flush run state before runtime dirs are reaped.

Called when the Claude Code session is ending (DL-002).  For every run
currently in ``running`` status, replays the append-only ``events.jsonl``
to compute the latest projection, then merges projection fields into
``run-state.json`` so the durable store reflects the last known state
before the session (and its runtime dirs) disappear.

Idempotent
----------
Calling this multiple times is safe because it reads from the append-only
``events.jsonl`` and writes ``run-state.json`` atomically.  If the session
end hook fires multiple times (e.g., both Stop and SessionEnd are wired),
the last write wins without corruption (atomic overwrite).

Never reads or writes ~/.claude/teams or ~/.claude/tasks (DL-002).
Exit code is always 0 (non-fatal).

Testability
-----------
``main()`` accepts an injected ``payload`` dict (unused by SessionEnd; for
API symmetry).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence.registry import list_runs, find_run
from skills.lib.workflow.persistence.projection import replay
from skills.lib.workflow.persistence.atomic import write_atomic
from skills.lib.workflow.persistence.workflow_bridge import bridge_session_workflows
from skills.lib.workflow.persistence.teams_bridge import mark_team_runs_completed

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

_RUNNING_STATUSES: frozenset[str] = frozenset({"running"})


def main(payload: dict | None = None) -> int:
    """SessionEnd hook entrypoint.

    Args:
        payload: Injected payload dict (unused by SessionEnd; for API symmetry).

    Returns:
        Always 0 (non-fatal hook).
    """
    # Bridge Workflow run-states for the ending session into the durable substrate
    # before the runtime directories are reaped.
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
            log.warning("session_end_hook: workflow bridge failed", exc_info=True)
        try:
            mark_team_runs_completed(session_id)
        except Exception:
            log.warning("session_end_hook: teams bridge mark_completed failed", exc_info=True)

    for run_summary in list_runs():
        if run_summary.get("status") not in _RUNNING_STATUSES:
            continue

        run_id: str = run_summary["run_id"]
        handle = find_run(run_id)
        if handle is None:
            continue

        try:
            run_dir = handle.as_run_dir()
            projection = replay(run_dir)

            state_path = handle.run_state
            existing: dict = {}
            if state_path.exists():
                try:
                    existing = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = {}

            # Merge: projection fields take precedence over stale run-state
            # fields, but we keep run-state fields that are not in the projection
            # (e.g. skill config, session_id set at run creation).
            merged: dict = {
                **existing,
                **{k: v for k, v in projection.items() if v is not None},
            }
            write_atomic(state_path, merged)
        except Exception:
            log.warning(
                "session_end_hook: flush failed for run_id=%r",
                run_id, exc_info=True,
            )

    return 0


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}
    sys.exit(main(payload))
