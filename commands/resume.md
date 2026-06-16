<!-- /resume <run_id_prefix> -- phase-aware resume with default-deny consent gate. -->
<!-- Consent gate: write/execute phases require explicit confirmation; read_only phases -->
<!-- are auto-replayed. Untagged phases default to needs_confirmation. (ref: DL-006) -->
Resume a skill run from where it left off.

Usage: `/resume <run_id_prefix>`

**Consent gate**: phases tagged `write` or `execute` in the run manifest, and any
untagged phase, require explicit confirmation before re-running. Only phases
tagged `read_only` are replayed automatically. (DL-006, R-003)

---

**Step 1 — Classify remaining phases:**

```bash
python3 -c "
import sys, json
sys.path.insert(0, '$HOME/.claude/skills/scripts')
from skills.lib.workflow.persistence.registry import list_runs, find_run
from skills.lib.workflow.persistence.resume import classify_phases, detect_parent_permission_mode

prefix = '$ARGUMENTS'
if not prefix:
    print(json.dumps({'error': 'Usage: /resume <run_id_prefix>'}))
    sys.exit(1)

match = next((r for r in list_runs() if r['run_id'].startswith(prefix)), None)
if not match:
    print(json.dumps({'error': f'No run found matching: {prefix}'}))
    sys.exit(1)

handle = find_run(match['run_id'])
if handle is None:
    print(json.dumps({'error': f'Run directory not found for: {match[\"run_id\"]}'}))
    sys.exit(1)

result = classify_phases(handle)
print(json.dumps({
    'run_id': match['run_id'],
    'skill': match.get('skill'),
    'status': match.get('status'),
    'parent_permission_mode': result['parent_permission_mode'],
    'permission_mode_overridden': result['permission_mode_overridden'],
    'warning': result['warning'],
    'phases': result['phases'],
}, indent=2))
"
```

---

**Step 2 — Read the output and act accordingly:**

**If `permission_mode_overridden` is `true`:**

> **WARNING: permissionMode enforcement is OVERRIDDEN.**
> The parent session is running under a permissive mode (`bypassPermissions`, `acceptEdits`, or `auto`).
> This overrides the child's `permissionMode`, which means the consent gate cannot be enforced.
> **No phase will be auto-replayed.** Every remaining phase requires explicit user confirmation
> before proceeding. (DL-021, R-007)

Ask the user: "The parent session overrides permissionMode enforcement. Do you want to proceed
with manual confirmation for each phase?"

**For `auto_replay` phases** (only possible when `permission_mode_overridden` is false):

These phases are tagged `read_only` and will be replayed automatically. Tell the user which
phases will auto-replay.

**For `needs_confirmation` phases:**

List each phase name and ask the user to confirm each one individually before re-running.
Do not proceed with any `needs_confirmation` phase without explicit user confirmation.

---

**Step 3 — Check for Agent Teams tasks (if the run used Agent Teams):**

```bash
python3 -c "
import sys, json
sys.path.insert(0, '$HOME/.claude/skills/scripts')
from skills.lib.workflow.persistence.registry import list_runs, find_run
from skills.lib.workflow.persistence.resume import compute_remaining_tasks
import os

prefix = '$ARGUMENTS'
match = next((r for r in list_runs() if r['run_id'].startswith(prefix)), None)
if not match:
    sys.exit(0)

handle = find_run(match['run_id'])
if handle is None:
    sys.exit(0)

result = compute_remaining_tasks(handle)
if result['team_mode'] or result['incomplete_tasks']:
    print(json.dumps({
        'team_mode': result['team_mode'],
        'incomplete_tasks': result['incomplete_tasks'],
        'respawn_descriptor': result['respawn_descriptor'],
    }, indent=2))

teams_env = os.environ.get('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS', '')
if not teams_env.strip():
    print('Note: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not set.')
    print('Agent Teams mode is disabled. Fallback: Workflow tool + Agent-tool subagents.')
    print('Resume semantics are identical in both modes. (DL-009)')
"
```

**Step 4 — Resume (after user consent is obtained for all phases):**

Re-invoke the skill entry point for the run's skill, passing the `run_id` so the
skill can restore context from the durable store:

```bash
python3 -m skills.<SKILL_NAME>.<ENTRYPOINT> --resume-run-id $RUN_ID
```

Replace `<SKILL_NAME>` and `<ENTRYPOINT>` with the values from the run's
`run-state.json`. For Agent Teams runs, use the `respawn_descriptor` from
`compute_remaining_tasks()` to scope the fresh team to the incomplete task set.
Dead teammates are never rehydrated — always spawn a fresh team. (DL-007)
