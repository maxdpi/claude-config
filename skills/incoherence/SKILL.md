---
name: incoherence
description: Detect and resolve incoherence in documentation, code, specs vs implementation.
---

# Incoherence Detector

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

## Invocation

Invoke the Workflow tool with the script at `skills/incoherence/workflow.mjs`. Pass the user's request (scope, context, or target files) as `args`.

The workflow drives all phases natively.

Do NOT explore or detect first. Invoke the workflow and follow its phases.

## Workflow Phases

1. **Detection**: Survey codebase, explore dimensions, verify candidates
2. **Resolution**: Present issues via AskUserQuestion, collect user decisions
3. **Application**: Apply resolutions, present final report

Resolution is interactive - user answers structured questions inline. No manual file editing required.
