#!/usr/bin/env python3
"""Run registry: derive the run list by SCANNING per-run ``run-state.json`` files.

Design notes
------------
* The registry is NEVER a separate mutable index file.  It is derived
  on-demand by scanning ``<base_dir>/*/run-state.json`` files (R-005,
  DL-003).  No global mutable file to corrupt or go stale.
* ``list_runs`` returns a lightweight summary for each discovered run
  (``run_id``, ``status``, ``skill``, ``started_at``).  Callers that need
  the full projection open ``projection.json`` via the returned :class:`RunHandle`.
* ``find_run`` returns a :class:`RunHandle` whose paths mirror :class:`RunDir`
  (same attribute names) so callers can open events / projection without
  holding on to the original ``RunDir``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .rundir import RunDir, _resolve_base_dir


# ---------------------------------------------------------------------------
# Lightweight run handle (returned by find_run)
# ---------------------------------------------------------------------------


@dataclass
class RunHandle:
    """Lightweight handle to an existing run directory.

    Mirrors :class:`RunDir` path attributes so callers can read events /
    projection without holding the original ``RunDir`` instance.
    """

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

    def as_run_dir(self) -> RunDir:
        """Return an equivalent :class:`RunDir` (same run_id + base)."""
        return RunDir(run_id=self.run_id, base=self.base)


# ---------------------------------------------------------------------------
# Registry queries
# ---------------------------------------------------------------------------


def list_runs(base_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Derive the run registry by scanning per-run ``run-state.json`` files.

    NEVER reads a separate index file — the registry is computed fresh from
    the on-disk layout each call (R-005).

    Args:
        base_dir: Base directory to scan.  Defaults to the value resolved
            from ``~/.claude/settings.json`` (``skillRuns.baseDir``) or
            ``~/.claude/skill-runs``.

    Returns:
        A list of dicts, one per discovered run, each containing at least:
        ``run_id``, ``status``, ``skill`` (may be ``None``), ``started_at``
        (ISO string), and ``active_phase`` (the last started phase or
        ``None``).  Results are sorted by ``started_at`` ascending.
    """
    base = Path(base_dir).expanduser() if base_dir else _resolve_base_dir()
    if not base.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_state_path in sorted(base.glob("*/run-state.json")):
        try:
            data = json.loads(run_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Derive active_phase from projection.json if available.
        active_phase: str | None = None
        proj_path = run_state_path.parent / "projection.json"
        if proj_path.exists():
            try:
                proj = json.loads(proj_path.read_text(encoding="utf-8"))
                phases: dict[str, Any] = proj.get("phases") or {}
                # Find any phase whose status is "running".
                running = [pid for pid, info in phases.items() if isinstance(info, dict) and info.get("status") == "running"]
                if running:
                    active_phase = running[0]
                elif phases:
                    # Fall back to the last started phase (most recently started_at).
                    def _phase_ts(pid: str) -> float:
                        info = phases[pid]
                        return info.get("started_at") or 0.0 if isinstance(info, dict) else 0.0
                    active_phase = max(phases.keys(), key=_phase_ts)
            except (json.JSONDecodeError, OSError):
                pass

        runs.append(
            {
                "run_id": data.get("run_id", run_state_path.parent.name),
                "status": data.get("status", "unknown"),
                "skill": data.get("skill"),
                "started_at": data.get("started_at"),
                "active_phase": active_phase,
            }
        )

    runs.sort(key=lambda r: r["started_at"] or "")
    return runs


def find_run(run_id: str, base_dir: Path | str | None = None) -> RunHandle | None:
    """Return a :class:`RunHandle` for *run_id*, or ``None`` if not found.

    Args:
        run_id: The run identifier to look up.
        base_dir: Base directory to search.  Defaults to the resolved base.

    Returns:
        A :class:`RunHandle` if the run directory exists and contains a
        readable ``run-state.json``, otherwise ``None``.
    """
    base = Path(base_dir).expanduser() if base_dir else _resolve_base_dir()
    candidate = base / run_id
    state_file = candidate / "run-state.json"
    if not state_file.exists():
        return None
    try:
        json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return RunHandle(run_id=run_id, base=base)
