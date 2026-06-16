---
name: problem-analysis
description: Invoke IMMEDIATELY via Agent Teams (or Workflow tool fallback) when user requests problem analysis or root cause investigation. Do NOT explore first - the team orchestrates the investigation.
---

# Problem Analysis

Root cause identification skill. Identifies WHY a problem occurs, NOT how to fix it.

## Invocation

### Primary path (Agent Teams enabled)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is set, launch an Agent Team from `skills/problem-analysis/team.md`. Pass the problem description as the input.

The team drives structured root cause investigation (lead + adversarial teammates).

### Fallback path (Agent Teams unset)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is unset, invoke the Workflow tool with `skills/problem-analysis/workflow.mjs` + Agent-tool subagents. The same durable phase-boundary events are emitted on both paths.

Do NOT explore or analyze first. Launch the team (or workflow) and follow its output.
