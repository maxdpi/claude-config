---
name: deepthink
description: Invoke IMMEDIATELY via Agent Teams (or Workflow tool fallback) when user requests structured reasoning for open-ended analytical questions. Do NOT explore first - the team orchestrates the thinking workflow.
---

# DeepThink

When this skill activates, IMMEDIATELY launch the Agent Team. The team IS the entry point.

## Invocation

### Primary path (Agent Teams enabled)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is set, launch an Agent Team from `skills/deepthink/team.md`. Pass the user's analytical question as the input.

The team runs structured multi-perspective reasoning (lead + adversarial teammates).

### Fallback path (Agent Teams unset)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is unset, invoke the Workflow tool with `skills/deepthink/workflow.mjs` + Agent-tool subagents. The same durable phase-boundary events are emitted on both paths.

Do NOT explore or analyze first. Launch the team (or workflow) and follow its output.
