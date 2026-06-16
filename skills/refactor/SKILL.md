---
name: refactor
description: Invoke IMMEDIATELY via the Workflow tool when user requests refactoring analysis, technical debt review, or code quality improvement. Do NOT explore first - the workflow orchestrates exploration.
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
