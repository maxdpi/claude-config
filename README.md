# My Claude Code Workflow

> **This is a fork of [solatis/claude-config](https://github.com/solatis/claude-config).**
> It keeps the upstream philosophy (planning before execution, context hygiene,
> review cycles) but re-platforms the entire skills suite onto Claude Code's
> **native orchestration runtimes** and adds a **durable, cross-session skill-run
> persistence substrate**. See [What This Fork Changes](#what-this-fork-changes)
> for the full list. Original credit for the philosophy and the first generation
> of skills goes to the upstream author.

I use Claude Code for most of my work. After months of iteration, I noticed a
pattern: LLM-assisted code rots faster than hand-written code. Technical debt
accumulates because the LLM does not know what it does not know, and neither do
you until it is too late.

This repo is my solution: skills and workflows that force planning before
execution, keep context focused, and catch mistakes before they compound.

## What This Fork Changes

Upstream orchestrated multi-phase skills through a Python CLI runtime: each skill
re-invoked itself with `--step N`, and a `subagent.py` emitted prose dispatch
directives to coordinate fan-out. That re-invocation loop was the *only* thing
giving skills cross-session durability. This fork removes that runtime entirely
and rebuilds the capability on native primitives. The high-level changes:

- **Native-runtime port of all 10 skills.** Linear/staged skills
  (`codebase-analysis`, `refactor`, `planner`, `arxiv-to-md`, `incoherence`,
  `prompt-engineer`, `leon-writing-style`) now run on the **Workflow tool**
  (`workflow.mjs`); divergent/adversarial skills (`decision-critic`, `deepthink`,
  `problem-analysis`) now run on **Agent Teams** (`SKILL.md`). The Python `--step`
  CLI, the `--step` re-invocation loop, and the `subagent.py` dispatch-prose
  machinery are deleted.
- **Durable skill-run persistence substrate.** A thin external store at
  `~/.claude/skill-runs/<run_id>/` (append-only `events.jsonl` → pure fold →
  `projection.json` + `run-state.json`, all atomic writes) records native runtime
  state and survives crashes, `/clear`, and session exit — the cross-session
  resume the native runtimes lack on their own.
- **Run-management slash commands:** `/runs`, `/run-status <id>`, and a
  phase-aware `/resume <id>` with a default-deny consent gate.
- **`settings.json` hook wiring** that mirrors runtime state *out* into the
  substrate (`SessionStart`/`Stop`/`SessionEnd`, `SubagentStart`/`SubagentStop`,
  `TaskCreated`/`TaskCompleted`/`TeammateIdle`).
- **Agent Teams bridge** that captures Agent Teams runs into the substrate, with
  graceful degradation to Workflow tool + subagents when Agent Teams is disabled.
- **New skill** `leon-writing-style` and a new **`researcher`** subagent.
- **Vendored official Claude Code docs** (`docs/claude-code/`, ~150 files) plus a
  refresh script, so the suite can be built and reviewed against a pinned copy of
  the platform docs.
- **A pytest substrate test harness** (`tests/`) — persistence core, hook
  adapters, resume engine, port-parity fixtures, plus property and chaos layers.
- **19 per-directory `CLAUDE.md` indexes** added across the tree for context
  hygiene, and `sync.sh` for installing the config into `~/.claude`.

The sections below ("Why This Exists", "Principles", "Usage") describe the
inherited philosophy. The fork-specific machinery is detailed under
[Architecture: Native Runtimes + Durable Substrate](#architecture-native-runtimes--durable-substrate).

## Why This Exists

LLM-assisted coding fails long-term. Technical debt accumulates because the LLM
cannot see it, and you are moving too fast to notice. I treat this as an
engineering problem, not a tooling problem.

LLMs are tools, not collaborators. When an engineer says "add retry logic",
another engineer infers exponential backoff, jitter, and idempotency. An LLM
infers nothing you do not explicitly state. It cannot read the room. It has no
institutional memory. It will cheerfully implement the wrong thing with perfect
confidence and call it "production-ready".

Larger context windows do not help. Giving an LLM more text is like giving a
human a larger stack of papers; attention drifts to the beginning and end, and
details in the middle get missed. More context makes this worse. Give the LLM
exactly what it needs for the task at hand -- nothing more.

## Principles

This workflow is built on four principles.

### Context Hygiene

Each task gets precisely the information it needs -- no more. Sub-agents start
with a fresh context, so architectural knowledge must be encoded somewhere
persistent.

I use a two-file pattern in every directory:

**CLAUDE.md** -- Claude loads these automatically when entering a directory.
Because they load whether needed or not, content must be minimal: a tabular
index with short descriptions and triggers for when to open each file. When
Claude opens `app/web/controller.py`, it retrieves just the indexes along that
path -- not prose it might never need.

**README.md** -- Invisible knowledge: architecture decisions, invariants not
apparent from code. The test: if a developer could learn it by reading source
files, it does not belong here. Claude reads these only when the CLAUDE.md
trigger says to.

The principle is just-in-time context. Indexes load automatically but stay
small. Detailed knowledge loads only when relevant.

The technical writer agent enforces token budgets: ~200 tokens for CLAUDE.md,
~500 for README.md, 100 for function docs, 150 for module docs. These limits
force discipline -- if you are exceeding them, you are probably documenting what
code already shows. Function docs include "use when..." triggers so the LLM
knows when to reach for them.

The planner workflow maintains this hierarchy automatically. If you bypass the
planner, you maintain it yourself.

### Planning Before Execution

LLMs make first-shot mistakes. Always. The workflow separates planning from
execution, forcing ambiguities to surface when they are cheap to fix.

Plans capture why decisions were made, what alternatives were rejected, and what
risks were accepted. Plans are written to files. When you clear context and
start fresh, the reasoning survives.

### Review Cycles

Execution is split into milestones -- smaller units that are manageable and can
be validated individually. This ensures continuous, verified progress. Without
it, execution becomes a waterfall: one small oversight early on and agents
compound each mistake until the result is unusable.

Quality gates run at every stage. A technical writer agent checks clarity; a
quality reviewer checks completeness. The loop runs until both pass.

Plans pass review before execution begins. During execution, each milestone
passes review before the next starts.

### Cost-Effective Delegation

The orchestrator delegates to smaller agents -- Haiku for straightforward tasks,
Sonnet for moderate complexity. Prompts are injected just-in-time, giving
smaller models precisely the guidance they need at each step.

When quality review fails or problems recur, the orchestrator escalates to
higher-quality models. Expensive models are reserved for genuine ambiguity, not
routine work.

## Does This Actually Work?

I have not run formal benchmarks. I can only tell you what I have observed using
this workflow to build and maintain non-trivial applications entirely with
Claude Code -- backend systems, data pipelines, streaming applications in C++,
Python, and Go.

The problems I used to hit constantly are gone:

**Ambiguity resolution.** You ask an LLM "make me a sandwich" and it comes back
with a grilled cheese. Technically correct. Not what you meant. The planning
phase forces these misunderstandings to surface before you have built the wrong
thing.

**Code hygiene.** Without review cycles, the same utility function gets
reimplemented fifteen times across a codebase. The quality reviewer catches
this. The technical writer ensures documentation stays consistent.

**LLM-navigable documentation.** Function docs include "use when..." triggers.
CLAUDE.md files tell the LLM which files matter for a given task. The LLM stops
guessing which code is relevant.

Is it better than writing code by hand? I think so, but I cannot speak for
everyone. This workflow is opinionated. I am a backend engineer -- the patterns
should apply to frontend work, but I have not tested that. If you are less
experienced with software engineering, I would like to know whether this helps
or adds overhead.

If you are serious about LLM-assisted coding and want to try a structured
approach, give it a shot. I would like to hear what works and what does not.

## Quick Start

Clone the fork into your Claude Code configuration directory:

```bash
# Per-project
git clone https://github.com/jeanbrazeau/claude-config .claude

# Global (new setup)
git clone https://github.com/jeanbrazeau/claude-config ~/.claude

# Global (existing ~/.claude)
cd ~/.claude
git remote add workflow https://github.com/jeanbrazeau/claude-config
git fetch workflow
git merge workflow/main --allow-unrelated-histories
```

If you clone elsewhere, install the config dirs into `~/.claude` with the
included installer (it `rsync --delete`s the tracked directories into place):

```bash
./sync.sh
```

The skill-run substrate is wired through hooks in `settings.json`, which expect
the Python helpers at `~/.claude/skills/scripts/`. After installing globally the
hooks fire automatically; no extra setup is needed. The persistence/orchestration
substrate has its own test suite:

```bash
PYTHONPATH=skills/scripts python3 -m pytest tests/ -q
```

### Configuration

`settings.json` exposes the substrate knobs:

- `skillRuns.baseDir` — where runs are stored (default `~/.claude/skill-runs`).
- `skillRuns.retentionDays` — TTL for **done** runs only; crashed/incomplete runs
  are kept indefinitely (they are the resumable ones).
- `skillRuns.copyTranscript` — copy the native subagent transcript into the run
  dir on `SubagentStop` (default `true`); set `false` to rely solely on native
  transcripts.
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` — opt into Agent Teams mode for the
  adversarial skills. When unset, those skills degrade gracefully to the Workflow
  tool + Agent-tool subagents; resume semantics are identical in both modes.

## Usage

The workflow for non-trivial changes: explore -> plan -> execute.

**1. Explore the problem.** Understand what you are dealing with. Figure out the
solution.

This is relatively free-form. If the project and/or surface area is particularly
large, use the `codebase-analysis` skill to explore the project's code properly
before proposing a solution.

**2. (Optional) Think it through.** I reach for `deepthink` very often, more than
any other skill. It handles analytical questions where you do not know the answer
structure yet -- taxonomy design, trade-offs, definitional questions, evaluative
judgments, exploratory investigations.

It auto-detects complexity. Quick mode reasons directly. Full mode launches
parallel sub-agents with different analytical perspectives, then synthesizes
through agreement patterns. Both self-verify.

So, for most analytical questions, deepthink is enough. It explores your
codebase when context is missing. Reach for specialized skills only when the
question is clearly scoped:

- `problem-analysis`: Root cause analysis specifically
- `decision-critic`: Stress-testing a specific decision

**3. Write a plan.** "Use your planner skill to write a plan to
plans/my-feature.md"

The planner runs your plan through review cycles -- technical writer for
clarity, quality reviewer for completeness -- until it passes.

The planner captures all decisions, tradeoffs, and information not visible from
the code so that this context does not get lost.

**4. Clear context.** `/clear` -- start fresh. You have written everything
needed into the plan.

**5. Execute.** "Use your planner skill to execute plans/my-feature.md"

The planner delegates to sub-agents. It never writes code directly. Each
milestone goes through the developer, then the technical-writer and
quality-reviewer. No milestone starts until the previous one passes review.

Where possible, it executes multiple tasks in parallel.

For detailed breakdowns of each skill, see their READMEs:

- [DeepThink](skills/deepthink/README.md)
- [Codebase Analysis](skills/codebase-analysis/README.md)
- [Problem Analysis](skills/problem-analysis/README.md)
- [Decision Critic](skills/decision-critic/README.md)
- [Planner](skills/planner/README.md)

### In Practice

I needed to migrate a legacy C# Windows Service from print-based logging to
something that actually rotates files.

The codebase had a homegrown Log() method writing to a single file with
File.AppendAllText. No rotation, no log levels, synchronous I/O blocking the
thread. Six Console.WriteLine calls scattered elsewhere went nowhere when
running as a service.

I started with exploration and analysis in a single prompt:

```
Use your codebase analysis skill to briefly explore this C# project,
with a focus on all the places where debug logs are currently emitted.

Then use your problem analysis skill to think through an appropriate
logging framework:
 * must work with .NET Framework 4.8.1
 * must support log rotation out of the box
 * we run multiple processes on the same machine, so it needs structured
   multi-process support
```

The codebase analysis found 31 call sites and the Console.WriteLine leakage. The
problem analysis evaluated NLog, Serilog, log4net, and
Microsoft.Extensions.Logging against my constraints.

The recommendation was NLog. It handles rotation and async out of the box.
Multi-process support comes from layout variables. Serilog would work but
requires three packages for the same functionality.

I agreed with the recommendation. Not a complicated decision, so I skipped the
`decision-critic` and moved to planning:

```
Use your planner skill to write an implementation plan to: plan-logging.md
```

The planner surfaced two ambiguities:

1. Replace all Log() call sites, or just the implementation? Obvious to a human,
   but worth clarifying upfront.
2. Log rotation defaults. The planner assumed 1-day rotation, but I also need
   size-based rotation at 1GB.

The plan went through review. The technical writer flagged comments that
explained what rather than why -- the NLog.config had comments like "configures
file target" instead of explaining the rotation strategy. The quality reviewer
caught two issues I would have missed: no explicit LogManager.Shutdown() in the
service's OnStop() handler, and incorrect file paths missing the src/ prefix.

These are the bugs that ship to production when you skip review cycles. The
shutdown issue would have caused log loss on service restart. The path issue
would have failed silently.

After fixes, I cleared context and executed:

```
Use your planner skill to execute: @plan-logging.md
```

The developer, debugger, technical writer, and quality reviewer run the
implementation. Each milestone passes review before the next starts. If the
implementation deviated from the plan, I would know.

## Architecture: Native Runtimes + Durable Substrate

This is the largest change in the fork. Upstream's skills were driven by a Python
`--step` CLI that re-invoked itself between phases; that re-invocation was what
let a run survive a fresh session. Claude Code now ships native orchestration
primitives — the **Workflow tool** (deterministic JS, journal-based
`resumeFromRunId`, same-session only), **Agent Teams** (lead + teammates + shared
task list, experimental/env-gated, all state ephemeral), and **Agent-tool
subagents** (ephemeral, report-back only). All three execute orchestration well
but lack the one thing the Python loop provided: **cross-session durability and
resume**. A run that crashes, a session that exits, or a script edited mid-flight
loses all progress.

The fork's answer is a **thin durable substrate around the native runtimes** —
not a new orchestrator. Native runtimes drive execution; the substrate only
*records* it and *replays* it.

### How it works

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

Data flow is **one-directional**: runtimes → hooks → event log → fold →
projection. The store lives at `~/.claude/skill-runs/<run_id>/`, **outside** the
runtime-owned dirs (`~/.claude/teams`, `~/.claude/tasks`) that the runtime
overwrites while live and reaps on session end. The substrate treats those dirs
as read-only-while-live and copies state *outward* through hook events — it never
authors or edits them.

Key invariants (ported from the upstream "koan" persistence design):

- **File-boundary:** LLM-facing agents write `.md` only; the substrate is the
  sole writer of `.json`.
- **Atomic writes:** every `.json` is written tmp-then-`os.rename`, so concurrent
  readers never see torn state. Concurrent same-run appends are serialized by an
  advisory `flock` around the append→fold→projection-rewrite section.
- **Pure, forward-compatible fold:** the fold ignores unknown event types and
  fields, so evolving (experimental) runtime hooks don't break replay.
- **Retention:** prune only `done`/tombstoned runs past the TTL; keep
  crashed/incomplete runs forever — those are precisely the resumable ones.

### Resume is phase-aware

`/resume` does not blindly replay. Each skill declares its phases tagged
`read_only | write | execute` in a `manifest.json` written at run creation. On
resume the engine **auto-replays read-only/planning phases** but **requires
explicit confirmation before any write/execute phase** (default-deny for any
untagged phase). For Agent Teams it never tries to rehydrate dead teammates —
teammates are ephemeral — it re-spawns a **fresh team scoped to the remaining
tasks** reconstructed from the durable task graph.

One sharp edge it handles: native `permissionMode` is the enforcement mechanism
for read-only phases, but a permissive parent session
(`bypassPermissions`/`acceptEdits`/`auto`) overrides a child's `plan` mode. When
the parent mode overrides, the engine drops to full default-deny (every phase
needs confirmation) and `/resume` warns you.

The full decision log (DL-001..DL-026), constraints, and the wave-by-wave
implementation plan live in [`PERSISTENCE-PLAN.md`](PERSISTENCE-PLAN.md) and
[`plan/`](plan/).

## Run Management

The substrate is exposed through three slash commands:

| Command | What it does |
| --- | --- |
| `/runs` | List durable skill runs (no arguments). |
| `/run-status <id>` | Show state and projection for one run. |
| `/resume <id>` | Phase-aware resume with a default-deny consent gate. |

A `SessionStart` hook also detects incomplete runs and offers to resume them, and
prunes terminal runs past the retention TTL.

## Skills & Agents

**Skills** (`skills/`): `arxiv-to-md`, `cc-history`, `codebase-analysis`,
`decision-critic`, `deepthink`, `doc-sync`, `incoherence`, `leon-writing-style`
*(new in this fork)*, `planner`, `problem-analysis`, `prompt-engineer`,
`refactor`. Linear skills carry a `workflow.mjs` (Workflow tool); adversarial
skills carry a `SKILL.md` (Agent Teams).

**Subagents** (`agents/`): `architect`, `debugger`, `developer`,
`quality-reviewer`, `technical-writer`, and `researcher` *(new in this fork)*.
Leaf workers carry `disallowedTools: Agent` so a spawned worker cannot itself
spawn; the spawn surface is constrained entirely by native primitives
(`Agent(type)` allowlists and `permissions.deny`) rather than the removed Python
dispatch-prose guards.

## Vendored Docs & Tests

- **`docs/claude-code/`** — a mirrored, organized copy of the official Claude Code
  docs (~150 files) plus a refresh script, so skill ports can be built and
  reviewed against a pinned snapshot of the platform.
- **`tests/`** — a pytest suite for the substrate: persistence core, hook
  adapters, contract/registry/retention, resume engine, the Agent Teams bridge,
  Workflow/adversarial **port-parity fixtures** (proving each native port matches
  the retired Python behavior before deletion), plus property-based and chaos
  layers. Run with `PYTHONPATH=skills/scripts python3 -m pytest tests/ -q`.

## Other Skills

Not every task needs the full planning workflow. These skills handle specific
concerns.

### DeepThink

I use this skill multiple times a day -- whenever I do not know what shape the
answer should take.

Unlike `problem-analysis` or `decision-critic`, deepthink has no fixed
structure. It handles trade-offs, taxonomy questions, evaluative judgments --
whatever you throw at it.

So, when do I reach for it?

Meta-cognitive debugging. I keep making the same mistake. The LLM keeps
misunderstanding the task. Why? Something is broken and I need to see it before
I can fix it.

Strategy evaluation. Multiple valid approaches exist (and gut feel is not
enough). PDF conversion: download the TeX source, parse the PDF directly, or
let the LLM render it visually. S3 artifact versioning: timestamp paths,
pointer files, checksums. Systematic comparison beats intuition.

Best practices research. What is the canonical approach? How do mature CI/CD
systems handle artifact versioning? Industry patterns likely exist -- I just do
not know them yet.

Architecture and design. How should these components interact? Where do the
delegation boundaries go? I think them through before committing to code.

Consolidation decisions. Should these two skills be merged? Do they serve
distinct purposes, or am I maintaining unnecessary complexity?

Two modes, auto-detected. Quick mode reasons directly. Full mode launches
parallel sub-agents with distinct analytical perspectives, then synthesizes
through agreement patterns.

```
Use your deepthink skill to think through [question]
```

For explicit mode selection:

```
Use your deepthink skill (quick) to [question]
Use your deepthink skill (full) to [question]
```

### Refactor

LLM-generated code accumulates technical debt. The LLM does not see duplication
across files or notice god functions growing.

The refactor skill explores multiple dimensions in parallel -- naming,
extraction, types, errors, modules, architecture, abstraction -- validates
findings against evidence, and outputs prioritized recommendations. It does not
generate code; it tells you what to fix and why.

Use it when:

- After LLM-generated features work but feel messy
- Before major changes to identify friction points
- Code review reveals structural issues
- Simple changes require touching many files

```
Use your refactor skill on src/services/
```

With focus area:

```
Use your refactor skill on src/ -- focus on refactoring the rendering engine so that it can be reused in multiple components.
```

### Prompt Engineer

This workflow consists entirely of prompts. Each can be optimized individually.

The skill analyzes prompts, proposes changes with explicit pattern attribution,
and waits for your approval before applying anything.

Use it when:

- A sub-agent definition is not performing as expected
- Optimizing a skill's Python script prompts
- Reviewing a multi-prompt workflow for consistency

```
Use your prompt engineer skill to optimize the system prompt for agents/developer.md
```

The skill was optimized using itself.

### Doc Sync

The CLAUDE.md/README.md hierarchy requires maintenance. The structure changes
over time. Documentation drifts.

The doc-sync skill audits and synchronizes documentation across a repository.

Use it when:

- Bootstrapping the workflow on an existing repository
- After major refactors or directory restructuring
- Periodic audits to check for documentation drift

If you use the planning workflow consistently, the technical writer agent
handles documentation as part of execution. Doc-sync is primarily for
bootstrapping or recovery.

```
Use your doc-sync skill to synchronize documentation across this repository
```

For targeted updates:

```
Use your doc-sync skill to update documentation in src/validators/
```

### Leon Writing Style

New in this fork. A staged writing workflow that generates style-matched content
rather than analysis — it runs its phases on the Workflow tool like the other
linear skills.

```
Use your leon-writing-style skill to draft [content]
```
