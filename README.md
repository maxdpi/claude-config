# My Claude Code Workflow

> **This is a fork of [solatis/claude-config](https://github.com/solatis/claude-config).**
> It keeps the upstream philosophy (planning before execution, context hygiene,
> review cycles) but re-platforms the entire skills suite onto Claude Code's
> **native orchestration runtimes** — the Workflow tool and Agent Teams — and adds
> a **durable, cross-session skill-run persistence substrate**. Original credit for
> the philosophy and the first generation of skills goes to the upstream author.

This repo is a configuration directory for [Claude Code](https://claude.com/claude-code).
It installs a suite of **skills** (multi-phase agent workflows), a roster of
**subagents** (specialized leaf workers), a set of **slash commands**, shared
**conventions**, and a persistence layer that lets long-running skill runs survive
crashes, `/clear`, and session exit.

The rest of this document is a **reference for everything this config exposes**:
every skill (and which runtime drives it), every subagent, every command, and the
substrate that ties them together. For the design philosophy behind the workflow,
jump to [Philosophy](#philosophy).

---

## Contents

- [Mental Model: Skills, Workflows, Teams, Subagents](#mental-model-skills-workflows-teams-subagents)
- [Skill Reference](#skill-reference)
  - [Linear workflow skills](#linear-workflow-skills-workflow-tool)
  - [Adversarial team skills](#adversarial-team-skills-agent-teams)
  - [Interactive & utility skills](#interactive--utility-skills)
- [Subagent Reference](#subagent-reference)
- [Slash Commands](#slash-commands)
- [The Durable Substrate](#the-durable-substrate)
- [Installation & Configuration](#installation--configuration)
- [Philosophy](#philosophy)
- [Repository Layout](#repository-layout)

---

## Mental Model: Skills, Workflows, Teams, Subagents

Four concepts, layered:

| Concept | What it is | How it runs |
| --- | --- | --- |
| **Skill** | A named, invocable capability (`Use your <name> skill…` or `/<name>`). The unit you reach for. | Backed by either a workflow or a team. |
| **Workflow** | A *linear/staged* skill: deterministic JS (`workflow.mjs`) that drives phases through the **Workflow tool**, fanning out to subagents. | Workflow tool; journal-based, same-session resume. |
| **Team** | An *adversarial/divergent* skill: the **lead** (your main session) reads a `SKILL.md` and orchestrates **teammates** in natural language via **Agent Teams**. | Agent Teams (env-gated); degrades to Agent-tool subagents when disabled. |
| **Subagent** | A specialized leaf worker (`agents/*.md`) with its own model, tools, and system prompt. Workflows and teams both dispatch to these. | Spawned per task; ephemeral, report-back only. |

The split that matters most: **a skill is either a Workflow or a Team.**

- A skill backed by a `workflow.mjs` is a **Workflow skill** — its control flow is
  code: fixed phases, parallel fan-out, pipelines. Good when the *shape* of the work
  is known in advance (survey → deepen → synthesize).
- A skill backed only by a `SKILL.md` orchestration prompt is a **Team skill** — its
  control flow is the lead reasoning in natural language, spawning teammates,
  reading their findings, and adapting. Good when the work is *adversarial or
  divergent* (generate competing hypotheses, critique, synthesize a verdict).

> **Note on the dual presence:** Several Workflow skills ship *both* a `SKILL.md`
> (the front-door description + invocation contract) and a `workflow.mjs` (the
> deterministic backend). The `SKILL.md` is the entry point; the `.mjs` is what
> actually executes the phases.

Both runtimes emit identical **durable events** to the substrate, so
[resume](#the-durable-substrate) works the same regardless of which one drives a skill.

---

## Skill Reference

Invoke any skill conversationally (`Use your refactor skill on src/`) or, where a
slash command exists, with `/<name>`. Skills marked **"Invoke IMMEDIATELY"** in their
description should be launched *before* exploring — the skill itself orchestrates the
exploration.

### Linear workflow skills (Workflow tool)

These run `workflow.mjs` on the Workflow tool. Each declares a `phases` list and a
`phaseTrust` table (which phases are `read_only` vs `write`/`execute`) — the table is
the single source of truth the resume engine uses to decide what to auto-replay.

#### `planner` — plan then execute, with review gates

The centerpiece. Interactive planning and execution for complex tasks. It never
writes code directly; it delegates to subagents and runs every milestone through
review before the next begins.

- **Phases:** `intake-gather → intake-deepen → intake-summarize → plan-design → plan-code → plan-docs` (each plan phase paired with a `-qr` quality-review pass) `→ execute → exec-review → milestone-validate / -plan / -outcome / -propagate`. Initiative mode adds upstream `core-flows` and `tech-plan` phases.
- **Subagents:** `developer` (implementation), `technical-writer` (docs/clarity), `quality-reviewer` (completeness/risk), `architect`/`debugger` as needed.
- **Use it for:** any non-trivial change. Write the plan, `/clear`, then execute.
- **Invoke:** `Use your planner skill to write a plan to plans/feature.md` · `…to execute plans/feature.md` · `argument-hint: [task] [plan|execute|milestones]`

#### `codebase-analysis` — understand a codebase

Systematic, orchestrated exploration for architecture comprehension and repository
orientation. **Comprehension only** — for code-quality judgments use `refactor`; for
single-file bug hunts use the `debugger`.

- **Phases:** `scope → survey → deepen → synthesize`
- **Use it for:** "how does this work / how is it structured" on an unfamiliar or large surface.
- **Invoke:** `Use your codebase analysis skill to explore <path/topic>`

#### `refactor` — find technical debt

Explores code-quality dimensions in parallel (naming, extraction, types, errors,
modules, architecture, abstraction), validates findings against evidence, and outputs
**prioritized recommendations**. It does not write code — it tells you what to fix and
why. **Improvement judgments only** — for neutral orientation use `codebase-analysis`.

- **Phases:** `mode_selection → dispatch → triage → cluster → contextualize → synthesize`
- **Invoke:** `Use your refactor skill on src/services/` (optionally `-- focus on <area>`)

#### `incoherence` — do docs and code agree?

Detects and resolves contradictions between an implementation and its stated intent
(docs, specs, comments). A broad sweep followed by targeted deep dives and a resolution pass.

- **Phases:** `survey → dimension_select → broad_sweep → synthesize_candidates → deep_dive → verdict_analysis → resolution → application → report`
- **Invoke:** `Use your incoherence skill to check whether the docs match the code in <area>`

#### `prompt-engineer` — optimize prompts

Analyzes prompts, proposes changes with explicit pattern attribution, and **waits for
approval** before applying. Useful for tuning subagent definitions and skill prompts.
(This skill was optimized using itself.)

- **Phases:** `triage → assess → plan → draft → refine → approve → execute`
- **Invoke:** `Use your prompt engineer skill to optimize agents/developer.md`

#### `arxiv-to-md` — papers to markdown

Converts arXiv papers into LLM-consumable markdown. Also syncs a folder of PDFs to a
markdown destination.

- **Phases:** `discover → convert → finalize`
- **Invoke:** `Use your arxiv-to-md skill on <arXiv ID/URL>` (or `/arxiv-to-md`)

#### `leon-writing-style` — style-matched writing

A staged writing workflow (new in this fork) that *generates* content matched to a
voice rather than analyzing it, with explicit AI-tell detection and voice-consistency checks.

- **Phases:** `content_classification → purpose_audience → draft → ai_tells_detection → positive_markers → structural_metrics → voice_consistency → refinement → final_review`
- **Invoke:** `Use your leon-writing-style skill to draft <content>`

### Adversarial team skills (Agent Teams)

These run with **no `workflow.mjs`** and **no `team.md`**. The lead reads `SKILL.md`
and orchestrates teammates in natural language. Gated on
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`: when set, workers are Agent Teams teammates;
when unset, they degrade gracefully to Agent-tool subagents. Resume semantics are
identical in both modes.

#### `deepthink` — structured divergent reasoning

The most-reached-for skill for open-ended analytical questions where you don't yet know
what shape the answer takes — trade-offs, taxonomy design, evaluative judgments,
strategy comparison, architecture decisions. The lead clarifies context, designs
sub-questions, dispatches divergent reasoners, then synthesizes a **confidence-rated**
answer through agreement patterns.

- **Worker roles:** divergent-reasoners × 3 (`researcher`)
- **Invoke:** `Use your deepthink skill to think through <question>`

#### `decision-critic` — stress-test a decision

Adversarial critique of a specific decision or claim. The lead spawns workers to attack
it from independent angles, then synthesizes a verdict.

- **Worker roles:** verifier (`quality-reviewer`), challenger (`researcher`)
- **Invoke:** `Use your decision-critic skill on <decision or claim>`

#### `problem-analysis` — root-cause analysis

Identifies root causes via competing hypotheses and iterative investigation. The lead
gates the problem, forms hypotheses, dispatches investigators to gather evidence, then
formulates the root cause.

- **Worker roles:** investigators × N (`researcher`)
- **Invoke:** `Use your problem analysis skill to find why <symptom>`

**Choosing among the three:** `deepthink` is the general analytical front door (no
fixed answer structure). Reach for `problem-analysis` when the question is specifically
*why is this broken*, and `decision-critic` when you have a *specific decision* to
pressure-test.

### Interactive & utility skills

#### `discovery` — open-ended exploration front door

Single-phase interactive **frame loop** for thinking out loud — feature-design
questions, bug hunts, troubleshooting, general Q&A. It refuses nothing, **parks after
every turn** awaiting your input, and **never auto-advances** to a structured workflow.
The escape hatch when you don't want to commit to a skill yet; negotiate an exit when ready.

- **Invoke:** `/discovery <topic>` or `Use your discovery skill`

#### `curation` — propose durable memory (human-approved)

Deliberate cross-run learning. The lead runs a batch loop: inventory candidate
learnings, self-critique each draft against the memory-entry gate, propose, and write
**only what you approve**. Nothing is written to memory silently.

- **Invoke:** `Use your curation skill` · `argument-hint: [postmortem | review | document <source> | bootstrap]`

#### `doc-sync` — synchronize documentation

Audits and synchronizes the CLAUDE.md / README.md hierarchy across a repository so
indexes and per-directory docs stay consistent with the file tree. Primarily for
bootstrapping the workflow on an existing repo or recovering after a large refactor.
(If you use `planner` consistently, `technical-writer` keeps docs in sync as part of execution.)

- **Invoke:** `Use your doc-sync skill to synchronize documentation across this repository`

#### `cc-history` — query conversation history

Queries and analyzes Claude Code conversation history (`~/.claude/projects`) — past
sessions, token usage, tool calls, message timelines.

- **Invoke:** `Use your cc-history skill to <question about past sessions>`

---

## Subagent Reference

Subagents (`agents/*.md`) are the leaf workers that skills dispatch to. Each carries
its own model, tool allowlist, and system prompt. **Leaf workers carry
`disallowedTools: Agent`** so a spawned worker cannot itself spawn — the spawn surface
is constrained entirely by native primitives, not by prose guards.

| Subagent | Model | Role | Notable config |
| --- | --- | --- | --- |
| `architect` | Opus 4.8 | Understands architecture, conventions, designs quality solutions | `permissionMode: plan`, `effort: high`, read-only tools |
| `developer` | Sonnet 4.6 | Implements specs with tests — the only writer of code | `isolation: worktree` |
| `debugger` | Sonnet 4.6 | Analyzes bugs through systematic evidence gathering | `memory: project` |
| `quality-reviewer` | Sonnet 4.6 | Reviews code/plans for production risk, conformance, structure | `memory: project` |
| `technical-writer` | Sonnet 4.6 | Documentation optimized for LLM consumption; enforces token budgets | — |
| `researcher` *(new)* | Sonnet 4.6 | Read-only adversarial critique, divergent reasoning, investigation | read-only tools |
| `scout` | Haiku 4.5 | Cheap read-only investigator for narrow questions — casts wide, reports signal-dense | read-only tools |

Model assignment follows cost-effective delegation: Haiku (`scout`) for cheap wide
casts, Sonnet for the bulk of implementation/review, Opus (`architect`) reserved for
genuine architectural ambiguity.

---

## Slash Commands

| Command | What it does |
| --- | --- |
| `/discovery <topic>` | Enter the open-ended exploration frame loop (routes to the `discovery` skill). |
| `/runs` | List all durable skill runs from the registry as a table (no arguments). |
| `/run-status <id>` | Show state and projection for one run. |
| `/resume <id>` | Phase-aware resume with a default-deny consent gate. |

A `SessionStart` hook also surfaces resumable runs automatically and prunes terminal
runs past the retention TTL.

---

## The Durable Substrate

Claude Code's native runtimes orchestrate well but share one gap: **`resumeFromRunId`
is same-session only**. A run that crashes, a session that exits, or a script edited
mid-flight loses all progress. This fork's answer is a **thin durable store around the
native runtimes** — not a new orchestrator. Runtimes drive execution; the substrate
only *records* it and *replays* it.

```
Native runtimes (Workflow tool / Agent Teams / subagents)
        │  Task/Teammate/SubagentStop events (hooks, mirror OUT)
        ▼
Hook adapters  ──normalize──▶  events.jsonl  (append-only, O_APPEND atomic)
                                    │  replay
                                    ▼
                              pure fold  ──▶  projection.json + run-state.json
                                    ▲                    │  (atomic tmp+rename)
        /runs · /run-status · /resume <id>  ────read─────┘
```

### Run directory layout

```
~/.claude/skill-runs/<run_id>/
    run-state.json    — static metadata (run_id, skill, started_at, status)
    events.jsonl      — append-only event log
    projection.json   — latest folded projection (pure fold over events)
    manifest.json     — phase tag table (read_only / write / execute per phase)
    .lock             — advisory flock file
```

`run_id` is `<ISO-timestamp>-<8-char-uuid4>` (sortable, collision-safe). The store
lives **outside** the runtime-owned dirs (`~/.claude/teams`, `~/.claude/tasks`) that
the runtime overwrites while live and reaps on session end; the substrate treats those
as read-only-while-live and copies state *outward* through hook events.

### Key invariants

- **File-boundary:** LLM-facing agents write `.md` only; the substrate is the sole
  writer of `.json`.
- **Atomic writes:** every `.json` is written tmp-then-`os.rename`; concurrent same-run
  appends are serialized by an advisory `flock` around append → fold → projection-rewrite.
- **Pure, forward-compatible fold:** unknown event types/fields are ignored, so
  evolving (experimental) runtime hooks never break replay.
- **Retention:** prune only `done`/tombstoned runs past the TTL; keep
  crashed/incomplete runs forever — those are precisely the resumable ones.

### Phase-aware resume

`/resume` does **not** blindly replay. Each skill's `phaseTrust` table (or the team
task graph) tags phases `read_only | write | execute`. On resume the engine:

- **auto-replays** `read_only`/planning phases, and
- **requires explicit confirmation** before any `write`/`execute` phase (default-deny
  for any untagged phase).

For Agent Teams it never rehydrates dead teammates — it re-spawns a **fresh team
scoped to the remaining tasks** reconstructed from the durable task graph.

> **Sharp edge it handles:** native `permissionMode` enforces read-only phases, but a
> permissive parent session (`bypassPermissions`/`acceptEdits`/`auto`) overrides a
> child's `plan` mode. When that happens, the engine drops to full default-deny (every
> phase needs confirmation) and `/resume` warns you.

The full decision log (DL-001..DL-026) lives in
[`PERSISTENCE-PLAN.md`](PERSISTENCE-PLAN.md), [`plan/`](plan/), and
[`skills/README.md`](skills/README.md).

---

## Installation & Configuration

Clone the fork into your Claude Code configuration directory:

```bash
# Per-project
git clone https://github.com/jeanbrazeau/claude-config .claude

# Global (new setup)
git clone https://github.com/jeanbrazeau/claude-config ~/.claude

# Global (existing ~/.claude)
cd ~/.claude
git remote add workflow https://github.com/jeanbrazeau/claude-config
git fetch workflow && git merge workflow/main --allow-unrelated-histories
```

If you clone elsewhere, install the tracked config dirs into `~/.claude` with the
included installer (`rsync --delete`):

```bash
./sync.sh
```

The substrate is wired through hooks in `settings.json`, which expect the Python
helpers at `~/.claude/skills/scripts/`. After a global install the hooks fire
automatically — no extra setup. Run the substrate test suite with:

```bash
PYTHONPATH=skills/scripts python3 -m pytest tests/ -q
```

### Configuration knobs (`settings.json`)

| Key | Default | What |
| --- | --- | --- |
| `skillRuns.baseDir` | `~/.claude/skill-runs` | Where runs are stored. |
| `skillRuns.retentionDays` | `7` | TTL for **done** runs only; crashed/incomplete runs are kept indefinitely. |
| `skillRuns.copyTranscript` | `true` | Copy the native subagent transcript into the run dir on `SubagentStop`. |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | unset | Opt into Agent Teams for the adversarial skills; unset degrades them to Agent-tool subagents. |

**Wired hooks:** `SessionStart`, `Stop`, `SessionEnd`, `SubagentStart`,
`SubagentStop`, `TaskCreated`, `TaskCompleted`, `TeammateIdle` — these mirror runtime
state *out* into the substrate.

---

## Philosophy

LLM-assisted code rots faster than hand-written code: technical debt accumulates
because the LLM cannot see it and you are moving too fast to notice. This config treats
that as an engineering problem. Four principles:

- **Context hygiene.** Each task gets precisely the information it needs — no more.
  A two-file pattern in every directory: minimal `CLAUDE.md` indexes that load
  automatically, and `README.md`s holding invisible knowledge (architecture, invariants)
  read only when a trigger says to. The `technical-writer` enforces token budgets
  (~200 tokens for CLAUDE.md, ~500 for README.md).
- **Planning before execution.** LLMs make first-shot mistakes, always. Separating
  planning from execution forces ambiguities to surface when they are cheap to fix.
  Plans are written to files, so reasoning survives a `/clear`.
- **Review cycles.** Execution is split into milestones, each validated individually.
  A `technical-writer` checks clarity; a `quality-reviewer` checks completeness. No
  milestone starts until the previous passes.
- **Cost-effective delegation.** The orchestrator delegates to smaller models
  (Haiku/Sonnet) with just-in-time prompts, escalating to Opus only for genuine ambiguity.

**The canonical loop for non-trivial work:** explore (`codebase-analysis`) → think
(`deepthink`) → plan (`planner` write) → `/clear` → execute (`planner` execute).

---

## Repository Layout

| Directory | What |
| --- | --- |
| `skills/` | Skill definitions: linear `workflow.mjs` (Workflow tool) + adversarial `SKILL.md` (Agent Teams), plus the Python substrate tree under `scripts/`. |
| `agents/` | Subagent definitions (developer, quality-reviewer, researcher, …). |
| `commands/` | Slash commands (`discovery`, `resume`, `runs`, `run-status`). |
| `conventions/` | Universal doc/code-quality conventions for agents and skills. |
| `output-styles/` | Output-style definitions. |
| `plan/` | Multi-wave implementation plan for the orchestration tier. |
| `docs/` | Platform assumptions + vendored official Claude Code docs (~150 files). |
| `tests/` | pytest suite for the persistence/orchestration substrate. |
| `settings.json` | Harness config: skill-runs substrate, hooks, permissions. |
| `sync.sh` | Installs the config dirs into `~/.claude` via `rsync --delete`. |
| `PERSISTENCE-PLAN.md` | Design plan + decision log (DL-*) for the durable substrate. |

For per-skill internals see each skill's `README.md`; for the substrate design see
[`skills/README.md`](skills/README.md) and [`PERSISTENCE-PLAN.md`](PERSISTENCE-PLAN.md).
