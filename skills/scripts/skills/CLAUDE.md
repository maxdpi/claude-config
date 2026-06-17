# skills/

Python package root for all skill implementations. Substantive packages have their own `CLAUDE.md`; stub packages contain only `__init__.py`.

## Files

| File          | What                                                  | When to read                       |
| ------------- | ----------------------------------------------------- | ---------------------------------- |
| `__init__.py` | Package marker with one-line module comment           | -                                  |

## Subdirectories — substantive

| Directory | What                                                              | When to read                                            |
| --------- | ----------------------------------------------------------------- | ------------------------------------------------------- |
| `hooks/`  | Claude Code hook entrypoints (session start/end, subagent events) | Modifying hook behavior, debugging hook dispatch        |
| `lib/`    | Shared utilities and workflow orchestration framework             | Adding skills, modifying step handling, importing types |
| `planner/` | Planning and execution workflows with QR gates and TW passes     | Creating/executing plans, modifying planner phases      |
| `refactor/` | Package stub for refactor skill (ported to native runtime)      | Importing refactor package                              |

## Subdirectories — stubs (only `__init__.py`)

| Directory           | What                                           | When to read                              |
| ------------------- | ---------------------------------------------- | ----------------------------------------- |
| `arxiv_to_md/`      | Stub — skill ported to `skills/arxiv-to-md/workflow.mjs`    | -                          |
| `codebase_analysis/` | Stub — skill ported to `skills/codebase-analysis/workflow.mjs` | -                        |
| `decision_critic/`  | Stub — skill uses `skills/decision-critic/SKILL.md` (adversarial) | -                      |
| `deepthink/`        | Stub — skill uses `skills/deepthink/SKILL.md` (adversarial)  | -                          |
| `doc_sync/`         | Stub — skill still uses Python CLI (`doc-sync/SKILL.md`)     | -                          |
| `incoherence/`      | Stub — skill ported to `skills/incoherence/workflow.mjs`     | -                          |
| `leon_writing_style/` | Stub — skill ported to `skills/leon-writing-style/workflow.mjs` | -                       |
| `problem_analysis/` | Stub — skill uses `skills/problem-analysis/SKILL.md` (adversarial) | -                      |
| `prompt_engineer/`  | Stub — skill ported to `skills/prompt-engineer/workflow.mjs` | -                           |
