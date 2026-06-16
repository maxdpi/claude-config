---
name: decision-critic
description: Invoke IMMEDIATELY via Agent Teams (or Workflow tool fallback) to stress-test decisions and reasoning. Do NOT analyze first - the team orchestrates the critique workflow.
---

# Decision Critic

When this skill activates, IMMEDIATELY launch the Agent Team. The team IS the entry point.

## Invocation

### Primary path (Agent Teams enabled)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is set, launch an Agent Team from `skills/decision-critic/team.md`. Pass the decision statement to critique as the input.

The team runs the 7-step adversarial critique methodology (lead + adversarial teammates).

### Fallback path (Agent Teams unset)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is unset, invoke the Workflow tool with `skills/decision-critic/workflow.mjs` + Agent-tool subagents. The same durable phase-boundary events are emitted on both paths.

Do NOT analyze or critique first. Launch the team (or workflow) and follow its output.
