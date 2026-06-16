# Live-Session Test Kit

Master runbook for validating the durable-substrate migration against a real
`~/.claude` install. Everything here is run **by you** inside a real Claude Code
session. None of these scripts are executed automatically.

---

## SAFETY

**Read this section first.**

1. **These scripts touch your real `~/.claude`.** Review each command before
   running it. The hook and assert scripts are intentionally narrow in scope,
   but you should understand what each does.

2. **What is written:** Only `~/.claude/skill-runs-debug/` (debug payloads and
   snapshots). Never `~/.claude/teams`, `~/.claude/tasks`, or
   `~/.claude/skill-runs` (the production substrate).

3. **What is read:** `~/.claude/settings.json`, `~/.claude/skill-runs/`,
   `~/.claude/skill-runs-debug/`. Read-only operations do not modify state.

4. **Hook exit codes:** Every hook in `tests/live/hooks/` exits 0 in all
   circumstances. A capture failure is printed to stderr and swallowed —
   it cannot break your running session.

5. **How to fully uninstall the debug hooks:**
   - Open `~/.claude/settings.json`
   - Remove the `dump_payload_hook.py` command entries from each hook list
   - Keep the production `skills/hooks/*.py` entries untouched
   - Restart Claude Code (hooks are loaded at session start)
   - Verify: `ls ~/.claude/skill-runs-debug/` should stop growing after a session

6. **Prerequisite:** The `claude-config` repo must be synced to
   `~/.claude/skills/scripts` (the production install path) **or** be available
   as a checkout at a known path. The assert scripts try both automatically.
   Specifically, they look for the substrate at:
   - `<repo_root>/skills/scripts`   (worktree / dev checkout)
   - `~/.claude/skills/scripts`     (production install)

---

## Layout

```
tests/live/
  README.md                       this file
  settings.debug.json             merge this into ~/.claude/settings.json for S1/S5
  hooks/
    dump_payload_hook.py          debug capture hook (one script for all events)
  assert/
    assert_payload_fields.py      S1 — R-008 field name verdict
    assert_events_populated.py    S2 — event log + projection check
    assert_no_runtime_dir_writes.py  S2 — C-003 runtime dir isolation check
    assert_resume_classification.py  S3 — DL-021 override + phase classification
```

---

## Quick Reference

| Scenario | Priority | What it validates | Key script |
|---|---|---|---|
| S1 | **HIGHEST** | R-008: are `_PAYLOAD_*` field names correct? | `assert_payload_fields.py` |
| S2 | High | Production hooks fire + substrate is populated | `assert_events_populated.py` |
| S3 | High (keystone) | Cross-session resume + DL-021 override | `assert_resume_classification.py` |
| S4 | Medium | Workflow bridge against a real run-state | inline Python (see S4) |
| S5 | Optional | Agent Teams enabled path | teams_dir_probe + S1 |

---

## S1 — Real Payload Capture (R-008, highest priority)

**Goal:** Confirm (or refute) whether the hook payload field names assumed in
`hook_adapter._PAYLOAD_*` match the names Claude Code actually sends. This is
the #1 open question in the substrate.

**The constants being tested (from `hook_adapter.py`):**

| Constant | Assumed name | Source of assumption |
|---|---|---|
| `_PAYLOAD_AGENT_ID` | `"agentId"` | A4 transcript records (not directly from hook payload) |
| `_PAYLOAD_SESSION_ID` | `"sessionId"` | A4 transcript records |
| `_PAYLOAD_PARENT_AGENT_ID` | `"parentAgentId"` | Assumed; absent = top-level |
| `_PAYLOAD_DEPTH` | `"depth"` | Assumed; absent = 0 |
| `_PAYLOAD_TRANSCRIPT_PATH` | `"transcript_path"` | Assumed; absent triggers derive-path fallback |

**Step 1 — Set REPO_ROOT.**

