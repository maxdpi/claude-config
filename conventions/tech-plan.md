# Tech Plan: Structural Architecture and Dedicated Review

What the tech-plan artifact contains, the rules that govern it, and the
dedicated adversarial review that validates it before milestone decomposition.
Referenced by `skills/planner/workflow.mjs` (mode: initiative, tech-plan-spec
and tech-plan-review phases). Ported from koan's tech_plan_spec and
tech_plan_review phases.

## Part 1: Spec — What the Tech Plan Is

The tech-plan artifact is the **structural counterpart to core-flows.md**. Where
core-flows describes what the system does, tech-plan describes how it is built:
containers, modules, data shapes, and the relationships between them.

The artifact is **disposable**: its reviewer may rewrite it in place, and
milestone Outcomes eventually supersede it as the ground truth of what was
actually built. Do not treat it as frozen.
See `conventions/artifacts.md` for the disposable lifetime class definition and the full per-artifact lifecycle table.

### Prerequisites

Before writing the tech-plan, the architect MUST:
1. Read the frozen brief.
2. Read core-flows.md in full. The structural choices here must be consistent
   with the behavioral flows core-flows describes.

### Three Load-Bearing Sections

| Section | Diagram slot | Content |
| ------- | ------------ | ------- |
| **Architectural Approach** | CON (container view) | Runtime building blocks (services, stores, queues, external systems) and their connections. Apply the CON suppression rule from conventions/visualization.md. |
| **Data Model** | Fenced code blocks (schema notation) | Data shapes — structs, schemas, message envelopes. NOT ER diagrams; fenced code blocks only. |
| **Component Architecture** | CMP per container; SEQ for cross-component flows; STT for per-entity lifecycles where warranted | Internal structure of each container. Apply suppression rules from conventions/visualization.md. |

All diagram rules — slot types, suppression thresholds, grounding rule,
level-separation rule, mermaid syntax hazards — are defined in
`conventions/visualization.md` and apply here without modification. Do not
restate thresholds or rules in this artifact.

### Strict Content Rules

| Rule | Detail |
| ---- | ------ |
| **Structure, not HOW** | The tech-plan describes what exists and how components relate. Per-file and per-function implementation steps belong in milestone plan specs, not here. |
| **Chosen path + rejected alternatives** | Each section MUST state what was chosen AND what was considered and dismissed, so the reviewer has material to stress-test. |
| **No implementation detail** | Do not specify function signatures, algorithm internals, or configuration keys. Those are executor concerns. |
| **Grounded** | Every node, container, and schema field must be named in or directly implied by the brief or core-flows. Invent nothing. |

## Part 2: Review — Dedicated Adversarial Stress-Test

The tech-plan review is a **dedicated adversarial phase** with its own review
semantics. It is NOT a renamed copy of the plan-QR gate. The following
rules from plan-review DO NOT apply here:

> The plan-review rules "do not verify file paths" and "do not flag
> executor-resolvable issues" MUST NOT carry over to tech-plan-review.
> Codebase verification is exactly what architectural review is for.

### What the Reviewer Does

1. **Extract 3–7 critical architectural decisions** from the tech-plan (choices
   where the wrong answer causes compounding downstream errors).
2. **Stress-test each decision on six axes**:

| Axis | Question |
| ---- | -------- |
| Simplicity | Is this the simplest structure that satisfies the brief and core-flows? |
| Flexibility | Can the structure accommodate the known variation points without a rewrite? |
| Robustness | Does the structure handle the failure modes the brief names? |
| Scaling | Does the structure hold at the scale the brief implies? |
| Codebase fit | Is the structure consistent with the existing codebase's module boundaries, naming, and conventions? |
| Consistency with brief and core-flows | Does each structural choice trace to a behavior in core-flows or a decision in the brief? |

3. **Scout authority**: Scouts are authorized and encouraged to verify
   integration-point claims, boundary definitions, and schema compatibility
   against the actual codebase. Codebase reads are a first-class tool here.
4. **Classify and act** on each finding per `conventions/producer-validator.md`
   (INTERNAL vs NEW-FILES-NEEDED, rewrite-or-loop-back). All finding-classification
   semantics are defined there; do not restate them here.

### Verdict

- **INTERNAL findings**: fix in place by rewriting the relevant tech-plan section.
  Do not loop back to the architect for INTERNAL findings.
- **NEW-FILES-NEEDED findings**: loop back to tech-plan-spec with the outstanding
  findings plus any in-place fixes already applied.
- When all findings are resolved, the tech-plan is approved and the
  initiative proceeds to milestone decomposition.

## Referenced by

`skills/planner/workflow.mjs` (mode: initiative, tech-plan-spec and tech-plan-review phases).
