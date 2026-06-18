# persistence/

Durable event-sourcing substrate for skill runs: run directories, append-only event log, projection, phase manifest, and resume engine.

## Files

| File                | What                                                                             | When to read                                                          |
| ------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `__init__.py`       | Public API exports for all substrate primitives                                  | Importing persistence types, understanding public surface             |
| `atomic.py`         | `write_atomic()` — tmp-file + fsync + `os.rename` + parent-dir fsync            | Modifying any file-write path, understanding write-safety invariants  |
| `contract.py`       | Per-subagent directory contract: `task.json` (input) + `state.json` (audit projection) | Adding subagent tracking, modifying spawn contracts              |
| `eventlog.py`       | `append_event()` — O_APPEND kernel-atomic write to `events.jsonl`, rewrites `projection.json` | Adding event types, debugging concurrent hook writes          |
| `events.py`         | Workflow-level event envelope schema and event-type constants                    | Adding event types, understanding event payload shape                 |
| `fold.py`           | Pure projection fold: `events.jsonl` → `projection` (no I/O, no side effects)   | Understanding projection semantics, adding new event handling         |
| `hook_adapter.py`   | Single normalization point: CC hook payloads → `SkillEvent` dicts                | Modifying hook field names, adding new hook payload fields            |
| `journal_bridge.py` | Best-effort mirror of Workflow-tool journal entries into `events.jsonl`          | Debugging journal-to-substrate sync (M-006)                           |
| `manifest.py`       | Phase manifest: declares `read_only`/`write`/`execute` tags per phase            | Modifying phase trust, understanding default-deny resume gate         |
| `paths.py`          | Shared fs primitives: `claude_dir()`, `read_settings_file()` (absent-vs-corrupt), `iso_now()`, `quarantine_path()` | Adding a shared path/settings primitive; avoiding per-module copies |
| `projection.py`     | `replay()` — deterministic replay of `events.jsonl` for verification             | Verifying projection integrity, debugging crash recovery              |
| `registry.py`       | Run registry derived by scanning `*/run-state.json` — no global index file       | Listing runs, finding runs by id, understanding scan-based discovery  |
| `resume.py`         | Phase-aware resume engine: `classify_phases()` (consent gate) + `compute_remaining_tasks()` | Modifying resume UX, understanding phase-trust security model |
| `retention.py`      | TTL pruning (`prune_runs`) and resumability gate (`is_resumable`)                | Modifying retention policy, debugging stale run cleanup               |
| `rundir.py`         | `create_run_dir()` — allocates `~/.claude/skill-runs/<run_id>/` and initializes files | Adding new run-dir files, understanding run directory layout      |
| `team_mode.py`      | Orchestration mode selection: Agent Teams vs Agent-tool subagent fallback        | Understanding mode detection, modifying fallback behavior             |
| `teams_bridge.py`   | Hook-driven bridge: Agent Teams hook events → durable substrate                  | Debugging Agent Teams capture, modifying team event handling          |
| `workflow_bridge.py`| Hook-driven bridge: Workflow-tool run-state JSON → `events.jsonl` + manifest     | Debugging Workflow-tool phase bridging, modifying phase lifecycle     |

## Substrate stratification (assessed, not split) — DL-T3-10

The persistence substrate has a natural two-tier boundary that is **already true by
usage**. No modules are split — documenting the existing boundary captures the same
value without churn.

**Shared modules** (imported by both linear `workflow.mjs` skills AND adversarial
`SKILL.md` skills):

| Module           | Used by adversarial skills? |
| ---------------- | --------------------------- |
| `events.py`      | yes — event envelope schema |
| `teams_bridge.py`| yes — Agent Teams hook capture |
| `team_mode.py`   | yes — mode detection |
| `atomic.py`      | yes — write-safety primitive |
| `paths.py`       | yes — shared fs primitives |
| `registry.py`    | yes — run listing |
| `fold.py`        | yes — pure projection fold |

**Linear-skill / Workflow-tool–only modules** (never on the adversarial path):

| Module              | Why adversarial skills don't touch it |
| ------------------- | ------------------------------------- |
| `manifest.py`       | phase-trust manifest; adversarial skills have no Workflow phases |
| `resume.py`         | Workflow-tool resume engine; adversarial leads re-invoke manually |
| `workflow_bridge.py`| Workflow-tool hook bridge; not wired for NL-lead sessions |
| `plan_html.py`      | plan HTML rendering; planner-only |
| `journal_bridge.py` | Workflow-tool journal sync; adversarial skills have no journal |

**Why adversarial skills are NOT re-platformed onto the Workflow tool (DL-T3-10):**
Content-hash keying of `(prompt, opts)` means the cache benefit of Workflow-tool
phases is identical to the NL-lead path adversarial skills already use, while
re-platforming would lose the lead's natural-language orchestration. This is a
confirmed no-op. Adversarial skills stay on the NL-lead path.

## Subdirectories

| Directory | What                                                                   | When to read                                                 |
| --------- | ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| `probe/`  | Environment-capability probes with captured `*_result.json` outputs   | Understanding runtime assumptions (A1–A4), reviewing probe results |
