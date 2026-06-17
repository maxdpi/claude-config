# Skills Architecture

Agent workflows implemented on two native runtimes: the **Workflow tool** for
linear skills and **Agent Teams** for adversarial skills. A durable substrate
(`skills/scripts/skills/lib/workflow/persistence/`) provides cross-session run
state and resume that neither native runtime supplies on its own.

## Runtimes

### Workflow Tool — linear skills

Entry point: `skills/<name>/workflow.mjs`

Each script exports `meta` (name, phases list, `phaseTrust` table) and a `run()`
function. Control flow uses `phase()`, `agent()`, `parallel()`, and `pipeline()`
primitives from the native Workflow tool. Sub-agent `.md` definitions live under
`agents/` and are invoked via `agentType` on `agent()` opts; frontmatter
(`permissionMode`, `maxTurns`, `skills:`) lives on those `.md` files (DL-023),
not on the `.mjs` script.

| Skill               | Entry point                             |
| ------------------- | --------------------------------------- |
| `codebase-analysis` | `skills/codebase-analysis/workflow.mjs` |
| `refactor`          | `skills/refactor/workflow.mjs`          |
| `planner`           | `skills/planner/workflow.mjs`           |
| `arxiv-to-md`       | `skills/arxiv-to-md/workflow.mjs`       |
| `incoherence`       | `skills/incoherence/workflow.mjs`       |
| `prompt-engineer`   | `skills/prompt-engineer/workflow.mjs`   |
| `leon-writing-style`| `skills/leon-writing-style/workflow.mjs`|

Example `meta` block (from `refactor/workflow.mjs`):

```js
export const meta = {
  name: "refactor",
  phases: ["mode_selection", "dispatch", "triage", "cluster", "contextualize", "synthesize"],
  phaseTrust: {
    "mode_selection": "read_only",
    "dispatch":       "read_only",
    // ...
  },
};
```

The `phaseTrust` table is the single source of truth consumed by the durable
substrate's `write_phase_manifest()` to classify which phases the resume engine
auto-replays (DL-014).

### Agent Teams — adversarial skills

Entry point: `skills/<name>/team.md`

Gated on `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. When the env var is unset, the
skill falls back to a Workflow tool + Agent-tool subagent path that produces
identical durable events (DL-009).

`team.md` files carry YAML frontmatter (`skills:`, `tools:`, `model:`) and a
body embedded as the team definition. The body IS applied to teammates on the
Agent Teams path; `skills:` in frontmatter is a fallback-path mechanism only
(DL-023).

Agent definitions referenced by teammates live under `agents/` (e.g.
`../../agents/quality-reviewer.md`, `../../agents/architect.md`).

| Skill             | Entry point                        | Team shape                                    |
| ----------------- | ---------------------------------- | --------------------------------------------- |
| `decision-critic` | `skills/decision-critic/team.md`   | Lead (architect) + verifier + challenger      |
| `deepthink`       | `skills/deepthink/team.md`         | Lead + parallel analytical teammates          |
| `problem-analysis`| `skills/problem-analysis/team.md`  | Lead + parallel investigation teammates       |

## Durable Substrate

`skills/scripts/skills/lib/workflow/persistence/`

Bridges the gap that both native runtimes share: `resumeFromRunId` is
same-session-only (A2, confirmed in `docs/PLATFORM-ASSUMPTIONS.md`). The
substrate provides cross-session run state and phase-aware resume.

### Run directory layout

```
~/.claude/skill-runs/<run_id>/
    run-state.json    — static metadata (run_id, skill, started_at, status)
    events.jsonl      — append-only event log
    projection.json   — latest folded projection (pure fold over events)
    manifest.json     — phase tag table (read_only / execute per phase)
    .lock             — advisory flock file
```

`run_id` format: `<ISO-timestamp>-<8-char-uuid4>` (sortable, collision-safe).
Base dir resolves from `~/.claude/settings.json` key `skillRuns.baseDir`;
defaults to `~/.claude/skill-runs`.

### Event model

`events.jsonl` is append-only. The `fold()` function is pure: it reduces the
event log to `projection.json` without I/O or mutation (C-005). Unknown event
types are ignored (forward-compatible). Key event types:

- `run_started`, `run_completed`, `run_failed`
- `phase_started`, `phase_completed`
- `subagent_spawned`, `subagent_completed`
- `task_created`, `task_completed` (Agent Teams path)
- `resume_cursor`

### Mirror OUT via hooks

`hook_adapter.py` and `workflow_bridge.py` connect native runtime lifecycle
events (SubagentStop, etc.) to `append_event()`. The hook bridge is the
authoritative phase-record writer; `log()` lines in `.mjs` files are human
breadcrumbs only.

### Phase-trust resume

`resume.py` implements a default-deny consent gate (R-003, DL-006):

- `read_only` phases auto-replay on resume.
- `execute` / `write` phases and any untagged phase require explicit user
  confirmation.
- DL-021 override: when the parent session runs under `bypassPermissions`,
  `acceptEdits`, or `auto`, ALL phases become `needs_confirmation` regardless
  of their tag.

Agent Teams resume (DL-007): re-spawns a fresh team scoped to incomplete tasks
from the durable event log. Dead teammates are never rehydrated.

### Slash commands

| Command              | Source file            | What                                              |
| -------------------- | ---------------------- | ------------------------------------------------- |
| `/runs`              | `commands/runs.md`     | List runs from the registry as a table            |
| `/run-status`        | `commands/run-status.md` | Show projection for a specific run_id           |
| `/resume <run_id>`   | `commands/resume.md`   | Phase-aware resume with consent gate              |

See `docs/PLATFORM-ASSUMPTIONS.md` for the empirically validated platform facts
(journal layout, `resumeFromRunId` scope, subagent transcript paths, `~/.claude/tasks`
ephemerality) that the substrate design is built on.

## Non-ported Skills

Two skills still run on the Python runtime directly. See each skill's `SKILL.md`
for invocation.

| Skill        | Entry point               | Notes                                   |
| ------------ | ------------------------- | --------------------------------------- |
| `doc-sync`   | `skills/doc-sync/SKILL.md`  | Documentation sync across a repository |
| `cc-history` | `skills/cc-history/SKILL.md`| Claude Code conversation history analysis |

## Shared Python Helpers

`skills/scripts/skills/lib/workflow/` — what survives after the Python
orchestration layer was removed:

| File/Module     | What                                                   |
| --------------- | ------------------------------------------------------ |
| `core.py`       | `Workflow`, `StepDef`, `Arg` — metadata types (legacy; scheduled for deletion in M-008b after parity gate R-004) |
| `discovery.py`  | Pull-based workflow discovery via importlib scanning   |
| `types.py`      | Domain types: `Dispatch`, `AgentRole`, etc.            |
| `prompts/step.py` | `format_step(body, next_cmd, title)` — assemble a step block |
| `prompts/file.py` | `format_file_content(path, content)` — embed file content with 4-backtick fence |
| `persistence/`  | Durable substrate (see above)                          |

`prompts/__init__.py` exports only `format_step` and `format_file_content`.
The dispatch-prose module (`subagent.py`) has been deleted (DL-025).

## Repo Facts

- Synced into `~/.claude` via `sync.sh`.
- Agent persona definitions: `agents/` (architect, developer, researcher,
  quality-reviewer, technical-writer, debugger).
- Shared writing conventions: `conventions/` (documentation, temporal, structural,
  severity, intent-markers).
