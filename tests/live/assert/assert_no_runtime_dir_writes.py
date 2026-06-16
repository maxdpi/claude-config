#!/usr/bin/env python3
"""Assert: substrate never writes under ~/.claude/teams or ~/.claude/tasks.

PURPOSE (Scenario S2, C-003/DL-002):
    This script supports a BEFORE/AFTER workflow:

    BEFORE a skill run:
        python3 assert_no_runtime_dir_writes.py --snapshot before

    AFTER the skill run:
        python3 assert_no_runtime_dir_writes.py --check

    The --snapshot command records the current state (mtime + file listing)
    of ~/.claude/teams and ~/.claude/tasks to a JSON snapshot file.
    The --check command re-scans and compares — reporting any new files or
    modified mtimes that appeared during the run.

    A --quick mode performs a single-shot check without a prior snapshot,
    reporting the current contents (useful for understanding the baseline).

USAGE:
    # Before the skill run:
    python3 tests/live/assert/assert_no_runtime_dir_writes.py --snapshot before

    # After the skill run:
    python3 tests/live/assert/assert_no_runtime_dir_writes.py --check

    # Just show current state:
    python3 tests/live/assert/assert_no_runtime_dir_writes.py --quick

SNAPSHOT FILE:
    Written to ~/.claude/skill-runs-debug/runtime_dir_snapshot_<label>.json
    (same debug directory; never touches the production substrate)

WHAT IT READS:
    ~/.claude/teams/  (may not exist if Agent Teams is disabled)
    ~/.claude/tasks/

WHAT IT WRITES:
    ~/.claude/skill-runs-debug/runtime_dir_snapshot_<label>.json  (--snapshot only)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_CLAUDE_DIR: Path = Path.home() / ".claude"
_MONITORED_DIRS: list[Path] = [
    _CLAUDE_DIR / "teams",
    _CLAUDE_DIR / "tasks",
]
_DEBUG_DIR: Path = _CLAUDE_DIR / "skill-runs-debug"


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _scan_dir(d: Path) -> dict:
    """Return a dict of {relative_path: mtime} for all files under d."""
    result: dict = {}
    if not d.exists():
        return {"_exists": False}
    result["_exists"] = True
    try:
        for entry in sorted(d.rglob("*")):
            if entry.is_file():
                try:
                    st = entry.stat()
                    result[str(entry.relative_to(d))] = {
                        "mtime": st.st_mtime,
                        "size": st.st_size,
                    }
                except OSError:
                    pass
    except OSError:
        pass
    return result


def _take_snapshot(label: str) -> dict:
    """Capture the current state of monitored dirs."""
    snap: dict = {
        "label": label,
        "ts": time.time(),
        "dirs": {},
    }
    for d in _MONITORED_DIRS:
        snap["dirs"][str(d)] = _scan_dir(d)
    return snap


def _save_snapshot(snap: dict, label: str) -> Path:
    """Write snapshot to the debug dir."""
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEBUG_DIR / f"runtime_dir_snapshot_{label}.json"
    path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _load_snapshot(label: str) -> dict | None:
    """Load a previously saved snapshot."""
    path = _DEBUG_DIR / f"runtime_dir_snapshot_{label}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _compare(before: dict, after: dict) -> list[str]:
    """Return a list of change descriptions between two snapshots."""
    changes: list[str] = []
    before_dirs: dict = before.get("dirs", {})
    after_dirs: dict = after.get("dirs", {})

    all_dir_keys = set(before_dirs) | set(after_dirs)
    for dir_key in sorted(all_dir_keys):
        b = before_dirs.get(dir_key, {})
        a = after_dirs.get(dir_key, {})

        # Directory existence changed
        if not b.get("_exists", False) and a.get("_exists", False):
            changes.append(f"CREATED: {dir_key} directory appeared during run")
        elif b.get("_exists", False) and not a.get("_exists", False):
            changes.append(f"DELETED: {dir_key} directory disappeared during run (unexpected)")

        if not a.get("_exists", False):
            continue

        b_files = {k: v for k, v in b.items() if k != "_exists"}
        a_files = {k: v for k, v in a.items() if k != "_exists"}

        new_files = set(a_files) - set(b_files)
        deleted_files = set(b_files) - set(a_files)
        common_files = set(b_files) & set(a_files)

        for f in sorted(new_files):
            changes.append(f"NEW FILE: {dir_key}/{f} (size={a_files[f]['size']})")

        for f in sorted(deleted_files):
            changes.append(f"DELETED: {dir_key}/{f}")

        for f in sorted(common_files):
            if b_files[f]["mtime"] != a_files[f]["mtime"]:
                changes.append(
                    f"MODIFIED: {dir_key}/{f} "
                    f"(mtime {b_files[f]['mtime']:.1f} -> {a_files[f]['mtime']:.1f})"
                )

    return changes


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def mode_snapshot(label: str) -> None:
    """Take a snapshot and save it."""
    snap = _take_snapshot(label)
    path = _save_snapshot(snap, label)
    print(f"Snapshot '{label}' saved to: {path}")
    for d, contents in snap["dirs"].items():
        exists = contents.get("_exists", False)
        n_files = len([k for k in contents if k != "_exists"])
        print(f"  {d}: {'exists' if exists else 'does not exist'}, {n_files} file(s) found")


def mode_check() -> None:
    """Load the 'before' snapshot and compare against current state."""
    before = _load_snapshot("before")
    if before is None:
        print("FAIL: no 'before' snapshot found.")
        print(f"Run --snapshot before first: python3 {__file__} --snapshot before")
        return

    after = _take_snapshot("after")
    elapsed = after["ts"] - before["ts"]
    print("=" * 72)
    print(f"Comparing: before (ts={before['ts']:.0f}) -> after (ts={after['ts']:.0f}) [{elapsed:.0f}s elapsed]")
    print(f"Monitored: {[str(d) for d in _MONITORED_DIRS]}")
    print("=" * 72)

    changes = _compare(before, after)
    if changes:
        print(f"\nFAIL: {len(changes)} change(s) detected in runtime dirs:\n")
        for c in changes:
            print(f"  {c}")
        print(
            "\nThe substrate wrote to ~/.claude/teams or ~/.claude/tasks."
            "\nThis violates C-003/DL-002."
            "\nIf these are pre-existing task subdirs (not new during the run), "
            "check whether ANY entry has a newer mtime — NEW FILE lines are the concern."
        )
    else:
        print("\nPASS: no new writes to ~/.claude/teams or ~/.claude/tasks during the run.")
        print("C-003/DL-002 constraint: CONFIRMED CLEAN")

    # Also save the after snapshot for reference
    _save_snapshot(after, "after")
    print(f"\nAfter snapshot saved to: {_DEBUG_DIR}/runtime_dir_snapshot_after.json")


def mode_quick() -> None:
    """Quick scan — show current contents without comparison."""
    print("Current state of runtime dirs:")
    for d in _MONITORED_DIRS:
        scan = _scan_dir(d)
        if not scan.get("_exists"):
            print(f"  {d}: does not exist")
            continue
        files = {k: v for k, v in scan.items() if k != "_exists"}
        print(f"  {d}: {len(files)} file(s)")
        for f, info in sorted(files.items()):
            print(f"    {f}  size={info['size']}  mtime={info['mtime']:.0f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  --snapshot <label>  Take a snapshot (use 'before' before the run)")
        print("  --check             Compare current state against 'before' snapshot")
        print("  --quick             Show current state without comparison")
        return

    if args[0] == "--snapshot":
        label = args[1] if len(args) > 1 else "snapshot"
        mode_snapshot(label)
    elif args[0] == "--check":
        mode_check()
    elif args[0] == "--quick":
        mode_quick()
    else:
        print(f"Unknown argument: {args[0]}")
        print("Use --snapshot <label>, --check, or --quick")


if __name__ == "__main__":
    main()
