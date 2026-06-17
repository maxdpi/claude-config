#!/usr/bin/env python3
"""Allocate a unique run directory and initialise its files.

Run directory layout
--------------------
::

    ~/.claude/skill-runs/<run_id>/
        run-state.json    — static run metadata (run_id, skill, started_at …)
        events.jsonl      — append-only event log (written by eventlog.py)
        projection.json   — latest folded projection (rewritten by eventlog.py)
        manifest.json     — phase tag table (written by manifest.py)
        .lock             — advisory flock file used by eventlog.py

Configuration
-------------
The base directory is resolved from ``~/.claude/settings.json`` (key
``skillRuns.baseDir``).  If the key is absent the default is
``~/.claude/skill-runs``.

The ``run_id`` is ``<ISO-timestamp>-<uuid4-short>`` — deterministic enough
to sort chronologically, unique enough to avoid collisions even under rapid
sequential invocations (R-005).
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .atomic import write_atomic
from .fold import empty_projection
from .team_mode import select_orchestration_mode

_CLAUDE_DIR = paths.claude_dir()
_SETTINGS_KEY = "skillRuns.baseDir"
_DEFAULT_BASE = _CLAUDE_DIR / "skill-runs"


def _resolve_base_dir() -> Path:
    """Read ``~/.claude/settings.json`` for ``skillRuns.baseDir``; fall back to default.

    The key name is ``skillRuns.baseDir``.  If the settings file is absent the
    default ``~/.claude/skill-runs`` is used silently; a malformed file is
    logged at WARNING by ``paths.read_settings_file`` (I1) before falling back.
    """
    for name in ("settings.local.json", "settings.json"):
        data = paths.read_settings_file(_CLAUDE_DIR / name)
        val = data.get("skillRuns", {}).get("baseDir")
        if val:
            return Path(val).expanduser()
    return _DEFAULT_BASE


def _new_run_id() -> str:
    """Return ``<compact-ISO-timestamp>-<8-char-uuid4>``."""
    ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"{ts}-{short}"


# ---------------------------------------------------------------------------
# Run directory handle
# ---------------------------------------------------------------------------


@dataclass
class RunDir:
    """Handle returned by ``create_run_dir``; exposes paths as attributes."""

    run_id: str
    base: Path

    @property
    def path(self) -> Path:
        return self.base / self.run_id

    @property
    def run_state(self) -> Path:
        return self.path / "run-state.json"

    @property
    def events_jsonl(self) -> Path:
        return self.path / "events.jsonl"

    @property
    def projection(self) -> Path:
        return self.path / "projection.json"

    @property
    def manifest(self) -> Path:
        return self.path / "manifest.json"

    @property
    def lockfile(self) -> Path:
        return self.path / ".lock"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def init_run_dir_files(
    run_dir: RunDir,
    *,
    skill: str | None = None,
    extra_state: dict | None = None,
) -> None:
    """Create the directory tree and write the five initial files for *run_dir*.

    The run id lives on the caller-supplied :class:`RunDir`, so callers that
    must control the id (e.g. the Workflow bridge, which keeps its deterministic
    ``wf-{wf_run_id}`` id) reuse this exact initialization sequence without
    inheriting :func:`create_run_dir`'s random id. ``extra_state`` is merged into
    the run-state dict after the base fields, so a caller may add its own keys
    (``wf_run_id``, ``session_id``, …) and may override ``status`` — the
    deterministic-id and per-caller-metadata invariants both survive the reuse.

    Args:
        run_dir: The (already-constructed) run directory handle to initialize.
        skill: Optional skill name recorded in ``run-state.json``.
        extra_state: Optional extra run-state fields merged after the base set.
    """
    # Create directory tree.
    run_dir.path.mkdir(parents=True, exist_ok=True)

    # run-state.json — static metadata; never rewritten after creation.
    run_state: dict = {
        "run_id": run_dir.run_id,
        "skill": skill,
        # Orchestration mode is a historical fact decided at creation, not a
        # property of the live environment — resume reads this back instead of
        # re-checking the env var, which can change between sessions (DL-T1-01).
        "orchestration_mode": select_orchestration_mode().mode,
        "started_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "status": "running",
    }
    if extra_state:
        run_state.update(extra_state)
    write_atomic(run_dir.run_state, run_state)

    # events.jsonl — append-only; start as empty file.
    run_dir.events_jsonl.touch()

    # projection.json — starts as empty projection.
    write_atomic(run_dir.projection, empty_projection())

    # manifest.json — empty tag table; populated by manifest.write_phase_manifest.
    write_atomic(run_dir.manifest, {})

    # .lock — advisory flock target; just needs to exist.
    run_dir.lockfile.touch()


def create_run_dir(
    skill: str | None = None,
    base_dir: Path | str | None = None,
) -> RunDir:
    """Allocate a unique run directory and write initial files.

    Args:
        skill: Optional skill name recorded in ``run-state.json``.
        base_dir: Override the base directory (resolved from settings or the
            ``~/.claude/skill-runs`` default when *None*).

    Returns:
        A :class:`RunDir` handle with ``path``, ``run_state``,
        ``events_jsonl``, ``projection``, ``manifest``, and ``lockfile``
        properties pointing at the new directory.
    """
    base = Path(base_dir).expanduser() if base_dir else _resolve_base_dir()
    rd = RunDir(run_id=_new_run_id(), base=base)
    init_run_dir_files(rd, skill=skill)
    return rd