```bash
REPO_ROOT="/Users/ethnet/Documents/GitHub/claude-config"
# Verify the hook script is at this path:
ls "$REPO_ROOT/tests/live/hooks/dump_payload_hook.py"
```

**Step 2 — Edit `settings.debug.json` to set the absolute path.**

Open `tests/live/settings.debug.json` and replace every instance of
`/REPO_ROOT` with your actual repo path (e.g. `/Users/ethnet/Documents/GitHub/claude-config`).

You can do this with:

```bash
sed -i '' "s|/REPO_ROOT|$REPO_ROOT|g" "$REPO_ROOT/tests/live/settings.debug.json"
```

**Step 3 — Merge the debug hook wiring into `~/.claude/settings.json`.**

The `settings.debug.json` file contains a `hooks` block with `dump_payload_hook.py`
entries for all events. Merge these **alongside** (not replacing) any existing hook
entries. For each hook event key (SubagentStart, SubagentStop, etc.), ADD the
`dump_payload_hook.py` command to the existing list.

Manual merge example — for `SubagentStart`, your settings.json should look like:

```json
"SubagentStart": [
  {
    "matcher": ".*",
    "hooks": [
      {
        "type": "command",
        "command": "cd ~/.claude/skills/scripts && PYTHONPATH=. python3 skills/hooks/subagent_start_hook.py"
      },
      {
        "type": "command",
        "command": "python3 /Users/ethnet/Documents/GitHub/claude-config/tests/live/hooks/dump_payload_hook.py SubagentStart"
      }
    ]
  }
]
```

**Step 4 — Restart Claude Code** to pick up the new hook wiring.

**Step 5 — Run any skill that spawns a subagent.** The simplest way is to
paste this message into a new Claude Code session:

```
Use the Agent tool to spawn a trivial subagent: just say "hello world" and return.
```

Or use any existing skill:

```
/codebase-analysis
```

(The `/codebase-analysis` skill spawns subagents via the Workflow tool.)

**Step 6 — Verify capture files exist.**

```bash
ls -la ~/.claude/skill-runs-debug/
# Expected: payloads-SubagentStart.jsonl and payloads-SubagentStop.jsonl
# (and possibly others depending on which events fired)

# Inspect a raw payload to see what CC actually sends:
python3 -c "import json; [print(json.dumps(json.loads(l)['payload'], indent=2)) for l in open('$HOME/.claude/skill-runs-debug/payloads-SubagentStart.jsonl').readlines()[:1]]"
```

**Step 7 — Run the assertion.**

```bash
cd "$REPO_ROOT"
python3 tests/live/assert/assert_payload_fields.py
```

**Expected outcome (if assumptions are correct):**

```
PASS  SubagentStart.agentId (constant='agentId'): present, non-null...
PASS  SubagentStart.sessionId (constant='sessionId'): present, non-null...
WARN  SubagentStart.parentAgentId: present but always None/empty. (expected for top-level)
WARN  SubagentStart.depth: present but always None/empty. (expected for top-level)
PASS/WARN  SubagentStop.transcript_path: ...
RESULT: PASS with N warning(s)
```

**If a FAIL appears:**

The FAIL line includes a `=> UPDATE hook_adapter._PAYLOAD_X = 'real_name'`
instruction. Apply that change to `hook_adapter.py` and re-run to confirm.

---

## S2 — Live Hook Firing / Event Population

**Goal:** Confirm that the production hooks fire during a real skill run, that
`events.jsonl` receives correctly-typed events, that `projection.json` matches
`replay()`, and that the substrate does not write into the runtime dirs.

**Step 1 — Ensure PRODUCTION hooks are installed.** The hooks in
`~/.claude/settings.json` should match the wiring in the repo's `settings.json`:

```
SubagentStart -> skills/hooks/subagent_start_hook.py
SubagentStop  -> skills/hooks/run_event_hook.py
TaskCreated   -> skills/hooks/run_event_hook.py
TaskCompleted -> skills/hooks/run_event_hook.py
TeammateIdle  -> skills/hooks/run_event_hook.py
SessionStart  -> skills/hooks/session_start_hook.py
Stop          -> skills/hooks/session_end_hook.py
SessionEnd    -> skills/hooks/session_end_hook.py
```

