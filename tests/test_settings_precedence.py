#!/usr/bin/env python3
"""Settings-precedence contract for the canonical ``read_settings_merged`` helper.

Regression guard for the latent precedence bug: three persistence modules
(``resume``, ``rundir``, ``retention``) each read ``~/.claude`` settings with
*local-over-base* precedence, but via two opposite mechanisms — first-present-key
iteration over ``(local, json)`` in two of them and a shallow ``dict.update()``
over ``(json, local)`` in the third. Both happened to be correct, but the
divergence was a copy-paste hazard. They now all route through
``paths.read_settings_merged`` (a *deep* merge).

The load-bearing case (``test_local_allow_does_not_shadow_base_default_mode``)
pins exactly what a naive shallow merge would have broken: a
``settings.local.json`` defining only ``permissions.allow`` must NOT shadow a
``permissions.defaultMode`` set only in ``settings.json`` — that is the
security-sensitive permission-mode read (R-003/R-007).
"""
from __future__ import annotations

import json
from pathlib import Path

import sys

_SCRIPTS = Path(__file__).parent.parent / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.persistence import paths  # noqa: E402


def _write(d: Path, name: str, obj: dict) -> None:
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def test_local_overrides_base_at_leaf(tmp_path: Path) -> None:
    _write(tmp_path, "settings.json", {"theme": "dark", "skillRuns": {"retentionDays": 7}})
    _write(tmp_path, "settings.local.json", {"theme": "light"})
    merged = paths.read_settings_merged(tmp_path)
    assert merged["theme"] == "light"  # local wins
    assert merged["skillRuns"]["retentionDays"] == 7  # base-only key survives


def test_local_allow_does_not_shadow_base_default_mode(tmp_path: Path) -> None:
    """The security-sensitive case a shallow merge would have inverted."""
    _write(tmp_path, "settings.json", {"permissions": {"defaultMode": "plan"}})
    _write(tmp_path, "settings.local.json", {"permissions": {"allow": ["Bash(ls)"]}})
    merged = paths.read_settings_merged(tmp_path)
    # Deep merge keeps BOTH nested keys; defaultMode is NOT shadowed away.
    assert merged["permissions"]["defaultMode"] == "plan"
    assert merged["permissions"]["allow"] == ["Bash(ls)"]


def test_local_can_override_nested_leaf(tmp_path: Path) -> None:
    _write(tmp_path, "settings.json", {"permissions": {"defaultMode": "plan"}})
    _write(tmp_path, "settings.local.json", {"permissions": {"defaultMode": "auto"}})
    merged = paths.read_settings_merged(tmp_path)
    assert merged["permissions"]["defaultMode"] == "auto"  # local leaf wins


def test_absent_files_yield_empty(tmp_path: Path) -> None:
    assert paths.read_settings_merged(tmp_path) == {}


def test_base_only_when_local_absent(tmp_path: Path) -> None:
    _write(tmp_path, "settings.json", {"skillRuns": {"baseDir": "/x"}})
    merged = paths.read_settings_merged(tmp_path)
    assert merged["skillRuns"]["baseDir"] == "/x"


def test_call_sites_route_through_helper(tmp_path: Path, monkeypatch) -> None:
    """resume/rundir/retention read precedence via the one canonical helper."""
    from skills.lib.workflow.persistence import resume, rundir, retention

    _write(tmp_path, "settings.json", {
        "permissions": {"defaultMode": "plan"},
        "skillRuns": {"baseDir": str(tmp_path / "base-runs"), "retentionDays": 9},
    })
    _write(tmp_path, "settings.local.json", {"permissions": {"allow": ["Bash(ls)"]}})

    monkeypatch.setattr(resume, "_CLAUDE_DIR", tmp_path)
    monkeypatch.setattr(rundir, "_CLAUDE_DIR", tmp_path)
    monkeypatch.setattr(retention, "_CLAUDE_DIR", tmp_path)

    # resume permission-mode read: base defaultMode survives local allow-only file.
    assert resume.detect_parent_permission_mode() == "plan"
    # rundir base-dir read.
    assert rundir._resolve_base_dir() == (tmp_path / "base-runs")
    # retention reads via _read_settings -> deep merge.
    assert retention._retention_days() == 9
