# assert/

Live assertion scripts for validating substrate behavior against a real `~/.claude` install after running the S1–S3 scenarios from `live/README.md`.

## Files

| File | What | When to read |
| ---- | ---- | ------------ |
| `assert_events_populated.py` | S2: checks that `events.jsonl` is populated and typed, `projection.json` matches `replay()`, and `projection.phases` is non-empty for Workflow skills | Verifying substrate event population after a production hook run |
| `assert_no_runtime_dir_writes.py` | S2 / C-003: before/after snapshot diff of `~/.claude/teams` and `~/.claude/tasks` to confirm the substrate never writes into runtime dirs | Validating runtime dir isolation during or after a skill run |
| `assert_payload_fields.py` | S1 / R-008: cross-checks every `hook_adapter._PAYLOAD_*` constant against actual captured SubagentStart/Stop payload keys; reports CONFIRMED/ABSENT/NULL per field | Verifying or refuting assumed hook payload field names after a real subagent spawn |
| `assert_resume_classification.py` | S3: calls `resume.classify_phases` on an interrupted run and asserts DL-021 override fires (`permission_mode_overridden=True`, all phases `needs_confirmation`) in a `defaultMode=auto` environment | Testing cross-session resume classification and DL-021 override behavior |
