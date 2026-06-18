# Milestones: Soundness Criteria and Cross-Milestone Learning

What makes a milestone sound, how to size it, and how each milestone's Outcome
carries forward to the next. Referenced by `skills/planner/workflow.mjs`
(`mode: milestones`). Ported from koan's milestones workflow.

## What a Milestone Is

A milestone is a coherent, **independently-deliverable** unit of work within a
broad initiative. It is the unit of planning and execution: each milestone gets
its own plan, its own executor session, and its own review. The milestone loop
runs `plan → execute → exec-review → UPDATE` per milestone until all are done.

Milestones are NOT tasks, stories, or tickets. They are structural partitions of
a codebase-change initiative, grounded in the actual dependency graph of the code
being modified.

## Soundness Criteria

A sound milestone satisfies four properties. Each has an operational test applied
before execution (validation gate) — a milestone that fails any test is split,
merged, or re-grounded before the loop runs it.

1. **Independently deliverable** (local-constraint property). *Test:* if the
   executor implemented only milestone N and stopped, would N's stated outcome
   still hold? If it needs N+1 to land, N is not independent.
2. **Grounded in code structure.** Decompose along dependency edges, not against
   them. *Test:* map each milestone to a set of files/modules. Do the milestones
   partition the affected subgraph into connected subgraphs, or slice across
   strongly-connected components? The latter is a structural error.
3. **Plannable within one plan session.** *Test:* can the planner read every file
   the milestone touches (or its interface files) and still write a detailed
   plan? 40+ files across multiple subsystems probably fails.
4. **Executable within one executor session.** *Test:* a plan of roughly 10–30
   concrete steps is the ceiling for one executor session before quality
   degrades. Larger should split.

## Sizing Heuristics

The binding constraint is the **context capacity of downstream phases**, not time
estimates.

- **Files-touched:** ~5–30 files per milestone. Fewer → merge with a neighbor.
  More → split.
- **Plan-step:** the milestone's plan should be ~10–30 steps. If the decomposer
  can already see 50+ steps, it is too large.
- **Description:** if the milestone sketch needs more than ~6 sentences, it is
  probably doing too much.

## Grounding (in priority order)

1. Read the project's **module structure** (directory tree, top-level packages,
   visible boundaries) — the prior for where milestones should cut.
2. Identify the **affected subgraph** from intake findings; read the import graph
   among the touched modules.
3. **Map each milestone to a scope** — name the files/modules it owns. A scope
   that cannot be named in terms of existing structure is either greenfield
   (legitimate) or imaginary (a decomposition error).
4. **Check for overlaps.** Two milestones owning the same file/function are not
   independent — overlapping ownership means they are not truly partitioned.

## The Outcome Schema

After exec-review completes for a milestone, UPDATE the `milestones` artifact:
mark the milestone done and append an `### Outcome` section describing **what was
actually accomplished, not what was planned**, with exactly four subsections:

| Subsection | Content |
| ---------- | ------- |
| **Integration points created** | New interfaces, extension seams, modules subsequent milestones can depend on — named with file paths and identifiers. |
| **Patterns established** | Naming, file placement, error handling, and test conventions this milestone committed to. |
| **Constraints discovered** | Things harder or different than the sketch anticipated; explicit facts that change what future milestones can assume. |
| **Deviations from plan** | What the executor did differently and why (sourced from the deviation report + exec-review). |

Preserve all prior milestones' Outcome sections intact when updating. After the
UPDATE, advance the next pending milestone and adjust remaining sketches if the
deviations require it.

## Cross-Milestone Learning

When planning milestone N > 1, carry forward what prior milestones established:

- Read the **Outcome sections** of all completed milestones before planning the
  next one. They describe integration points, patterns, and constraints already
  in place.
- If an Outcome references a specific file or interface the current milestone
  extends, **read that file directly** — the code is the source of truth, not the
  prior plan.
- Cross-milestone learning is about **directing attention**, not recovering lost
  context.

## Forward Propagation

Forward propagation is the **complement of backward Outcome carry-forward** (see
The Outcome Schema and Cross-Milestone Learning above). Where those sections
describe reading completed milestones' Outcomes when planning the next one,
forward propagation describes writing what was learned FORWARD into the specs
of milestones that have not yet run.

The two mechanisms handle different temporal directions of the same learning:

| Direction | Mechanism | When it runs |
| --------- | --------- | ------------ |
| Backward (pull) | Cross-Milestone Learning — read prior Outcomes before planning the next milestone | At each milestone-plan phase |
| Forward (push) | Forward Propagation — push learnings into pending specs after each milestone-outcome | At each milestone-propagate phase, immediately after milestone-outcome |

### When to Propagate

After a milestone's exec-review and Outcome, review what verification and the
verdict revealed. Ask: does what was learned affect any REMAINING (pending)
milestone?

Propagation-worthy learnings include:
- A constraint encountered during execution that invalidates an assumption in a
  pending milestone's plan.
- A pattern established that pending milestones should follow for consistency.
- A decision made (or unmade) that pending milestones were relying on.
- A completed milestone that makes a pending one unnecessary (flag for skip with
  a clear reason).

If nothing relevant was learned, **write nothing and proceed**. Forward
propagation is a no-op when the completed milestone's learnings do not affect
any remaining milestone.

### How to Propagate

For each affected pending milestone, add a section to its spec:

```
## [autonomous] Propagated Context

<what was learned and why it affects this milestone>
```

Update the plan's Decisions section if a decision was made or invalidated,
prefixing autonomous additions with `[autonomous]`.

### The [autonomous] Marker

The `[autonomous]` prefix marks every edit the planner makes to a pending
milestone spec or the Decisions section without explicit user authorization.
It is the literal string `[autonomous]` — not an emoji, not a shorthand.
These edits are grep-auditable: `grep -r '\[autonomous\]'` surfaces every
autonomous propagation in a plan. The marker is namespace-disjoint from the
`:PERF:/:UNSAFE:/:SCHEMA:` intent-marker family (`conventions/intent-markers.md`);
it carries no code-quality or security semantics.

## Compound-Risk Framing

Errors at the milestone layer compound across every subsequent phase:

```
milestone decomposition error
  -> wrong plan scope -> wrong plan
    -> wrong execution -> wrong code
      -> wrong exec-review -> wrong Outcome
        -> wrong next-milestone plan
```

This is why milestones are validated against the soundness criteria *before* the
loop executes them. A missed issue here is inherited by every downstream
milestone.
