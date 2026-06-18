# Core Flows: Frozen Behavioral Spec

What the core-flows artifact is, what it contains, and the rules that make it
useful as an independent stress-test surface for downstream structural design.
Referenced by `skills/planner/workflow.mjs` (mode: initiative, core-flows phase).
Ported from koan's core_flows phase.

## What the Artifact Is

The core-flows artifact is the **behavioral counterpart to the frozen brief**. It
describes how the initiative operates — actors, triggers, sequenced steps, and
exit conditions — at a level that contains no implementation detail. Every
downstream design and execution phase reads it as authoritative behavioral truth.

The artifact is **FROZEN at exit**. No downstream phase may rewrite it. A
downstream phase that discovers a behavioral error records that error in its own
Outcome or Decisions section; it does not edit core-flows.md.

## What Goes in Each Flow

For each operational flow the initiative introduces or modifies, the artifact
contains two load-bearing elements:

1. **One SEQ diagram** — a `sequenceDiagram` showing the actors, the sequence
   of interactions, and any branching conditions. Refer to the suppression rule
   in conventions/visualization.md before drawing: if the flow is below the SEQ
   threshold, write it as prose instead.
2. **A step narrative** — trigger (what starts the flow), sequenced steps
   (in prose or a numbered list), and exit conditions (what constitutes
   completion or failure).

## Strict Content Rules

These rules are what give core-flows its value as an independent stress-test
surface: a behavioral spec that structural design cannot contaminate.

| Rule | Detail |
| ---- | ------ |
| **SEQ only** | No CON, CMP, or STT diagrams. The artifact is behavior, not structure. |
| **No file paths** | File and module names are implementation detail. Omit them. |
| **No component names** | Service names, class names, and function names belong in the tech-plan. |
| **No implementation detail** | How something is built is out of scope. What happens and in what order is in scope. |
| **Actor names are roles** | Use role labels (User, System, External Service) not code identifiers. |

## Diagrams

The core-flows artifact uses the **SEQ slot only**. All rules for the SEQ slot —
suppression threshold, grounding rule, mermaid syntax hazards (semicolons in
Note bodies, multi-line Notes) — are defined in `conventions/visualization.md`
and apply here without modification. Do not restate thresholds or rules in this
artifact.

When the SEQ suppression threshold is not met (see visualization.md), write the
flow as prose instead of a diagram.

## Relationship to Other Artifacts

| Artifact | Relationship |
| -------- | ------------ |
| Frozen brief | Core-flows is the behavioral companion. The brief covers scope/decisions/constraints; core-flows covers how the initiative operates at runtime. |
| tech-plan.md | Core-flows is read BEFORE tech-plan is written. The tech-plan's structural choices must be consistent with the behavioral flows here. |
| Milestone specs | Each milestone plan reads core-flows to confirm the milestone's behavior is grounded in an established flow. |

## Referenced by

`skills/planner/workflow.mjs` (mode: initiative, core-flows phase).
