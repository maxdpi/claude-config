#!/usr/bin/env python3
"""Replay events.jsonl -> projection (verification / recovery).

``replay`` reads the append-only event log from scratch, folds each event
through the pure ``fold`` function, and returns the resulting projection.
The output is deterministic and must be byte-for-byte identical to the
``projection.json`` last written by ``eventlog.append_event``.

This function is used:
* To verify that ``projection.json`` matches the canonical replay.
* To recover a correct projection if ``projection.json`` is absent or
  corrupted (e.g., after a crash between the O_APPEND and the atomic write).
"""
from __future__ import annotations

import json

from .eventlog import _replay_from_path
from .rundir import RunDir


def replay(run_dir: RunDir) -> dict:
    """Deterministically reproduce the projection from ``events.jsonl``.

    Reads every line of ``run_dir.events_jsonl``, skipping blank lines and
    malformed JSON, and reduces through :func:`fold` starting from an empty
    projection.

    Args:
        run_dir: Handle returned by ``create_run_dir``.

    Returns:
        The projection dict that ``projection.json`` should contain.
    """
    return _replay_from_path(run_dir.events_jsonl)


def verify_projection(run_dir: RunDir) -> bool:
    """Return True if ``projection.json`` matches a fresh replay.

    Compares the stored ``projection.json`` against ``replay(run_dir)``
    using normalised JSON (sorted keys, no whitespace differences).

    Args:
        run_dir: Handle returned by ``create_run_dir``.

    Returns:
        ``True`` when they match, ``False`` when they diverge.
    """
    stored_text = run_dir.projection.read_text(encoding="utf-8")
    stored = json.loads(stored_text)
    replayed = replay(run_dir)

    def canonical(d: dict) -> str:
        return json.dumps(d, ensure_ascii=False, sort_keys=True)

    return canonical(stored) == canonical(replayed)
