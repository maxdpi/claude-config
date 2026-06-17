---
name: planner
description: Interactive planning and execution for complex tasks. IMMEDIATELY invoke when user asks to use planner.
argument-hint: [task] [plan|execute]
arguments: [task, mode]
---

## Activation

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

| Mode      | Intent                             | Workflow script                              |
| --------- | ---------------------------------- | -------------------------------------------- |
| planning  | "plan", "design", "architect"      | `skills/planner/workflow.mjs` with `mode: plan`    |
| execution | "execute", "implement", "run plan" | `skills/planner/workflow.mjs` with `mode: execute` |

Invoke the Workflow tool with the script at `skills/planner/workflow.mjs`. Pass the user's request and the resolved mode as `args`.