**Step 2 — Take a BEFORE snapshot** of runtime dirs:

```bash
python3 tests/live/assert/assert_no_runtime_dir_writes.py --snapshot before
```

**Step 3 — Run a ported Workflow skill.** For example:

```
/refactor
```

or, in the Claude Code session prompt:

```
/codebase-analysis
```

Wait for it to complete (or run a few phases and let it finish normally).

**Step 4 — Note the run_id.** Either from the session output or:

```bash
python3 -c "
import json, sys
sys.path.insert(0, '$REPO_ROOT/skills/scripts')
from skills.lib.workflow.persistence.registry import list_runs
runs = list_runs()
for r in sorted(runs, key=lambda x: x.get('started_at') or ''):
    print(r['run_id'], r['status'], r.get('skill'), r.get('started_at'))
"
```

**Step 5 — Assert event population.**

```bash
python3 tests/live/assert/assert_events_populated.py
# Uses the most-recently started run automatically.
# To specify a run_id:
# python3 tests/live/assert/assert_events_populated.py wf-<id>
```

**Expected:**
```
PASS  1. Run directory exists
PASS  2. events.jsonl parseable + typed
PASS  3. projection.json matches replay()
PASS  4. projection.phases non-empty (Workflow bridge)
RESULT: PASS — substrate is correctly populated after a live run.
```

**Step 6 — Check runtime dir isolation.**

```bash
python3 tests/live/assert/assert_no_runtime_dir_writes.py --check
```

**Expected:**
```
PASS: no new writes to ~/.claude/teams or ~/.claude/tasks during the run.
C-003/DL-002 constraint: CONFIRMED CLEAN
```

If `~/.claude/tasks` shows modified files, check whether those are pre-existing
subdirectories from the Claude Code task system (not the substrate). The key
question is whether any NEW files appeared. Look for `NEW FILE:` lines.

---

## S3 — Cross-Session Resume End-to-End (the keystone)

**Goal:** Confirm that when a multi-phase Workflow skill is interrupted mid-run
and a new session is started, the SessionStart hook bridges the partial Workflow
run-state, `classify_phases` returns the correct DL-021 classification, and
`/resume <id>` works.

This environment runs `defaultMode=auto` → DL-021 override is ACTIVE → every
remaining phase should be `needs_confirmation` (no auto-replay).

**Step 1 — Start a multi-phase skill and interrupt it.**

In a Claude Code session:

```
/refactor
```

Let it run through at least one phase boundary (you will see phase output in
the skill). Then **exit the session** (Cmd+Q / close the terminal / Ctrl+C
then `exit`). Do NOT wait for the skill to complete.

Alternatively, use a skill that has multiple clearly-delimited phases (like
`/planner`) and exit after the first phase output appears.

**Step 2 — Note the run_id.** Before exiting, or via the snapshot from S2.
The run_id for Workflow skills is `wf-<wfRunId>` (e.g. `wf-f423bb66-344`).

**Step 3 — Start a NEW Claude Code session** (the session that crashed is
gone). The SessionStart hook should fire `bridge_session_workflows` and surface
a resume offer. You should see output like:

```
Resumable skill runs detected:
  wf-f423b  refactor  phase=Phase 2  5m ago
Use /resume <id> to continue or /runs to list all.
```

**Step 4 — Run the classification assertion.**

```bash
python3 tests/live/assert/assert_resume_classification.py wf-<your_run_id>
```

Replace `wf-<your_run_id>` with the actual run_id from Step 2.

**Expected output (defaultMode=auto environment):**

