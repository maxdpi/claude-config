# hooks/

Debug capture hook wired by `tests/live/settings.debug.json` for live payload inspection.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `dump_payload_hook.py` | Reads raw CC hook payload from stdin and appends one timestamped line to `~/.claude/skill-runs-debug/payloads-<EVENT_NAME>.jsonl`; writes only to `skill-runs-debug/`, never to production substrate dirs | Understanding debug capture behavior, troubleshooting missing payload files, verifying hook safety guarantees |
