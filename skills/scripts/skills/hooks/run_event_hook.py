#!/usr/bin/env python3
"""Hook entrypoint for Task/Teammate/SubagentStop Claude Code hooks.

Invoked by the CC hook system when TaskCreated, TaskCompleted, TeammateIdle,
or SubagentStop events fire.  Resolves the target run, normalizes the payload,
and appends the event to that run's events.jsonl (DL-002/DL-019).

Correlation order (DL-002/DL-012)
----------------------------------
(a) ``CLAUDE_SKILL_RUN_ID`` env var exported at run creation — fast path.
(b) Fallback: scan registry (run-state.json files) for session_id / task_id match.
(c) Unmatched: write to quarantine log and exit non-fatally.

Never writes inside ~/.claude/teams or ~/.claude/tasks (DL-002).
Exit code is always 0 so a hook failure never breaks the running skill.

SubagentStop copy-on-stop (DL-016)
-----------------------------------
When the SubagentStop payload carries ``transcript_path``, the native
transcript is copied atomically (tmp + os.rename) to ``transcript.jsonl``
in the subagent's run dir.  When absent, the path is DERIVED from the
``sessionId`` + ``agentId`` fields via the A4 probe helper; if still
unresolved a WARNING is logged (not a fatal error).

Testability
-----------
``main()`` accepts an injected ``payload`` dict (for tests).  When run as
``__main__``, it parses the payload from stdin (CC hook convention).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
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
    _PAYLOAD_AGENT_TRANSCRIPT_PATH,
)
from skills.lib.workflow.persistence.eventlog import append_event
from skills.lib.workflow.persistence.registry import list_runs, find_run
from skills.lib.workflow.persistence.rundir import _resolve_base_dir
from skills.lib.workflow.persistence.probe.subagent_transcript_probe import (
    resolve_transcript_path,
)
from skills.lib.workflow.persistence.teams_bridge import (
    record_team_event,
    _TEAM_HOOK_TYPES,
    extract_team_name,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

_QUARANTINE_PATH: Path = _resolve_base_dir().parent / "skill-run-quarantine.jsonl"


# ---------------------------------------------------------------------------
# Correlation helpers
# ---------------------------------------------------------------------------


def _resolve_run_id(hook_payload: dict) -> str | None:
    """Resolve the run_id for this hook invocation.

    Correlation order (DL-002):
    (a) CLAUDE_SKILL_RUN_ID env var — O(1), preferred.
    (b) Registry scan for session_id / task_id match — O(n runs).
    Returns None if neither resolves to a known run.
    """
    env_run_id = os.environ.get("CLAUDE_SKILL_RUN_ID", "").strip()
    if env_run_id:
        return env_run_id

    session_id: str | None = (
        hook_payload.get(_PAYLOAD_SESSION_ID)
        or hook_payload.get("session_id")
    )
    task_id: str | None = hook_payload.get("task_id")

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
        if task_id and state.get("task_id") == task_id:
            return run_summary["run_id"]

    return None


def _write_quarantine(hook_payload: dict, reason: str = "") -> None:
    """Append an unattributed event to the quarantine log.

    Never guesses a run_id: attributing an event to the wrong run would
    corrupt that run's projection (DL-002/R-002).
    """
    _QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "ts": time.time(),
        "reason": reason,
        "payload": hook_payload,
    }
    with open(_QUARANTINE_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Copy-on-stop (DL-016)
# ---------------------------------------------------------------------------


def _copy_native_transcript(
    hook_payload: dict,
    run_dir_path: Path,
) -> None:
    """Copy the native transcript to transcript.jsonl atomically.

    PRIMARY path: ``agent_transcript_path`` field in the SubagentStop payload --
    the SUBAGENT's own transcript (DL-016). NOTE: the plain ``transcript_path``
    field is the PARENT session transcript and must NOT be copied (confirmed via
    the S1 live-capture probe, R-008).
    DERIVED path: resolved from session_id + agent_id via the A4 probe helper.
    If neither resolves, a WARNING is logged but the hook exits non-fatally.

    The copy is atomic (tmp + os.rename) so concurrent readers see either
    the old complete file or the new complete file, never a partial copy.
    """
    native_agent_id: str | None = hook_payload.get(_PAYLOAD_AGENT_ID) or None
    native_session_id: str | None = hook_payload.get(_PAYLOAD_SESSION_ID) or None
    # Subagent's own transcript (NOT the parent session transcript).
    transcript_path_raw: str | None = hook_payload.get(_PAYLOAD_AGENT_TRANSCRIPT_PATH)

    src: Path | None = None

    if transcript_path_raw:
        candidate = Path(transcript_path_raw).expanduser()
        if candidate.exists():
            src = candidate
        else:
            log.warning(
                "run_event_hook: SubagentStop agent_transcript_path %r does not exist; "
                "will try deriving from session_id + agent_id",
                transcript_path_raw,
            )

    if src is None and native_session_id and native_agent_id:
        src = resolve_transcript_path(native_session_id, native_agent_id)
        if src is None:
            log.warning(
                "run_event_hook: copy-on-stop: could not resolve native transcript "
                "for session_id=%r agent_id=%r (DL-016).  "
                "Transcript NOT copied; resume age-guard fallback (DL-020) applies.",
                native_session_id, native_agent_id,
            )
            return

    if src is None:
        log.warning(
            "run_event_hook: copy-on-stop: no transcript_path in payload and "
            "session_id/agent_id unavailable -- transcript NOT copied.",
        )
        return

    # Determine destination: the subagent dir under the run dir.
    # We place transcript.jsonl directly in run_dir_path when we cannot
    # identify the specific subagent subdirectory.
    dest_dir: Path = run_dir_path
    if native_agent_id:
        # Look for a matching task.json in any subdir to find the right subagent dir.
        for task_file in run_dir_path.rglob("task.json"):
            try:
                task_data = json.loads(task_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if task_data.get("native_agent_id") == native_agent_id:
                dest_dir = task_file.parent
                break

    dest = dest_dir / "transcript.jsonl"

    # Atomic copy: write to a temp file in the same dir, then rename.
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dest_dir, prefix=".tmp-transcript-")
        try:
            with open(fd, "wb") as out_fh, open(src, "rb") as in_fh:
                shutil.copyfileobj(in_fh, out_fh)
                out_fh.flush()
                os.fsync(out_fh.fileno())
        except Exception:
            # fd is already closed by the context manager if the with block entered.
            # If the open() itself raised (before the with block), fd is still open;
            # close it before attempting cleanup.
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.rename(tmp_path, dest)
        tmp_path = None  # Rename succeeded — temp path no longer needs cleanup
    except Exception:
        log.warning(
            "run_event_hook: copy-on-stop: failed to copy %s -> %s",
            src, dest, exc_info=True,
        )
    finally:
        # Unlink the temp file if the rename did not consume it (leaked on error).
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main(payload: dict | None = None) -> int:
    """Hook entrypoint.

    Args:
        payload: Injected payload dict for tests.  When None, reads from stdin.

    Returns:
        Always 0 (non-fatal hook).
    """
    if payload is None:
        try:
            payload = json.loads(sys.stdin.read())
        except (json.JSONDecodeError, OSError):
            payload = {}

    hook_type: str = (
        payload.get("hook_event_name")
        or payload.get("hookEventName", "")
    )

    run_id = _resolve_run_id(payload)
    if not run_id:
        # Before quarantining, check if this is an Agent Teams event that can
        # be captured via the teams_bridge live hook stream (M-003 extension).
        # Criteria: hook type is a known team event type OR the payload carries
        # a resolvable team_name / session_id that teams_bridge can derive from.
        is_team_hook = hook_type in _TEAM_HOOK_TYPES or bool(extract_team_name(payload))
        if is_team_hook:
            team_run_id = record_team_event(payload)
            if team_run_id:
                # Event captured — do not quarantine.
                return 0
        log.warning(
            "run_event_hook: no run resolved for hook_type=%r — quarantining",
            hook_type,
        )
        _write_quarantine(payload, reason="no_run_resolved")
        return 0

    handle = find_run(run_id)
    if handle is None:
        log.warning(
            "run_event_hook: resolved run_id=%r but directory not found",
            run_id,
        )
        return 0

    event = normalize_hook_event(payload, run_id)
    if event is QUARANTINE:
        # SubagentStart with no native_agent_id: quarantine (DL-022).
        log.warning(
            "run_event_hook: SubagentStart with no resolvable native_agent_id "
            "for run=%r — quarantining (DL-022)",
            run_id,
        )
        _write_quarantine(payload, reason="no_native_agent_id_subagent_start")
        return 0

    if event is None:
        # Unknown hook type — skip silently.
        return 0

    run_dir = handle.as_run_dir()
    append_event(run_dir, event)

    # Copy-on-stop for SubagentStop events (DL-016).
    if hook_type == "SubagentStop":
        _copy_native_transcript(payload, handle.path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