```
Detected parent_permission_mode: 'auto'
  -> 'auto' is in OVERRIDING_MODES {bypassPermissions, acceptEdits, auto}
     DL-021 override is ACTIVE in this environment.

Classification result (N remaining phase(s)):
  Phase 2: classification='needs_confirmation', manifest_tag='write'
  ...

PASS  DL-021: permission_mode_overridden=True, 0 auto_replay phases.
      All N phase(s) -> needs_confirmation. Correct.

PASS  warning string is present (must be shown by /resume):
      permissionMode enforcement is OVERRIDDEN: parent session runs 'auto'...

RESULT: PASS
```

**Step 5 — Attempt resume in the session.**

```
/resume wf-<your_run_id>
```

Expected: Claude warns that the parent mode overrides phase-trust (DL-021 warning),
lists the remaining phases, and asks for explicit confirmation before proceeding.
No phases auto-replay.

---

## S4 — Workflow Bridge Against a Real Run-State

**Goal:** After running any Workflow skill, directly call `bridge_workflow_run`
against the actual `~/.claude/projects/.../workflows/<wfRunId>.json` file and
confirm that `projection.phases` is populated — a real, non-fixture bridge test.

**Step 1 — Find the workflow run-state JSON.**

```bash
# List all workflow run-state files from the most recent session:
find ~/.claude/projects -name "*.json" -path "*/workflows/*" | sort -t'/' -k7 | tail -10
```

Note one path, e.g.:
`~/.claude/projects/-Users-ethnet/6bc18a41-.../workflows/f423bb66-344.json`

**Step 2 — Inspect the run-state to confirm it's a Workflow skill.**

```bash
python3 -c "
import json
path = '$HOME/.claude/projects/-Users-ethnet/<session>/workflows/<runId>.json'
d = json.loads(open(path).read())
print('runId:', d.get('runId'))
print('status:', d.get('status'))
print('workflowName:', d.get('workflowName'))
print('phases:', len(d.get('workflowProgress', [])))
"
```

**Step 3 — Run the bridge and inspect the substrate run.**

```python
import sys
sys.path.insert(0, '/Users/ethnet/Documents/GitHub/claude-config/skills/scripts')

from skills.lib.workflow.persistence.workflow_bridge import bridge_workflow_run
import tempfile, os, json
from pathlib import Path

WF_PATH = Path.home() / ".claude/projects/-Users-ethnet/<session>/workflows/<runId>.json"

# Use a temp dir so this doesn't pollute the production skill-runs
with tempfile.TemporaryDirectory() as tmp:
    run_id = bridge_workflow_run(WF_PATH, skill_runs_base=tmp)
    print("run_id:", run_id)

    proj_path = Path(tmp) / run_id / "projection.json"
    proj = json.loads(proj_path.read_text())
    phases = proj.get("phases") or {}
    print("phases:", list(phases.keys()))
    if phases:
        print("PASS: bridge fired, projection.phases non-empty")
    else:
        print("FAIL: projection.phases is empty after bridge")
```

Run this as a one-off Python snippet in the Claude Code session or in a terminal.

**Expected:** `phases` list is non-empty (one entry per phase in the workflow),
proving `bridge_workflow_run` reads the real run-state and emits events correctly.

---

## S5 (Optional) — Agent Teams Enabled

**Goal:** When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set, validate that
team.md skills fire TeammateIdle payloads and that `~/.claude/teams` appears
(and may be populated) but is not written to by the substrate.

**Prerequisite:** This requires enabling the experimental flag, which is off by
default. Review the implications before enabling it in your environment.

**Step 1 — Enable Agent Teams for a single session.**

