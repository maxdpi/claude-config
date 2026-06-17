#!/usr/bin/env python3
"""Run-aware status line for the durable skill-run substrate.

Reads the Claude Code status-line payload on stdin and prints a single line:

    ⏵ Opus 4.8 · claude-config · ◇ 2 active (agent-teams ·3⚡)

The trailing run segment is shown only when there are *active* skill runs —
runs whose ``projection.json`` reports ``status == "running"`` and were touched
recently (so a stale/crashed run does not masquerade as live; the SessionStart
hook already surfaces resumable runs separately). It names the most-recently
active run's skill and its count of still-running subagents.

Design constraints (this runs on every render):
  * stdlib only, no package import — sidesteps the hooks' sys.path bootstrap
    fragility and keeps startup instant;
  * bounded work — at most ``_SCAN_LIMIT`` of the newest run dirs are parsed;
  * never raises — any error degrades to the model+dir prefix (or an empty line).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

#: Newest run dirs to parse per render (bounds work when many runs accumulate).
_SCAN_LIMIT = 40
#: A "running" run is only counted active if touched within this window.
_ACTIVE_WINDOW_SECONDS = 4 * 60 * 60


def _claude_dir() -> Path:
    return Path.home() / ".claude"


def _skill_runs_base() -> Path:
    """Resolve the skill-runs base dir, honoring ``skillRuns.baseDir`` if set.

    Mirrors the substrate default without importing it. Local settings override
    base settings; both are read tolerantly.
    """
    base = _claude_dir() / "skill-runs"
    merged: dict = {}
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((_claude_dir() / name).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged.update(data)
        except (OSError, ValueError):
            continue
    configured = (merged.get("skillRuns") or {}).get("baseDir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser()
    return base


def _active_runs(base: Path, now: float) -> list[dict]:
    """Return projection dicts for recently-touched ``status == running`` runs."""
    if not base.is_dir():
        return []
    try:
        dirs = [p for p in base.iterdir() if p.is_dir()]
    except OSError:
        return []
    dirs.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    active: list[dict] = []
    for d in dirs[:_SCAN_LIMIT]:
        proj = d / "projection.json"
        try:
            if now - proj.stat().st_mtime > _ACTIVE_WINDOW_SECONDS:
                continue
            data = json.loads(proj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("status") == "running":
            active.append(data)
    return active


def _running_subagents(projection: dict) -> int:
    subs = projection.get("subagents")
    if not isinstance(subs, dict):
        return 0
    return sum(
        1 for s in subs.values()
        if isinstance(s, dict) and s.get("status") == "running"
    )


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}

    model = (payload.get("model") or {}).get("display_name") or "Claude"
    cwd = (payload.get("workspace") or {}).get("current_dir") or payload.get("cwd") or ""
    dir_name = Path(cwd).name if cwd else ""

    segments = [f"⏵ {model}"]
    if dir_name:
        segments.append(dir_name)

    try:
        active = _active_runs(_skill_runs_base(), time.time())
    except Exception:
        active = []

    if active:
        top = active[0]
        skill = top.get("skill") or "run"
        running = _running_subagents(top)
        tail = f"{skill} ·{running}⚡" if running else skill
        segments.append(f"◇ {len(active)} active ({tail})")

    print(" · ".join(segments))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A status line must never error loudly; emit nothing on catastrophe.
        print("")
