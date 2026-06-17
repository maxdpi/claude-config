#!/usr/bin/env python3
"""Phase-aware resume engine honoring phase-trust (M-004).

Two independent concerns are deliberately separated:

1. **classify_phases** — SECURITY-CRITICAL consent gate.
   Reads the run manifest produced by ``write_phase_manifest`` and classifies
   each REMAINING phase by trust level.  Default-deny: a phase is auto-replayed
   ONLY if explicitly tagged ``read_only``.  Any untagged or
   ``write``/``execute`` phase requires explicit user confirmation.

   DL-021 PARENT-PRECEDENCE OVERRIDE: when the parent session runs under a
   permissive mode (``bypassPermissions``, ``acceptEdits``, or ``auto``), no
   phase is auto-replayed — all become ``needs_confirmation`` — and the result
   carries a flag so ``/resume`` can warn the user.

2. **compute_remaining_tasks** — Agent Teams remaining-task computation.
   From the durable event log, derives the incomplete task set and emits a
   fresh-team re-spawn descriptor scoped to it.  NEVER rehydrates dead
   teammates (DL-007).

Decision references
-------------------
* DL-006  Phase-trust: trust forward, falsify backward; auto-replay read-only only.
* DL-007  Agent Teams resume re-spawns a FRESH team; dead teammates are not rehydrated.
* DL-017  Phase trust maps onto native permissionMode (plan / default).
* DL-021  Parent bypassPermissions/acceptEdits/auto overrides child permissionMode.
* R-003   Default-deny is the core invariant: ambiguity -> needs_confirmation.
* R-007   permissionMode consent gate defeated by permissive parent -> drop to full deny.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from .events import EVENT_TASK_COMPLETED, EVENT_TASK_CREATED
from .manifest import read_manifest
from .paths import claude_dir, read_settings_file, read_settings_merged
from .registry import RunHandle
from .rundir import RunDir
from .team_mode import AGENT_TEAMS_ENV, read_orchestration_mode

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parent permission mode detection (DL-021)
# ---------------------------------------------------------------------------

#: Modes that override a child's permissionMode and defeat phase-trust gating.
OVERRIDING_MODES: frozenset[str] = frozenset({"bypassPermissions", "acceptEdits", "auto"})

#: Base ``~/.claude`` dir; settings reads use the shared ``read_settings_file``
#: helper, which logs corruption (present-but-unreadable) at WARNING (I1/I5).
_CLAUDE_DIR = claude_dir()


def detect_parent_permission_mode() -> str:
    """Return the effective parent session permission mode.

    Resolution order (highest to lowest priority):

    1. ``CLAUDE_PERMISSION_MODE`` environment variable — set by the Claude
       Code runtime when spawning a subprocess with an explicit permission mode.
    2. ``CLAUDE_DEFAULT_MODE`` environment variable — broader env override.
    3. ``permissions.defaultMode`` in ``~/.claude/settings.local.json``
       (local overrides user settings).
    4. ``permissions.defaultMode`` in ``~/.claude/settings.json``
       (user-level settings; DL-021 probe found ``defaultMode = "auto"`` here
       in the target environment — the COMMON CASE).
    5. Default: ``"auto"`` — when the mode cannot be determined, treat it as
       overriding (default-deny).  This is intentionally conservative: an
       unknown mode must never silently enable auto-replay of write phases
       (R-003, R-007).

    Returns:
        The detected or assumed parent permission mode string.
    """
    # 1. Runtime-injected env var (most authoritative).
    for env_key in ("CLAUDE_PERMISSION_MODE", "CLAUDE_DEFAULT_MODE"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val

    # 2. settings.local.json takes precedence over settings.json (deep-merged
    #    by the canonical read_settings_merged so local's permissions.allow does
    #    not shadow a permissions.defaultMode set only in settings.json).
    data = read_settings_merged(_CLAUDE_DIR)
    # The probe (PLATFORM-ASSUMPTIONS.md A4) found the key at
    # permissions.defaultMode in settings.json.
    mode = (data.get("permissions") or {}).get("defaultMode", "")
    if mode:
        return mode

    # 3. Unknown -> default to "auto" (overriding, safe-deny).
    return "auto"


# ---------------------------------------------------------------------------
# Phase classification (DL-006, DL-021, R-003, R-007)
# ---------------------------------------------------------------------------

#: Returned by classify_phases for each remaining phase.
CLASSIFICATION_AUTO_REPLAY = "auto_replay"
CLASSIFICATION_NEEDS_CONFIRMATION = "needs_confirmation"


def _load_manifest_safely(run: RunHandle | RunDir) -> tuple[dict[str, str], bool]:
    """Read the manifest tag table, distinguishing absence from corruption.

    Default-deny is preserved in BOTH failure modes (an empty manifest means
    every phase is untagged -> needs_confirmation).  The difference is
    observability: a *missing* manifest is a legitimate empty result, while a
    *corrupt* manifest is an anomaly that must be surfaced so ``/resume`` can
    warn the user rather than silently presenting "deny all" as if no manifest
    were ever written (I1 — absent vs corrupt).

    Returns:
        ``(manifest, corrupt)`` — the tag table (empty on either failure) and a
        flag that is ``True`` only when the file was present but unparseable.
    """
    try:
        return read_manifest(run), False
    except FileNotFoundError:
        return {}, False
    except json.JSONDecodeError as exc:
        log.warning(
            "classify_phases: manifest for run %r is present but corrupt (%s) -- "
            "defaulting all phases to needs_confirmation and flagging for /resume",
            getattr(run, "run_id", run), exc,
        )
        return {}, True


def _classify_one_phase(tag: str | None, *, overridden: bool) -> str:
    """Apply the default-deny phase-trust policy to a single phase tag.

    Auto-replay requires BOTH an explicit ``read_only`` tag AND a
    non-overriding parent mode; every other case (untagged, ``write``,
    ``execute``, or an overriding parent) denies (R-003, DL-021).
    """
    if overridden:
        # DL-021: parent overrides child permissionMode -> deny all.
        return CLASSIFICATION_NEEDS_CONFIRMATION
    if tag == "read_only":
        return CLASSIFICATION_AUTO_REPLAY
    return CLASSIFICATION_NEEDS_CONFIRMATION


def classify_phases(
    run: RunHandle | RunDir,
    parent_permission_mode: str | None = None,
) -> dict[str, Any]:
    """Classify each REMAINING phase by whether it may be auto-replayed.

    This function is the **SECURITY-CRITICAL consent gate** for resume.
    It is deliberately narrow: it ONLY reads the run manifest and the
    current projection to determine which phases are still pending, then
    applies the default-deny phase-trust policy.

    Args:
        run: A :class:`RunHandle` or :class:`RunDir` for the crashed run.
        parent_permission_mode: The parent session's permission mode.  When
            ``None``, :func:`detect_parent_permission_mode` is called.
            Pass an explicit value in tests to avoid touching the filesystem.

    Returns:
        A dict with the following keys:

        ``phases``
            Mapping of ``phase_id -> {"classification": ..., "tag": ...}``
            for every remaining (non-completed) phase known to the manifest.
            ``classification`` is one of
            ``"auto_replay"`` or ``"needs_confirmation"``.
            ``tag`` is the manifest tag (``"read_only"``, ``"write"``,
            ``"execute"``) or ``None`` when the phase is untagged.

        ``parent_permission_mode``
            The resolved parent permission mode string.

        ``permission_mode_overridden``
            ``True`` when the parent mode is in
            ``{bypassPermissions, acceptEdits, auto}`` and has suppressed
            all auto-replay.  ``/resume`` MUST surface this as a user warning
            (DL-021, R-007).

        ``manifest_corrupt``
            ``True`` when ``manifest.json`` was present but unparseable.  The
            gate still defaults every phase to ``needs_confirmation`` (default-
            deny), but this flag distinguishes lost tags from a legitimately
            absent manifest so ``/resume`` can warn the user (I1).

        ``warning``
            Human-readable warning string when ``permission_mode_overridden``
            is ``True``, otherwise ``None``.

    Default-deny invariant (R-003)
    --------------------------------
    A phase is auto-replayed ONLY if **all** of the following hold:

    * The phase is explicitly tagged ``"read_only"`` in the manifest.
    * The parent permission mode is NOT in ``OVERRIDING_MODES``.

    Any other case (untagged, ``"write"``, ``"execute"``, or overriding
    parent) results in ``"needs_confirmation"``.

    DL-021 parent-precedence override
    ------------------------------------
    When ``parent_permission_mode in OVERRIDING_MODES`` the function
    classifies ALL remaining phases as ``"needs_confirmation"`` regardless
    of their manifest tag.  The caller (``/resume``) receives
    ``permission_mode_overridden=True`` and must warn the user.
    """
    if parent_permission_mode is None:
        parent_permission_mode = detect_parent_permission_mode()

    overridden: bool = parent_permission_mode in OVERRIDING_MODES

    # Read the manifest tag table.  Missing file -> empty manifest (all phases
    # treated as untagged -> needs_confirmation under default-deny).  A corrupt
    # file behaves identically for safety but is flagged so /resume can warn.
    manifest, manifest_corrupt = _load_manifest_safely(run)

    # Read the projection to find already-completed phases.
    completed_phases: set[str] = _completed_phases(run)

    # Classify each remaining (not-yet-completed) phase that appears in the
    # manifest.  Phases in the projection but absent from the manifest are
    # also collected and classified as untagged (needs_confirmation).
    all_phase_ids: set[str] = set(manifest.keys()) | _all_known_phases(run)
    remaining_phase_ids = all_phase_ids - completed_phases

    phase_classifications: dict[str, dict[str, Any]] = {}
    for phase_id in sorted(remaining_phase_ids):
        tag: str | None = manifest.get(phase_id)
        phase_classifications[phase_id] = {
            "classification": _classify_one_phase(tag, overridden=overridden),
            "tag": tag,
        }

    warning: str | None = None
    if overridden:
        warning = (
            f"permissionMode enforcement is OVERRIDDEN: parent session runs "
            f"'{parent_permission_mode}' (one of {{bypassPermissions, acceptEdits, auto}}). "
            f"No phase will be auto-replayed regardless of its manifest tag. "
            f"All {len(phase_classifications)} remaining phase(s) require explicit "
            f"confirmation before resuming. (DL-021, R-007)"
        )
    elif manifest_corrupt:
        warning = (
            f"manifest.json for this run is present but CORRUPT; its phase-trust "
            f"tags could not be read.  All {len(phase_classifications)} remaining "
            f"phase(s) default to needs_confirmation (default-deny, R-003).  This "
            f"is NOT the same as a fresh run with no manifest -- the tag table was "
            f"lost. (I1)"
        )

    return {
        "phases": phase_classifications,
        "parent_permission_mode": parent_permission_mode,
        "permission_mode_overridden": overridden,
        "manifest_corrupt": manifest_corrupt,
        "warning": warning,
    }


def _completed_phases(run: RunHandle | RunDir) -> set[str]:
    """Return the set of phase_ids whose status is 'completed' in the projection."""
    try:
        proj = json.loads(run.projection.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()

    phases: dict[str, Any] = proj.get("phases") or {}
    return {pid for pid, info in phases.items() if isinstance(info, dict) and info.get("status") == "completed"}


def _all_known_phases(run: RunHandle | RunDir) -> set[str]:
    """Return all phase_ids mentioned in the projection (regardless of status)."""
    try:
        proj = json.loads(run.projection.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()

    phases: dict[str, Any] = proj.get("phases") or {}
    return set(phases.keys())


# ---------------------------------------------------------------------------
# Remaining-task computation for Agent Teams (DL-007, C-006)
# ---------------------------------------------------------------------------
#
# The Agent-Teams gate env var name is the single source of truth in
# ``team_mode.AGENT_TEAMS_ENV`` and is imported above -- it is NOT re-declared
# here, so a rename updates every consumer atomically (I2).


def _scan_task_events(
    run: RunHandle | RunDir,
) -> tuple[dict[str, dict[str, Any]], set[str], int]:
    """Scan ``events.jsonl`` for task lifecycle events.

    Pure read + parse: returns the created-task map (keyed by task_id), the set
    of completed task_ids, and a count of corrupt lines skipped (I1).  Kept
    separate from the respawn-descriptor assembly so each concern is readable
    and testable in isolation (I9).  An absent log yields empty results; corrupt
    lines are counted, not silently dropped.
    """
    created: dict[str, dict[str, Any]] = {}
    completed_ids: set[str] = set()

    try:
        text = run.events_jsonl.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return created, completed_ids, 0

    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue

        etype = ev.get("type")
        payload: dict[str, Any] = ev.get("payload") or {}

        if etype == EVENT_TASK_CREATED:
            task_id = payload.get("task_id") or ev.get("agent_id")
            if task_id:
                created[task_id] = {
                    "task_id": task_id,
                    "title": payload.get("title") or "",
                    "session_id": payload.get("session_id"),
                }
        elif etype == EVENT_TASK_COMPLETED:
            task_id = payload.get("task_id") or ev.get("agent_id")
            if task_id:
                completed_ids.add(task_id)

    return created, completed_ids, skipped


def compute_remaining_tasks(run: RunHandle | RunDir) -> dict[str, Any]:
    """Compute the incomplete task set and produce a fresh-team respawn descriptor.

    This function handles the **Agent Teams remaining-task concern ONLY**.
    It is deliberately separate from :func:`classify_phases` so the consent
    gate can be tested and enforced independently.

    The function reads the durable event log (``events.jsonl``) to identify
    tasks created and completed during the crashed run.  Incomplete tasks are
    those that were created but never completed.

    **Dead teammates are NEVER rehydrated (DL-007).**  The returned descriptor
    describes a fresh team to be spawned by ``/resume`` — it does not reference
    any previous teammate id.

    Args:
        run: A :class:`RunHandle` or :class:`RunDir` for the crashed run.

    Returns:
        A dict with the following keys:

        ``team_mode``
            ``True`` when ``CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`` is set to
            a truthy value AND the run contains at least one task event.
            This is necessary-but-not-sufficient — the caller must verify
            the run was actually a team run before using the descriptor.

        ``incomplete_tasks``
            List of task dicts (``{"task_id": ..., "title": ..., ...}``) that
            were created but not completed.

        ``completed_task_ids``
            Set of task_id strings that were already completed (for audit).

        ``respawn_descriptor``
            A dict describing how to re-spawn a fresh team:

            ``tasks``
                The same list as ``incomplete_tasks`` — tasks for the new team.

            ``spawn_mode``
                ``"fresh_team"`` — always.  Dead teammates are never
                rehydrated (DL-007).

            ``note``
                Human-readable note explaining the respawn strategy.

            When ``incomplete_tasks`` is empty the descriptor's ``tasks``
            list is empty and the note explains no respawn is needed.
    """
    # Prefer the mode recorded at run creation: a run's mode is a historical
    # fact, and the live env var can differ from the session that created it
    # (DL-T1-02). Fall back to the live env var only for legacy runs whose
    # run-state predates the persisted field (C-001 additive-migration).
    # NOTE: AGENT_TEAMS_ENV is imported from team_mode (single source of truth,
    # I2) rather than redeclared locally.
    persisted_mode = read_orchestration_mode(run)
    if persisted_mode is not None:
        agent_teams_enabled = persisted_mode == "agent_teams"
    else:
        agent_teams_enabled = bool(os.environ.get(AGENT_TEAMS_ENV, "").strip())

    created, completed_ids, skipped = _scan_task_events(run)
    if skipped:
        log.warning(
            "compute_remaining_tasks: skipped %d corrupt line(s) in the event log "
            "for run %r -- the remaining-task set is derived from a partial log (I1)",
            skipped, getattr(run, "run_id", run),
        )

    incomplete: list[dict[str, Any]] = [
        task for task_id, task in created.items() if task_id not in completed_ids
    ]

    has_task_events = bool(created)
    team_mode = agent_teams_enabled and has_task_events

    if incomplete:
        note = (
            f"{len(incomplete)} task(s) incomplete; spawn a fresh team scoped to "
            f"these tasks.  Dead teammates are NOT rehydrated (DL-007)."
        )
    else:
        note = (
            "No incomplete tasks found; no fresh-team respawn required."
        )

    respawn_descriptor: dict[str, Any] = {
        "tasks": incomplete,
        "spawn_mode": "fresh_team",
        "note": note,
    }

    return {
        "team_mode": team_mode,
        "incomplete_tasks": incomplete,
        "completed_task_ids": completed_ids,
        "respawn_descriptor": respawn_descriptor,
        "skipped_corrupt_lines": skipped,
    }
