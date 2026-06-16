#!/usr/bin/env python3
"""Debug-capture hook: dump the raw CC hook payload to a per-event JSONL file.

Usage (wired from settings.debug.json):
    python3 /path/to/dump_payload_hook.py <EVENT_NAME>

For example:
    python3 .../dump_payload_hook.py SubagentStart

The hook reads the JSON payload from stdin (Claude Code hook convention),
stamps a monotonic timestamp and the event name, and APPENDS one line to:

    ~/.claude/skill-runs-debug/payloads-<EVENT_NAME>.jsonl

The output directory is created if it does not exist.

SAFETY GUARANTEES:
- This hook NEVER touches ~/.claude/teams, ~/.claude/tasks, or
  ~/.claude/skill-runs (the production substrate).
- It writes ONLY to ~/.claude/skill-runs-debug/.
- It exits 0 in all circumstances — a capture failure is logged to stderr
  but never breaks the running session.
- It does not import any substrate modules.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Output directory — intentionally separate from the production substrate.
# ---------------------------------------------------------------------------

_DEBUG_DIR: Path = Path.home() / ".claude" / "skill-runs-debug"
_FORBIDDEN_PREFIXES: tuple[Path, ...] = (
    Path.home() / ".claude" / "teams",
    Path.home() / ".claude" / "tasks",
)


def _safe_write(event_name: str, payload: dict) -> None:
    """Write one captured payload line to the per-event JSONL file.

    Never raises — any error is printed to stderr and swallowed.
    """
    # Verify we are not accidentally targeting a forbidden directory
    # (defensive: the constant above is correct, but belt-and-suspenders).
    for forbidden in _FORBIDDEN_PREFIXES:
        if str(_DEBUG_DIR).startswith(str(forbidden)):
            print(
                f"dump_payload_hook: BUG — output dir {_DEBUG_DIR} overlaps "
                f"forbidden prefix {forbidden}; aborting write.",
                file=sys.stderr,
            )
            return

    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"dump_payload_hook: cannot create {_DEBUG_DIR}: {exc}", file=sys.stderr)
        return

    out_path: Path = _DEBUG_DIR / f"payloads-{event_name}.jsonl"
    record: dict = {
        "ts": time.time(),
        "event": event_name,
        "payload": payload,
    }
    line: str = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        print(
            f"dump_payload_hook: write to {out_path} failed: {exc}",
            file=sys.stderr,
        )


def main() -> int:
    """Entry point. Always returns 0."""
    event_name: str = sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN"

    try:
        raw = sys.stdin.read()
        payload: dict = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"dump_payload_hook ({event_name}): stdin parse error: {exc}",
            file=sys.stderr,
        )
        payload = {"_parse_error": str(exc)}

    _safe_write(event_name, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
