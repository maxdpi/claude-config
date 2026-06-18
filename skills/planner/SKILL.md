---
name: planner
description: Interactive planning and execution for complex tasks. IMMEDIATELY invoke when user asks to use planner.
argument-hint: [task] [plan|execute|milestones]
arguments: [task, mode]
---

## Activation

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

| Mode       | Intent                                  | Workflow script                                       |
| ---------- | --------------------------------------- | ----------------------------------------------------- |
| plan       | "plan", "design", "architect"           | `skills/planner/workflow.mjs` with `mode: plan`       |
| execute    | "execute", "implement", "run plan"      | `skills/planner/workflow.mjs` with `mode: execute`    |
| milestones | "deliver", "milestone loop", "initiative" | `skills/planner/workflow.mjs` with `mode: milestones` |

Invoke the Workflow tool with the script at `skills/planner/workflow.mjs`. Pass the user's request and the resolved mode as `args`.

- **plan** runs intake (Gather → Deepen → Summarize) → design/code/docs with QR gates, and returns a `plan` artifact.
- **execute** turns an approved plan into code: per-wave executor dispatch over `code_changes` + an `exec-review` gate (rewrite-or-loop-back). Pass the plan via `args.plan` (object), `args.planPath`, or in the request text.
- **milestones** loops `plan → execute → exec-review` per milestone, accumulating each milestone's Outcome so the next milestone's planning builds on it (`conventions/milestones.md`).
