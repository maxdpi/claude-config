#!/usr/bin/env python3
"""Phase manifest: declare and read per-phase read_only|write|execute tags.

The manifest is the authoritative tag table consumed by the resume engine
(DL-014, DL-006).  Default-deny: a phase NOT listed in the manifest is
absent from the tag table and the resume engine MUST treat it as requiring
explicit confirmation before replay.

Tag values
----------
``read_only``
    Phase performs only reads/analysis; safe to auto-replay on resume.
``write``
    Phase mutates state (files, configs, …); requires confirmation.
``execute``
    Phase runs side-effecting commands; requires confirmation.

Phases not tagged are simply absent from the manifest (the resume engine's
default-deny policy prevents them from being auto-replayed).
"""
from __future__ import annotations

from typing import Literal

from .atomic import write_atomic
from .rundir import RunDir

PhaseTag = Literal["read_only", "write", "execute"]

_VALID_TAGS: frozenset[str] = frozenset({"read_only", "write", "execute"})


def write_phase_manifest(run_dir: RunDir, phases: dict[str, PhaseTag]) -> None:
    """Persist the phase tag table to ``manifest.json`` atomically.

    Args:
        run_dir: Handle returned by ``create_run_dir``.
        phases: Mapping of ``phase_id -> tag`` where tag is one of
            ``"read_only"``, ``"write"``, or ``"execute"``.  Phases not
            present in this mapping will be absent from the manifest
            (default-deny by the resume engine).

    Raises:
        ValueError: If any tag value is not one of the three valid strings.
    """
    invalid = {k: v for k, v in phases.items() if v not in _VALID_TAGS}
    if invalid:
        raise ValueError(
            f"Invalid phase tag(s): {invalid!r}.  "
            f"Valid values are: {sorted(_VALID_TAGS)}"
        )
    write_atomic(run_dir.manifest, dict(phases))


def read_manifest(run_dir: RunDir) -> dict[str, PhaseTag]:
    """Return the phase tag table from ``manifest.json``.

    Args:
        run_dir: Handle returned by ``create_run_dir``.

    Returns:
        A dict mapping ``phase_id -> tag``.  Phases absent from the file
        are absent from the returned dict; the caller applies default-deny.

    Raises:
        FileNotFoundError: If ``manifest.json`` does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    import json

    return json.loads(run_dir.manifest.read_text(encoding="utf-8"))