Set in the terminal before launching Claude Code:

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
claude  # start Claude Code
```

Or add to `~/.claude/settings.json`:

```json
"env": {
  "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
}
```

**Step 2 — Run a team.md skill and capture TeammateIdle payloads.**

With debug hooks installed (from S1), run:

```
/decision-critic
```

After the run, check for TeammateIdle captures:

```bash
ls ~/.claude/skill-runs-debug/payloads-TeammateIdle.jsonl
python3 -c "import json; [print(json.dumps(json.loads(l)['payload'], indent=2)) for l in open('$HOME/.claude/skill-runs-debug/payloads-TeammateIdle.jsonl').readlines()[:2]]"
```

**Step 3 — Check that `~/.claude/teams` was created by the runtime (not the substrate).**

```bash
python3 tests/live/assert/assert_no_runtime_dir_writes.py --quick
# Shows current contents of ~/.claude/teams (should exist now) and ~/.claude/tasks
```

Take a before/after snapshot around a team run to confirm the substrate
does not write to `~/.claude/teams`:

```bash
python3 tests/live/assert/assert_no_runtime_dir_writes.py --snapshot before
# ... run /decision-critic ...
python3 tests/live/assert/assert_no_runtime_dir_writes.py --check
```

**Step 4 — Check TeammateIdle payload fields.**

Run `assert_payload_fields.py` after a TeammateIdle capture — the script only
inspects SubagentStart/Stop, so TeammateIdle fields must be manually reviewed
from the raw JSON. Specifically look for: `teammate_id` (or `agentId`) and
`sessionId` in the payload. If the runtime uses different field names, update
`_PAYLOAD_TEAMMATE_ID` in `hook_adapter.py`.

**Step 5 — teams_dir_probe across session end (A3 retest).**

The probe from M-000 (`skills/scripts/skills/lib/workflow/persistence/probe/`)
can be re-run here. With Agent Teams enabled, `~/.claude/teams` should now
exist and its ephemerality can be tested:

```bash
# Check the contents before session end:
ls ~/.claude/teams/

# Exit Claude Code (session end)
# Start a new session and re-check:
ls ~/.claude/teams/
# Is it reaped? Or does it persist?
```

This re-tests the A3 finding (partially falsified in M-000 because teams was
disabled). Document the result alongside the M-000 findings.

---

## Troubleshooting

**"ERROR: cannot import substrate from any candidate path"**

The assert scripts need the substrate Python package at one of:
- `<repo_root>/skills/scripts` (the path relative to this test file)
- `~/.claude/skills/scripts`

If neither exists, sync the repo:
```bash
rsync -a /Users/ethnet/Documents/GitHub/claude-config/.claude/ ~/.claude/
```
Then re-run.

**"no runs found in skill-runs base"**

Production hooks haven't fired yet, or they wrote to a different base dir.
Check `~/.claude/settings.json` for `skillRuns.baseDir` (default: `~/.claude/skill-runs`).
Check for errors in the hook output by temporarily setting `PYTHONPATH`:

```bash
cd ~/.claude/skills/scripts
echo '{"hook_event_name":"SessionStart","session_id":"test"}' | python3 skills/hooks/session_start_hook.py
```

**"no captured payloads in skill-runs-debug/"**

The debug hook didn't fire. Verify:
1. `settings.debug.json` entries were merged into `~/.claude/settings.json`
2. The path in the command is absolute and correct
3. You restarted Claude Code after editing settings.json
4. A subagent was actually spawned (not just a regular model call)

To verify the hook runs at all:
```bash
echo '{"agentId":"test123","sessionId":"sess456"}' | python3 tests/live/hooks/dump_payload_hook.py SubagentStart
ls ~/.claude/skill-runs-debug/
```

**Projection mismatch in assert_events_populated.py**

If `projection.json != replay()`, the most common cause is a crash between an
`O_APPEND` write and the atomic projection update (the race the flock is
designed to prevent). Re-run the skill — a clean run should produce a matching
projection. If it consistently mismatches, file a bug with the mismatched JSON.

**DL-021 says `auto_replay` when it should say `needs_confirmation`**

Check `~/.claude/settings.json`:
```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); print(d.get('permissions',{}).get('defaultMode'))"
```
If this returns `"auto"`, DL-021 should be active. If `classify_phases` still
returns `auto_replay`, that is a bug in `resume.py` — file a bug with the
`classify_phases` return dict.
