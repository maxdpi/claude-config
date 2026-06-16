#!/usr/bin/env python3
"""SubagentStart hook: SYMMETRIC mirror-out trigger with SubagentStop.

Fires AFTER a subagent has already begun (matcher = agent type).  Its job is
correlation + audit — it is NOT a substitute for the parent pre-creating
task.json before spawn (DL-004).

Responsibilities
-----------------
1. Resolve the run (CLAUDE_SKILL_RUN_ID -> registry scan -> quarantine).
2. Materialize a task.json for the subagent dir if one does not exist yet
   (BEST-EFFORT LATE audit; the parent should have pre-created it — this is
   a safety net, not the primary path).
3. Emit EVENT_SUBAGENT_SPAWNED carrying native_agent_id / native_session_id /
   parent_agent_id / depth correlation so the durable log ties this run to
   the native transcript (DL-016/DL-022).
4. Quarantine (never append) if native_agent_id cannot be extracted (DL-022).
5. Exit code always 0 (non-fatal, DL-019).

Symmetry
--------
SubagentStart (this hook) emits EVENT_SUBAGENT_SPAWNED.
SubagentStop  (run_event_hook) emits EVENT_SUBAGENT_COMPLETED + copies transcript.
Together they bracket the native subagent lifecycle in the durable event log.

Testability
-----------
``main()`` accepts an injected ``payload`` dict (for tests).  When run as
``__main__``, it parses from stdin (CC hook convention).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence.hook_adapter import (
    QUARANTINE,
    normalize_hook_event,
    _PAYLOAD_AGENT_ID,
    _PAYLOAD_SESSION_ID,
    _PAYLOAD_PARENT_AGENT_ID,
    _PAYLOAD_DEPTH,
)
from skills.lib.workflow.persistence.eventlog import append_event
from skills.lib.workflow.persistence.registry import list_runs, find_run
from skills.lib.workflow.persistence.rundir import _resolve_base_dir
from skills.lib.workflow.persistence.atomic import write_atomic

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

_QUARANTINE_PATH: Path = _resolve_base_dir().parent / "skill-run-quarantine.jsonl"


# ---------------------------------------------------------------------------
# Correlation helpers (same order as run_event_hook — DL-002)
# ---------------------------------------------------------------------------


def _resolve_run_id(hook_payload: dict) -> str | None:
    """Resolve the run_id via CLAUDE_SKILL_RUN_ID or registry scan."""
    env_run_id = os.environ.get("CLAUDE_SKILL_RUN_ID", "").strip()
    if env_run_id:
        return env_run_id

    session_id: str | None = (
        hook_payload.get(_PAYLOAD_SESSION_ID)
        or hook_payload.get("session_id")
    )
    native_agent_id: str | None = hook_payload.get(_PAYLOAD_AGENT_ID) or None

    for run_summary in list_runs():
        handle = find_run(run_summary["run_id"])
        if handle is None:
            continue
        try:
            state = json.loads(handle.run_state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if session_id and state.get("session_id") == session_id:
            return run_summary["run_id"]
        # Also check if any subagent task.json references this native_agent_id.
        if native_agent_id:
            for task_file in handle.path.rglob("task.json"):
                try:
                    task_data = json.loads(task_file.read_text(encoding="utf-8"))
                    if task_data.get("native_agent_id") == native_agent_id:
                        return run_summary["run_id"]
                except (OSError, json.JSONDecodeError):
                    continue

    return None


def _write_quarantine(hook_payload: dict, reason: str = "") -> None:
    """Append unattributed event to quarantine log (never guess a run)."""
    _QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "ts": time.time(),
        "reason": reason,
        "payload": hook_payload,
    }
    with open(_QUARANTINE_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Late task.json materialization (best-effort audit)
# ---------------------------------------------------------------------------


def _maybe_materialize_task_json(
    run_dir_path: Path,
    native_agent_id: str,
    native_session_id: str | None,
    parent_agent_id: str | None,
    depth: int,
    run_id: str,
) -> None:
    """Write task.json for this subagent if one does not already exist.

    This is BEST-EFFORT LATE correlation — the parent should have called
    ``create_subagent_dir`` before spawning.  If it did, we skip.  If it
    did not, we create a minimal task.json so the subagent dir can be
    found by resume and inspection tooling (DL-004/CI-M-003-005).
    """
    # Use the native_agent_id as the agent dir name for this late-materialized dir.
    agent_dir = run_dir_path / f"subagent-{native_agent_id}"

    # If a task.json already exists for this native_agent_id anywhere in the
    # run tree, skip — the parent pre-created it correctly.
    for existing_task in run_dir_path.rglob("task.json"):
        try:
            data = json.loads(existing_task.read_text(encoding="utf-8"))
            if data.get("native_agent_id") == native_agent_id:
                return  # already present
        except (OSError, json.JSONDecodeError):
            continue

    agent_dir.mkdir(parents=True, exist_ok=True)
    task_doc: dict = {
        "agent_id": native_agent_id,
        "native_agent_id": native_agent_id,
        "native_session_id": native_session_id,
        "run_id": run_id,
        "run_dir": str(run_dir_path),
        "parent_agent_id": parent_agent_id,
        "depth": depth,
        "created_at": _now_iso(),
        "task": {"note": "late-materialized by SubagentStart hook (best-effort audit)"},
    }
    write_atomic(agent_dir / "task.json", task_doc)
    write_atomic(agent_dir / "state.json", {
        "native_agent_id": native_agent_id,
        "status": "spawned",
        "created_at": time.time(),
    })


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main(payload: dict | None = None) -> int:
    """SubagentStart hook entrypoint.

    Args:
        payload: Injected payload dict for tests.  When None, reads from stdin.

    Returns:
        Always 0 (non-fatal hook, DL-019).
    """
    if payload is None:
        try:
            payload = json.loads(sys.stdin.read())
        except (json.JSONDecodeError, OSError):
            payload = {}

    # Ensure hook_event_name is set so normalize_hook_event dispatches correctly.
    if "hook_event_name" not in payload and "hookEventName" not in payload:
        payload = {**payload, "hook_event_name": "SubagentStart"}

    native_agent_id: str | None = payload.get(_PAYLOAD_AGENT_ID) or None

    if not native_agent_id:
        # DL-022: quarantine before even resolving the run.
        log.warning(
            "subagent_start_hook: payload has no %r field — QUARANTINED (DL-022).  "
            "This is a null-correlated spawn; it will NOT be appended to any run.",
            _PAYLOAD_AGENT_ID,
        )
        _write_quarantine(payload, reason="no_native_agent_id_subagent_start")
        return 0

    run_id = _resolve_run_id(payload)
    if not run_id:
        log.warning(
            "subagent_start_hook: no run resolved for native_agent_id=%r — quarantining",
            native_agent_id,
        )
        _write_quarantine(payload, reason="no_run_resolved")
        return 0

    handle = find_run(run_id)
    if handle is None:
        log.warning(
            "subagent_start_hook: resolved run_id=%r but directory not found",
            run_id,
        )
        return 0

    # Normalize produces EVENT_SUBAGENT_SPAWNED; returns QUARANTINE if no agent_id.
    event = normalize_hook_event(payload, run_id)
    if event is QUARANTINE or event is None:
        # normalize_hook_event already logged; just quarantine.
        _write_quarantine(payload, reason="normalize_returned_quarantine")
        return 0

    run_dir = handle.as_run_dir()

    # Best-effort late task.json materialization (not a substitute for pre-spawn).
    native_session_id: str | None = payload.get(_PAYLOAD_SESSION_ID) or None
    parent_agent_id: str | None = payload.get(_PAYLOAD_PARENT_AGENT_ID) or None
    depth: int = int(payload.get(_PAYLOAD_DEPTH) or 0)
    _maybe_materialize_task_json(
        run_dir_path=handle.path,
        native_agent_id=native_agent_id,
        native_session_id=native_session_id,
        parent_agent_id=parent_agent_id,
        depth=depth,
        run_id=run_id,
    )

    append_event(run_dir, event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
