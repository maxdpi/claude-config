---
name: codebase-analysis
description: Invoke IMMEDIATELY via the Workflow tool when user requests codebase understanding, architecture comprehension, or repository orientation. Do NOT explore first - the workflow orchestrates exploration. Boundary - use this for comprehension ("how does this work / how is it structured"); for code-quality smells, technical debt, or improvement suggestions use refactor instead; for single-file bug investigation use the debugger.
---

# Codebase Analysis

Understanding-focused skill that builds foundational comprehension of codebase structure, patterns, flows, decisions, and context. Serves as foundation for downstream analysis skills (problem-analysis, refactor, etc.).

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

## Invocation

Invoke the Workflow tool with the script at `skills/codebase-analysis/workflow.mjs`. Pass the user's request as `args`.

The workflow drives four phases natively (Scope → Survey → Deepen → Synthesize).
