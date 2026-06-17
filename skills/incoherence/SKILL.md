---
name: incoherence
description: Invoke IMMEDIATELY via the Workflow tool when the user asks to check whether documentation, specs, comments, and code agree — detecting and resolving contradictions between an implementation and its stated intent. Do NOT explore first; the workflow orchestrates the consistency analysis.
---

# Incoherence Detector

When this skill activates, IMMEDIATELY invoke the Workflow tool. The workflow IS the entry point.

## Invocation

Invoke the Workflow tool with the script at `skills/incoherence/workflow.mjs`. Pass the user's request (scope, context, or target files) as `args`.

The workflow drives all phases natively.

Do NOT explore or detect first. Invoke the workflow and follow its phases.

## Inputs (`args`)

Pass the scope to analyze: a directory, a set of target files, or a free-text
description of the area to check (e.g. "does the planner README match
workflow.mjs?"). With no `args`, the workflow scopes to the repository root.

## Workflow Phases

The workflow runs nine sub-phases, grouped into three trust tiers. Detection is
read-only; only Resolution and Application can change state.

**Detection (read-only):**

1. **survey** — map the codebase region in scope; identify intent sources (docs,
   specs, comments) vs. implementation.
2. **dimension_select** — choose which consistency dimensions to check (falls back
   to defaults A/C/I if selection JSON is malformed).
3. **broad_sweep** — parallel wide-net pass; recall over precision (Haiku workers).
4. **synthesize_candidates** — dedupe and cluster the raw candidate contradictions.
5. **deep_dive** — parallel precision verification of each candidate (Sonnet workers).
6. **verdict_analysis** — classify each confirmed issue:
   TRUE_INCOHERENCE / SIGNIFICANT_AMBIGUITY / DOCUMENTATION_GAP /
   SPECIFICATION_GAP / FALSE_POSITIVE.

**Resolution (write):**

7. **resolution** — present each confirmed incoherence via AskUserQuestion (batches
   of up to 4) and collect your decisions inline. No manual file editing required.

**Application (execute) + Report (read-only):**

8. **application** — apply the chosen resolutions to the affected files.
9. **report** — emit the final `verdicts` report (issues found, classifications,
   resolutions applied).

The two-phase broad_sweep → deep_dive design is deliberate: the sweep maximizes
recall and the deep dive supplies precision, so a wide candidate list is expected
before verification narrows it.
