#!/usr/bin/env python3
"""Directory-as-contract: per-subagent directory with task.json + state.json.

Design notes
------------
* Each subagent gets a directory UNDER its parent's subtree so nested
  subagents nest RECURSIVELY (parent/depth tracked in task.json).
* The substrate (this layer) writes ONLY ``.json`` files: ``task.json``
  (INPUT contract — what to do, plus substrate metadata) and ``state.json``
  (audit projection at spawn time).  LLM-facing agents write only ``.md``
  (DL-004, C-004).
* Per-subagent OUTPUT history is NOT a custom ``events.jsonl``.  The native
  transcript is the source of truth (DL-015, DL-016).  When the M-003
  SubagentStop hook fires it copies the native transcript into the subagent
  dir as ``transcript.jsonl`` (copy-on-stop primary; DL-016).  The dir
  references that copy; it does not produce its own event stream.
* All ``.json`` writes are atomic via :func:`write_atomic` (C-004, DL-003).
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from .atomic import write_atomic
from .rundir import RunDir


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def subagent_dir_path(
    run_dir: RunDir,
    agent_id: str,
    parent_chain: list[str] | None = None,
) -> Path:
    """Return the directory path for *agent_id* under *run_dir*.

    Nested subagents nest by iterating *parent_chain* from root to leaf,
    so the path is ``<run>/<p0>/<p1>/.../<agent_id>/``.

    Args:
        run_dir: Handle returned by ``create_run_dir``.
        agent_id: Skill-internal identifier for this subagent.
        parent_chain: Ordered list of ancestor agent_ids from the root parent
            outward (e.g. ``["root", "mid"]`` for a 3-deep nest).  Pass
            ``None`` or ``[]`` for a top-level subagent under the run dir.

    Returns:
        The resolved :class:`~pathlib.Path` (not yet created).
    """
    base: Path = run_dir.path
    for ancestor in (parent_chain or []):
        base = base / ancestor
    return base / agent_id


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_subagent_dir(
    run_dir: RunDir,
    agent_id: str,
    task: dict[str, Any],
    state: dict[str, Any] | None = None,
    parent_agent_id: str | None = None,
    parent_chain: list[str] | None = None,
    depth: int = 0,
) -> Path:
    """Create a per-subagent directory with ``task.json`` and ``state.json``.

    The directory is placed UNDER the parent's subtree so nested subagents
    nest recursively.  ``task.json`` is the INPUT contract — it carries the
    task payload plus substrate-owned metadata (``run_dir``, ``parent_agent_id``,
    ``depth``).  ``state.json`` is the audit projection at spawn time.

    The per-subagent OUTPUT history is NOT a custom ``events.jsonl``.  The
    M-003 SubagentStop hook copies the native transcript into this directory
    as ``transcript.jsonl`` (copy-on-stop primary; DL-016).

    Args:
        run_dir: Handle returned by ``create_run_dir``.
        agent_id: Skill-internal identifier for this subagent.
        task: Caller-supplied task payload (prompt, phase, etc.).
        state: Optional audit projection snapshot at spawn time.  Defaults to
            an empty dict; callers may supply the current run projection.
        parent_agent_id: ``agent_id`` of the spawning parent, or ``None``
            for a top-level subagent.
        parent_chain: Ordered ancestor ``agent_id`` list from root outward.
            ``None`` or ``[]`` means this is a direct child of the run dir.
        depth: Nesting depth in the subagent tree (0 = top-level).

    Returns:
        The :class:`~pathlib.Path` of the created subagent directory.
    """
    subdir = subagent_dir_path(run_dir, agent_id, parent_chain)
    subdir.mkdir(parents=True, exist_ok=True)

    # task.json — INPUT contract: what to do + substrate-owned metadata.
    task_doc: dict[str, Any] = {
        "agent_id": agent_id,
        "run_id": run_dir.run_id,
        "run_dir": str(run_dir.path),
        "parent_agent_id": parent_agent_id,
        "depth": depth,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "task": task,
    }
    write_atomic(subdir / "task.json", task_doc)

    # state.json — audit projection snapshot (substrate-written .json, DL-004).
    write_atomic(subdir / "state.json", state or {})

    return subdir
