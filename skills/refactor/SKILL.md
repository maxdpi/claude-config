---
name: refactor
description: Invoke IMMEDIATELY via the Workflow tool when user explicitly asks for code smells, technical debt, refactoring opportunities, or code-quality improvements. Do NOT explore first - the workflow orchestrates exploration. Boundary - use this when the ask is about what to improve/fix in the code; for general comprehension or architecture orientation (no quality judgment requested) use codebase-analysis instead.
---

# Refactor

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

## Invocation

Invoke the Workflow tool with the script at `skills/refactor/workflow.mjs`. Pass the user's request as `args`.

The workflow drives six phases natively (mode_selection → dispatch → triage → cluster → contextualize → synthesize).

## Determining N (category count)

Pass `n` in `args` to control how many code smell categories are explored (default: 10):

- SMALL (single file, specific concern, "quick look"): N = 5
- MEDIUM (directory, module, standard analysis): N = 10
- LARGE (entire codebase, "thorough", "comprehensive"): N = 25

The workflow randomly selects N categories from the 38 available code quality categories defined in conventions/code-quality/.
