# skills/

Agent workflows implemented on two native runtimes: the Workflow tool (`workflow.mjs`) for linear skills and Agent Teams (`team.md`) for adversarial skills.

## MANDATORY: Read Before Modifying Python Files

**STOP. Before editing ANY Python file in `skills/scripts/`, you MUST read `README.md`.**

The README defines:

- File section ordering (SHARED PROMPTS -> CONFIGURATION -> MESSAGE TEMPLATES -> MESSAGE BUILDERS -> STEP DEFINITIONS -> OUTPUT FORMATTING -> ENTRY POINT)
- Step-delimited prompt organization within MESSAGE TEMPLATES
- Naming conventions for prompt constants (`[PHASE]_[TYPE]`)
- Patterns for dispatch prompts (static templates vs builder functions)
- Anti-patterns to avoid (action factories, forward references)

Failure to follow these patterns creates technical debt and inconsistency across skills. The patterns exist because they solve real problems with prompt readability and maintenance.

**Read `README.md` now if you haven't already.**

## Files

| File        | What                                                      | When to read                    |
| ----------- | --------------------------------------------------------- | ------------------------------- |
| `README.md` | File organization, prompt patterns, naming, anti-patterns | BEFORE modifying any skill code |

## Subdirectories

| Directory             | What                                      | When to read                             |
| --------------------- | ----------------------------------------- | ---------------------------------------- |
| `scripts/`            | Python package root for all skill code    | Executing non-ported skills, debugging   |
| `planner/`            | Planning and execution workflows          | Creating implementation plans            |
| `refactor/`           | Refactoring analysis across dimensions    | Technical debt review, code quality      |
| `problem-analysis/`   | Structured problem decomposition          | Understanding complex issues             |
| `decision-critic/`    | Decision stress-testing and critique      | Validating architectural choices         |
| `deepthink/`          | Structured reasoning for open questions   | Analytical questions without frameworks  |
| `codebase-analysis/`  | Systematic codebase exploration           | Repository architecture review           |
| `prompt-engineer/`    | Prompt optimization and engineering       | Improving agent prompts                  |
| `incoherence/`        | Consistency detection                     | Finding spec/implementation mismatches   |
| `doc-sync/`           | Documentation synchronization             | Syncing docs across repos                |
| `leon-writing-style/` | Style-matched content generation          | Writing content matching user's style    |
| `arxiv-to-md/`        | arXiv paper to markdown conversion        | Converting papers for LLM consumption    |
| `cc-history/`         | Claude Code conversation history analysis | Querying past conversations, token usage |

## Native Runtimes (ported skills)

Ten skills have been ported from the Python `--step` CLI to native runtimes (M-006/M-006.5/M-007):

**Linear skills — Workflow tool** (`skills/<name>/workflow.mjs`):

| Skill               | Entry point                            |
| ------------------- | -------------------------------------- |
| codebase-analysis   | `skills/codebase-analysis/workflow.mjs` |
| refactor            | `skills/refactor/workflow.mjs`          |
| planner             | `skills/planner/workflow.mjs`           |
| arxiv-to-md         | `skills/arxiv-to-md/workflow.mjs`       |
| incoherence         | `skills/incoherence/workflow.mjs`       |
| prompt-engineer     | `skills/prompt-engineer/workflow.mjs`   |
| leon-writing-style  | `skills/leon-writing-style/workflow.mjs`|

**Adversarial skills — Agent Teams** (`skills/<name>/team.md`), with Workflow+Agent-tool fallback when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is unset:

| Skill            | Entry point                         |
| ---------------- | ----------------------------------- |
| decision-critic  | `skills/decision-critic/team.md`    |
| deepthink        | `skills/deepthink/team.md`          |
| problem-analysis | `skills/problem-analysis/team.md`   |

Durable phase-boundary events are written under `skills/scripts/skills/lib/workflow/persistence/` on both paths.

## Non-ported skills (Python CLI still active)

`doc-sync` and `cc-history` still use the Python `--step` runtime. See each skill's `SKILL.md` for invocation.
