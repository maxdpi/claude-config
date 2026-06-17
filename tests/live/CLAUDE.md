# live/

Manual live-session test kit for validating the durable substrate against a real `~/.claude` install.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `README.md` | Master runbook: safety rules, layout, five validation scenarios (S1–S5) with step-by-step commands, troubleshooting | Running any live validation scenario; read first before touching `~/.claude/settings.json` |
| `settings.debug.json` | Debug hook wiring block to merge into `~/.claude/settings.json` for S1/S5; routes all hook events to `dump_payload_hook.py` | Installing debug hooks, setting up payload capture for field-name verification |

## Subdirectories

| Directory | What | When to read |
| --------- | ---- | ------------ |
| `assert/` | Assertion scripts for live scenarios S1–S3: payload field verification, event population check, runtime dir isolation, resume classification | Running live assertions after a real skill run |
| `hooks/` | Debug capture hook script wired by `settings.debug.json` | Understanding what the debug hook captures, troubleshooting missing payloads |
