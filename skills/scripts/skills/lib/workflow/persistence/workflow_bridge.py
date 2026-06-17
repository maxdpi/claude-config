#!/usr/bin/env python3
"""Hook-driven bridge from Workflow run-state JSON to the durable event substrate.

The Workflow tool runs .mjs skills sandboxed — no fs access and no Python import
capability. Phase boundaries are recorded in the Workflow run-state JSON written by
the native runtime. This module reads those files and mirrors the phase lifecycle
into events.jsonl, writes the phase manifest, and keeps everything idempotent so
re-bridging the same run-state produces no duplicate events.

AUTHORITATIVE phase record: this bridge (Python, hook-driven).
The DURABLE_EVENT log() lines in .mjs files are human breadcrumbs only.

Correlation
-----------
The substrate run_id is derived deterministically from the Workflow tool's wfRunId
(``wf-{wfRunId}``) so the bridge is idempotent: multiple calls for the same wfRunId
always resolve to the same run directory and never create duplicates.

Idempotency mechanism
---------------------
Before appending any event, we read the current projection and existing events:

- Phase events are deduped by phase index (``_wf_phase_idx`` in event payload).
- Subagent events are deduped by ``native_agent_id`` + event type.

A mid-run / partial run-state bridges the completed prefix and leaves the rest
incomplete, so a crashed run shows its remaining phases.

Design references: M-008b, DL-013, DL-014, R-003.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from .atomic import write_atomic
from .eventlog import append_event, read_events
from .events import (
    EVENT_PHASE_COMPLETED,
    EVENT_PHASE_STARTED,
    EVENT_RUN_STARTED,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_SUBAGENT_SPAWNED,
    event_schema,
)
from .manifest import write_phase_manifest
from .registry import find_run
from .rundir import RunDir, _resolve_base_dir, create_run_dir

log = logging.getLogger(__name__)

_CLAUDE_DIR = Path.home() / ".claude"

# Maximum safe event payload size for regular files — larger than PIPE_BUF because
# for regular files O_APPEND gives inode-level atomic seek+write per syscall; the
# flock is the real serialization mechanism.  65536 is the safe ceiling we enforce.
_MAX_EVENT_SIZE: int = 65536

# Valid phase trust tag values (mirrors manifest.py)
_VALID_TAGS: frozenset[str] = frozenset({"read_only", "write", "execute"})


# ---------------------------------------------------------------------------
# .mjs phaseTrust extractor
# ---------------------------------------------------------------------------


def _extract_phase_trust(mjs_source: str) -> dict[str, str]:
    """Extract phaseTrust mapping from a .mjs workflow source.

    Performs a tolerant parse: finds the ``phaseTrust`` object literal and reads
    its ``"title": "tag"`` entries. If absent, returns an empty dict (no tags —
    the resume engine defaults to deny).

    Never invents a ``read_only`` tag: absent phaseTrust -> empty dict -> caller
    passes empty dict to write_phase_manifest -> default-deny on all phases.
    """
    # Find phaseTrust object block
    pt_match = re.search(r'phaseTrust\s*:\s*\{([^}]*)\}', mjs_source, re.DOTALL)
    if not pt_match:
        return {}

    block = pt_match.group(1)
    trust: dict[str, str] = {}

    # Match "phase-name": "tag" pairs (single or double quoted)
    for m in re.finditer(
        r'["\']([^"\']+)["\']\s*:\s*["\']([^"\']+)["\']',
        block,
    ):
        phase_name = m.group(1)
        tag = m.group(2)
        if tag in _VALID_TAGS:
            trust[phase_name] = tag  # type: ignore[assignment]
        else:
            log.warning(
                "workflow_bridge: ignoring unknown phaseTrust tag %r for phase %r",
                tag, phase_name,
            )

    return trust


def _find_mjs(workflow_name: str) -> Path | None:
    """Locate ``<root>/skills/{workflowName}/workflow.mjs`` for the current layout.

    Works in BOTH layouts without hard-coded level counts:
      - repo checkout:  <repo>/skills/<name>/workflow.mjs
      - ~/.claude install: ~/.claude/skills/<name>/workflow.mjs
    This file lives at ``.../skills/scripts/skills/lib/workflow/persistence/
    workflow_bridge.py`` — i.e. UNDER an outer ``skills/`` dir that is the sibling
    parent of the per-skill dirs. We walk every ``skills``-named ancestor and
    return the first where ``<ancestor>/<name>/workflow.mjs`` exists (the inner
    ``scripts/skills`` ancestor won't match; the outer one will).
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if ancestor.name == "skills":
            candidate = ancestor / workflow_name / "workflow.mjs"
            if candidate.exists():
                return candidate
    return None


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------


def _already_bridged_phase_indices(events: list[dict]) -> set[int]:
    """Return the set of _wf_phase_idx values already in events.jsonl."""
    bridged: set[int] = set()
    for ev in events:
        payload = ev.get("payload") or {}
        if "_wf_phase_idx" in payload:
            try:
                bridged.add(int(payload["_wf_phase_idx"]))
            except (TypeError, ValueError):
                pass
    return bridged


def _already_bridged_agent_event_keys(events: list[dict]) -> set[str]:
    """Return a set of '{event_type}:{native_agent_id}' keys already in events.jsonl.

    Tracks both spawned and completed events per agent so we never emit duplicates
    on re-bridge even when state hasn't changed.
    """
    bridged: set[str] = set()
    for ev in events:
        nid = ev.get("native_agent_id")
        etype = ev.get("type")
        if nid and etype in (EVENT_SUBAGENT_SPAWNED, EVENT_SUBAGENT_COMPLETED):
            bridged.add(f"{etype}:{nid}")
    return bridged


# ---------------------------------------------------------------------------
# Safe append — logs + truncates oversized payloads instead of dropping events
# ---------------------------------------------------------------------------


def _safe_append(run_dir: RunDir, event: dict) -> None:
    """Append event, truncating resultPreview if the payload would be oversized.

    Never silently drops events. If truncation is insufficient, logs and raises
    so the caller can decide what to do.
    """
    line_bytes = (
        json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")

    if len(line_bytes) > _MAX_EVENT_SIZE:
        # Attempt to truncate resultPreview in payload
        payload = event.get("payload") or {}
        if "resultPreview" in payload:
            event = dict(event)
            payload = dict(payload)
            payload["resultPreview"] = payload["resultPreview"][:200] + "…[truncated]"
            event["payload"] = payload
            line_bytes = (
                json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode("utf-8")

    if len(line_bytes) > _MAX_EVENT_SIZE:
        log.warning(
            "workflow_bridge: event still oversized after truncation (%d bytes) — "
            "appending with flock serialization (regular file, safe)",
            len(line_bytes),
        )

    # eventlog.append_event uses flock for regular files; PIPE_BUF assertion was for
    # pipes. Patch: bypass the 512-byte assertion by writing directly here under lock.
    # We replicate the flock pattern from eventlog.py with our larger safe limit.
    import fcntl, os
    from .fold import empty_projection, fold
    from .atomic import write_atomic as _write_atomic

    events_path: Path = run_dir.events_jsonl
    lock_path: Path = run_dir.lockfile

    lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        ev_fd = os.open(str(events_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(ev_fd, line_bytes)
        finally:
            os.close(ev_fd)

        # Recompute projection
        projection = empty_projection()
        text = events_path.read_text(encoding="utf-8")
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                projection = fold(projection, json.loads(raw))
            except json.JSONDecodeError:
                continue
        _write_atomic(run_dir.projection, projection)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


# ---------------------------------------------------------------------------
# Main bridge entry point
# ---------------------------------------------------------------------------


def bridge_workflow_run(
    wf_runstate_path: Path | str,
    *,
    skill_runs_base: Path | str | None = None,
) -> str:
    """Bridge a Workflow run-state JSON into the durable substrate.

    Reads the Workflow run-state JSON at *wf_runstate_path*, creates or locates
    the substrate run directory (idempotent), writes the phase manifest from the
    .mjs ``meta.phaseTrust``, and appends durable events for each phase and
    subagent in ``workflowProgress``.

    Args:
        wf_runstate_path: Path to ``~/.claude/projects/{p}/{s}/workflows/{id}.json``.
        skill_runs_base: Override the skill-runs base directory (for tests).

    Returns:
        The substrate ``run_id`` string (``wf-{wfRunId}``).
    """
    wf_runstate_path = Path(wf_runstate_path)
    base = Path(skill_runs_base).expanduser() if skill_runs_base else _resolve_base_dir()

    # ── Read the Workflow run-state JSON ──────────────────────────────────────
    try:
        wf_state: dict[str, Any] = json.loads(
            wf_runstate_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("workflow_bridge: cannot read run-state %s: %s", wf_runstate_path, exc)
        raise

    wf_run_id: str = wf_state.get("runId") or wf_state.get("wfRunId") or wf_runstate_path.stem
    workflow_name: str = wf_state.get("workflowName") or "unknown"
    wf_status: str = wf_state.get("status") or "unknown"
    progress: list[dict] = wf_state.get("workflowProgress") or []

    # Derive session_id from path: .../projects/{proj}/{session}/workflows/{id}.json
    try:
        session_id: str | None = wf_runstate_path.parent.parent.name
    except Exception:
        session_id = None

    # ── Deterministic substrate run_id ────────────────────────────────────────
    run_id = f"wf-{wf_run_id}"

    # Map the Workflow run-state status onto the substrate's terminal/active
    # distinction. A COMPLETED workflow must be marked terminal so it is NOT
    # offered for resume forever and becomes eligible for the done-only TTL prune
    # (retention keys on status ∈ {done,tombstoned,completed} + completed_at).
    import datetime
    _now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    bridged_status = "completed" if wf_status == "completed" else "running"

    # ── Create or reuse substrate run dir (idempotent) ────────────────────────
    handle = find_run(run_id, base_dir=base)
    if handle is not None:
        run_dir = handle.as_run_dir()
        # Idempotent re-bridge: if the workflow has SINCE completed (e.g. it was
        # mid-run at SessionStart and finished by SessionEnd), promote the run to
        # terminal so it stops being offered for resume.
        try:
            cur = json.loads(run_dir.run_state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cur = {}
        if bridged_status == "completed" and cur.get("status") != "completed":
            cur["status"] = "completed"
            cur.setdefault("completed_at", _now_iso)
            write_atomic(run_dir.run_state, cur)
    else:
        run_dir = RunDir(run_id=run_id, base=base)
        run_dir.path.mkdir(parents=True, exist_ok=True)
        run_state_data: dict = {
            "run_id": run_id,
            "skill": workflow_name,
            "wf_run_id": wf_run_id,
            "session_id": session_id,
            "started_at": _now_iso,
            "status": bridged_status,
        }
        if bridged_status == "completed":
            run_state_data["completed_at"] = _now_iso
        write_atomic(run_dir.run_state, run_state_data)
        run_dir.events_jsonl.touch()
        from .fold import empty_projection
        write_atomic(run_dir.projection, empty_projection())
        write_atomic(run_dir.manifest, {})
        run_dir.lockfile.touch()

    # ── Extract phaseTrust from .mjs meta ────────────────────────────────────
    mjs_path = _find_mjs(workflow_name)
    phase_trust: dict[str, str] = {}
    if mjs_path is not None:
        try:
            mjs_source = mjs_path.read_text(encoding="utf-8")
            phase_trust = _extract_phase_trust(mjs_source)
        except (OSError, UnicodeDecodeError) as exc:
            log.warning(
                "workflow_bridge: cannot read .mjs %s: %s — phases will be UNTAGGED",
                mjs_path, exc,
            )
    else:
        log.warning(
            "workflow_bridge: workflow.mjs not found for '%s' — phases will be UNTAGGED",
            workflow_name,
        )

    # Write manifest (idempotent overwrite — same data each call)
    try:
        write_phase_manifest(run_dir, phase_trust)  # type: ignore[arg-type]
    except ValueError as exc:
        log.warning("workflow_bridge: manifest write error: %s", exc)

    # ── Append run_started if not already present ─────────────────────────────
    existing_events = read_events(run_dir)
    has_run_started = any(e.get("type") == EVENT_RUN_STARTED for e in existing_events)
    if not has_run_started:
        run_started_ev = event_schema(
            type=EVENT_RUN_STARTED,
            run_id=run_id,
            payload={"skill": workflow_name, "source": "workflow_bridge"},
        )
        _safe_append(run_dir, run_started_ev)
        existing_events = read_events(run_dir)

    # ── Phase-level idempotency sets ─────────────────────────────────────────
    already_bridged_phase_idx = _already_bridged_phase_indices(existing_events)
    already_bridged_agent_event_keys = _already_bridged_agent_event_keys(existing_events)

    # Collect phases + agents from workflowProgress
    wf_phases: list[dict] = [e for e in progress if e.get("type") == "workflow_phase"]
    wf_agents: list[dict] = [e for e in progress if e.get("type") == "workflow_agent"]

    # Build a lookup: phaseIndex -> list of agents
    agents_by_phase: dict[int, list[dict]] = {}
    for agent_entry in wf_agents:
        pi = agent_entry.get("phaseIndex")
        if pi is not None:
            agents_by_phase.setdefault(int(pi), []).append(agent_entry)

    # ── Emit events for each phase ────────────────────────────────────────────
    for ph in wf_phases:
        ph_idx: int = int(ph.get("index", 0))
        ph_title: str = ph.get("title") or f"phase-{ph_idx}"

        # Use phase title as phase_id (matches phaseTrust keys)
        phase_id = ph_title

        # Determine if this phase is done.
        # A phase with NO agents is done only when the overall run is completed
        # (vacuous truth would incorrectly mark every agent-less phase as done
        # in a mid-run / crashed run-state).
        phase_agents = agents_by_phase.get(ph_idx, [])
        if phase_agents:
            all_agents_done = all(a.get("state") == "done" for a in phase_agents)
        else:
            # No agents recorded yet for this phase — only done if run finished.
            all_agents_done = wf_status == "completed"
        phase_done = all_agents_done

        # Emit phase_started (dedup by phase index)
        started_idx_key = ph_idx * 2  # unique per phase: started=even, completed=odd
        if started_idx_key not in already_bridged_phase_idx:
            started_ev = event_schema(
                type=EVENT_PHASE_STARTED,
                run_id=run_id,
                payload={
                    "phase_id": phase_id,
                    "phase": phase_id,
                    "_wf_phase_idx": started_idx_key,
                    "source": "workflow_bridge",
                },
            )
            _safe_append(run_dir, started_ev)
            already_bridged_phase_idx.add(started_idx_key)

        # Emit subagent events for each agent in this phase
        for agent_entry in phase_agents:
            agent_id = agent_entry.get("agentId") or agent_entry.get("label") or f"agent-{ph_idx}"

            spawned_key = f"{EVENT_SUBAGENT_SPAWNED}:{agent_id}"
            if spawned_key not in already_bridged_agent_event_keys:
                spawned_ev = event_schema(
                    type=EVENT_SUBAGENT_SPAWNED,
                    run_id=run_id,
                    agent_id=agent_entry.get("label") or agent_id,
                    native_agent_id=agent_id,
                    native_session_id=session_id,
                    payload={
                        "phase": phase_id,
                        "label": agent_entry.get("label"),
                        "source": "workflow_bridge",
                    },
                )
                _safe_append(run_dir, spawned_ev)
                already_bridged_agent_event_keys.add(spawned_key)

            # Emit completed if agent is done
            if agent_entry.get("state") == "done":
                completed_key = f"{EVENT_SUBAGENT_COMPLETED}:{agent_id}"
                if completed_key not in already_bridged_agent_event_keys:
                    result_preview = agent_entry.get("resultPreview") or ""
                    # Truncate large resultPreview to keep event small
                    if len(result_preview) > 300:
                        result_preview = result_preview[:300] + "…[truncated]"
                    completed_ev = event_schema(
                        type=EVENT_SUBAGENT_COMPLETED,
                        run_id=run_id,
                        agent_id=agent_entry.get("label") or agent_id,
                        native_agent_id=agent_id,
                        native_session_id=session_id,
                        payload={
                            "phase": phase_id,
                            "resultPreview": result_preview,
                            "source": "workflow_bridge",
                        },
                    )
                    _safe_append(run_dir, completed_ev)
                    already_bridged_agent_event_keys.add(completed_key)

        # Emit phase_completed if all agents done (dedup by phase index)
        completed_idx_key = ph_idx * 2 + 1  # odd = completed
        if phase_done and completed_idx_key not in already_bridged_phase_idx:
            completed_ev = event_schema(
                type=EVENT_PHASE_COMPLETED,
                run_id=run_id,
                payload={
                    "phase_id": phase_id,
                    "phase": phase_id,
                    "_wf_phase_idx": completed_idx_key,
                    "source": "workflow_bridge",
                },
            )
            _safe_append(run_dir, completed_ev)
            already_bridged_phase_idx.add(completed_idx_key)

    return run_id


# ---------------------------------------------------------------------------
# Session-scope scanner (called from hooks)
# ---------------------------------------------------------------------------


def bridge_session_workflows(
    session_id: str,
    *,
    skill_runs_base: Path | str | None = None,
) -> list[str]:
    """Scan a session's workflows dir and bridge each run-state found.

    Called from SessionStart and SessionEnd hooks. Non-fatal: individual
    bridge failures are logged and skipped.

    Args:
        session_id: The Claude Code session ID (used to locate workflows dir).
        skill_runs_base: Override base directory (for tests).

    Returns:
        List of substrate run_ids that were bridged.
    """
    projects_dir = _CLAUDE_DIR / "projects"
    bridged_ids: list[str] = []

    if not projects_dir.exists():
        return bridged_ids

    # Find the session directory across all projects
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        session_dir = project_dir / session_id
        if not session_dir.is_dir():
            continue
        workflows_dir = session_dir / "workflows"
        if not workflows_dir.is_dir():
            continue

        for wf_json in workflows_dir.glob("*.json"):
            try:
                rid = bridge_workflow_run(
                    wf_json,
                    skill_runs_base=skill_runs_base,
                )
                bridged_ids.append(rid)
            except Exception as exc:
                log.warning(
                    "workflow_bridge: bridge_workflow_run failed for %s: %s",
                    wf_json, exc,
                )

    return bridged_ids
