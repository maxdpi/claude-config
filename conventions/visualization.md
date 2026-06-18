# Visualization: Diagram-Slot Discipline

When and how to embed Mermaid diagrams in design artifacts so plans are
human-inspectable, not JSON/prose only. Referenced by `skills/planner/workflow.mjs`
(design + design-QR) and `agents/technical-writer.md`. Condensed from koan's
visualization system (C4 L1–L3, Mermaid notation).

## The Core Move: Remove the "Should I Draw?" Decision

The naive framing — "the LLM decides when to add a diagram" — is the wrong
primitive. The **template** (this convention) decides two things:

1. **Whether** a diagram appears at a given slot.
2. **What kind** of diagram appears.

What remains for the producer:

- **Instance selection** — which components/actors/states/steps populate the slot.
- **Suppression** — render the slot as prose when complexity is below the
  threshold (§ Suppression).

Diagrams support the process; they are never the deliverable. There is no
standalone `diagrams.md`.

## Slot Catalog

Four diagram types. One type per slot; never mix types within a diagram.

| ID | Mermaid type | Concern | Use at |
| -- | ------------ | ------- | ------ |
| **CON** | `flowchart` | Runtime building blocks (services, stores, queues) the plan introduces/modifies, and their connections | The plan's overall approach |
| **CMP** | `classDiagram` or `flowchart` | Internal modules of one container and their structural relations | A container/milestone with several components |
| **SEQ** | `sequenceDiagram` | Interaction over time across components or actors | Each non-trivial flow |
| **STT** | `stateDiagram-v2` | Lifecycle of an entity with non-trivial transitions | An entity with a real state machine |

CON node shapes: `name[Service]`, `name[(Datastore)]`, `name[/Queue/]`,
`name((External))`. CON edges are directed and labelled with the protocol/message
type (HTTP, SQL, IPC, …). For CMP, pick `classDiagram` when interfaces/contracts
are the point, `flowchart` when flow is the point — one choice per diagram.

## Suppression Thresholds

A slot is rendered as **prose** (not a diagram) when its complexity falls below
the threshold. This handles trivial cases without a judgment call.

| Slot | Suppress (write prose instead) when |
| ---- | ----------------------------------- |
| CON | Single container, or 2 containers with one connection |
| CMP | Fewer than 4 components in scope |
| SEQ | 2 actors, fewer than 4 messages, and no branching |
| STT | Fewer than 3 states, or no guards / conditional transitions |

When a slot is suppressed, write the same information as prose at the slot's
location. **Never emit an empty placeholder, a "diagram suppressed" banner, or a
stub** — the prose stands on its own and the output looks like normal prose.

## Grounding Rule

> No node, actor, or state may appear in a diagram unless it is named or directly
> implied by the bounded inputs (the brief, the planning context, the milestones).

This is the explicit defense against hallucinated architecture. A reviewer
rejects any diagram whose identifiers are absent from the inputs.

## Level Separation

C4's value is level separation. Do not mix abstraction levels in one diagram
(e.g. services and classes together). Each slot has one concern and one level.

## Mermaid Syntax Hazards

`sequenceDiagram` treats some punctuation as syntax tokens:

- **No `;` inside `Note` bodies or message labels** (after the `:` in
  `A->>B: text`) — Mermaid reads `;` as a statement separator and breaks. Use
  `,`, `--`, or split into two Notes.
- **Multi-line Notes use `<br>`**, not raw newlines.

```
# Bad  — semicolon terminates the Note mid-sentence
Note over A,B: Two entry points; mutually exclusive
# Good
Note over A,B: Two entry points -- mutually exclusive
```

## Anti-Patterns

- **The "general documentation" diagram** — a flowchart summarizing "the system
  overall." Lowest-quality view type; forbidden. Every slot has a specific concern.
- **Hallucinated components** — violates the grounding rule.
- **Cross-level mixing** — violates level separation.
- **Notation drift** — switching diagram type within a document.
- **Diagrams as deliverables** — a diagram is part of a section, never standalone.
