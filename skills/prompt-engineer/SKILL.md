---
name: prompt-engineer
description: Invoke IMMEDIATELY via the Workflow tool when user requests prompt optimization. Do NOT analyze first - invoke this skill immediately.
---

# Prompt Engineer

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

## Invocation

Invoke the Workflow tool with the script at `skills/prompt-engineer/workflow.mjs`. Pass the user's request as `args`, including any scope hint if already clear.

The workflow determines scope in its first phase (triage) and proceeds through optimization phases natively.

### Scopes

The workflow auto-detects one of:

- **single-prompt**: One prompt file, general optimization
- **ecosystem**: Multiple related prompts that interact
- **greenfield**: No existing prompt, designing from requirements
- **problem**: Existing prompt(s) with specific issue to fix

Do NOT analyze or explore first. Invoke the workflow and follow its phases.
