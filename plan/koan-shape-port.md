# Koan Shape Port — Implementation Plan

Closing the workflow-shape gap between [koan](../../koan) and this repo.

## Scope

Port the **workflow shapes** koan encodes that this repo lacks. The durable
runtime substrate (events.jsonl → fold → projection, phase-aware resume, the
Agent-Teams bridge, the run-aware statusline) is **already built here** and is
reused, never rebuilt. Every milestone below is a phase-and-role design, not
runtime machinery.

Derived from two independent fresh-eyes catalogs (koan: 5 workflows + 12
cross-cutting shapes; this repo: 12 skills, 6 agents, conventions). The 8 gaps
are ordered so foundational shapes precede dependent ones.

## Gap → milestone map

| # | Missing koan shape | Milestone | Koan source |
| - | ------------------ | --------- | ----------- |
| 5 | Scout & executor role contracts | **M1** | Shapes A/E/F; `koan/phases/scout.py`, `executor.py` |
| 4 | Producer-validator rewrite-or-loop-back | **M2** | Shape C; `koan/docs/phase-trust.md` |
| 1 | Intake deep-dive (Gather→Deepen→Summarize) | **M3** | Shape D; `koan/phases/intake.py`, `docs/intake-loop.md` |
| 8 | Visualization-first artifact discipline | **M4** | Shape J; `koan/docs/visualization-system.md` |
| 6 | Discovery / open-ended frame workflow | **M5** | Workflow 4; `koan/phases/frame.py` |
| 7 | Curation deliberate-memory workflow | **M6** | Workflow 5 + Shape G; `koan/phases/curation.py` |
| 2 | Execute + exec-review | **M7** | Shape F + plan/exec/review cycle; `koan/phases/execute.py`, `exec_review.py` |
| 3 | Milestone loop with cross-milestone learning | **M8** | Workflow 2 + Shape I; `koan/docs/milestones.md` |

## Wave ordering

```
Wave 1 (foundations, parallel):   M1  M2
Wave 2 (independent shapes):      M3  M4  M5  M6
Wave 3 (depends on M1+M2):        M7
Wave 4 (depends on M2+M7):        M8
```

Rationale: M1 (roles) and M2 (review semantics) are load-bearing for the
execute/loop milestones. M3–M6 are largely independent and can land in any
order. M7 (execute) needs the executor role (M1) and the new review semantics
(M2). M8 (milestone loop) wraps M7's execute+review cycle.

---

## M1 — Register scout & executor role contracts

**Problem.** Three skills (`codebase-analysis`, `refactor`, `incoherence`) pass
`agentType: "Explore"` but no `agents/explorer.md` exists — the type is
undefined. There is also no executor discipline (koan's
comprehend→plan→implement→deviation-report) and no scout verify-step contract.

**Files**
- `agents/scout.md` — **new.** Cheap, read-only investigator. Contract:
  *Investigate* (cast wide, follow imports) → *Verify* (spot-check 2–3 critical
  claims) → *Report* (signal-dense: `file:line`, signatures, call chains; no
  prose padding). No nested scouts, no writes, no user interaction. Model:
  haiku tier. This is the registered home for the `Explore` agentType.
- `agents/developer.md` — **edit.** Add an *executor protocol* block:
  Comprehend (read artifacts, no code) → Plan (visible approach for the audit
  trail, no code) → Implement (apply + rationale comments) → emit a
  **deviation report** (implemented-as-planned / deviations / unanticipated
  decisions / incomplete). Mirrors koan `executor.py`.
- `skills/codebase-analysis/workflow.mjs`, `skills/refactor/workflow.mjs`,
  `skills/incoherence/workflow.mjs` — **edit.** Point `agentType: "Explore"`
  references at the now-registered scout (rename to `scout` or alias).

**Acceptance**
- `agents/scout.md` exists with the 3-step contract; the three skills resolve a
  defined agent type (no undefined `Explore`).
- `developer.md` documents the executor protocol and deviation-report format.
- Existing parity tests still pass.

---

## M2 — Producer-validator rewrite-or-loop-back semantics

**Problem.** `planner`'s QR gates re-run the **whole producer** on FAIL (single
retry, then best-effort). Koan's M4 lesson: most findings are in-place fixes the
producer should make from files it already loaded; full re-runs waste turns.

**Files**
- `conventions/producer-validator.md` — **new.** Defines the shape: a reviewer
  classifies each finding as **internal** (fix in place via artifact write) vs
  **new-files-needed** (surface, recommend loop-back to producer). The user's
  next-step decision is the implicit acceptance moment.
- `skills/planner/workflow.mjs` — **edit.** Change the three QR gates
  (design/code/docs) so a FAIL with only internal findings triggers an
  in-place fix pass rather than a full producer re-dispatch; only
  new-files-needed findings loop back to the producer.
- `agents/quality-reviewer.md` — **edit.** Add the internal vs new-files-needed
  classification to the QR verdict format.

**Acceptance**
- QR verdicts carry a per-finding internal/new-files-needed classification.
- Planner applies in-place fixes for internal findings without re-running the
  full producer; parity tests still pass.
- Convention doc is referenced by `quality-reviewer.md` and `planner`.

---

## M3 — Intake deep-dive

**Problem.** `planner` does `plan-init` + `context-verify` as thin inline
phases with **no question loop**. Koan calls intake "the most consequential
phase — gaps compound." We lack requirements elicitation.

**Files**
- `skills/planner/workflow.mjs` — **edit.** Replace `plan-init`/`context-verify`
  with the koan intake shape:
  - **Gather** — budgeted orientation reads (~5 files), then dispatch scouts
    (M1) for unfamiliar subsystems.
  - **Deepen** — iterative loop: map knowns/unknowns, classify each unknown
    **ASK** vs **SAFE**, ask via `AskUserQuestion` under *default-ask* framing
    ("a question you don't ask is an answer you're making up"), deepen on each
    answer, repeat until no ASK-class unknowns remain.
  - **Summarize** — write a frozen `brief` artifact
    (Scope / Affected-subsystems / Decisions / Constraints / Assumptions /
    Open-questions).
- `conventions/intake.md` — **new.** The ASK/SAFE rubric + default-ask framing
  + brief schema, reusable by any skill that needs elicitation.

**Acceptance**
- A non-trivial `/planner` request triggers ≥1 `AskUserQuestion` round when
  ASK-class unknowns exist, and skips cleanly when none do.
- A frozen brief artifact with the 6 sections is produced and passed forward.
- `phaseTrust` keeps intake phases `read_only`; parity tests pass.

---

## M4 — Visualization-first artifact discipline

**Problem.** Plans are JSON/prose only; not human-inspectable as diagrams.

**Files**
- `conventions/visualization.md` — **new.** Mermaid diagram-slot rules with
  suppression thresholds (koan `visualization-system.md`):
  - **SEQ** `sequenceDiagram` (per flow; suppress if 2 actors + <4 messages +
    no branching)
  - **CON** `flowchart` container (suppress if single container, or 2 with one
    connection)
  - **CMP** `classDiagram`/`flowchart` (suppress if <4 components)
  - **STT** `stateDiagram-v2` (suppress if <3 states or no conditional
    transitions)
  - Grounding rule: every node/actor/state must appear in the bounded inputs.
  - Level-separation: no cross-level mixing.
- `skills/planner/workflow.mjs` — **edit.** Have the design phase emit diagram
  slots per the convention; have `plan-design-qr` flag missing/ungrounded
  diagrams.
- `agents/technical-writer.md` — **edit.** Reference the convention.

**Acceptance**
- Plans carry mermaid blocks where thresholds are met and prose-only below
  threshold (no empty placeholders).
- QR rejects a diagram referencing a node absent from the brief/context.

---

## M5 — Discovery / open-ended frame workflow

**Problem.** No interactive exploration front door / escape hatch. The closest
skill (`codebase-analysis`) is autonomous (no dialogue, no promotion).

**Files**
- `skills/discovery/SKILL.md` — **new.** Single-phase `frame`: refuse nothing
  (design questions, bug hunts, general Q&A), park after each turn awaiting the
  user, never auto-advance. Three negotiated exits: promote into a structured
  skill (`planner`/`refactor`/etc.), hand off to another phase, or end. May
  dispatch scouts (M1) but writes nothing without negotiation.
- `commands/` — optional `/discovery` entrypoint.

**Acceptance**
- The skill conducts a multi-turn exploration without producing a fixed
  artifact unless the user requests one at exit.
- It can promote a session into `planner` carrying the gathered context.

---

## M6 — Curation deliberate-memory workflow

**Problem.** The persistence substrate stores runs, but no **workflow** proposes
memory entries for human approval. Most skills accrue no cross-run learning.

**Files**
- `skills/curation/SKILL.md` — **new.** Batch loop:
  *Inventory* (classify candidates ADD/UPDATE/NOOP/DEPRECATE) → *Memorize*
  per-batch (Draft → self-critique against a checklist → Revise → Propose to
  user → Apply approved → cross off). Directive modes: **postmortem** (from this
  session's transcript; no codebase reads), **review** (audit existing corpus;
  may scout to verify), **document** (from a user-pointed source), **bootstrap**
  (from codebase + interview). Reuses the existing memory substrate for storage.
- `conventions/memory-entry.md` — **new.** Entry schema + the self-critique
  checklist gate (all-PASS before any proposal reaches the user).

**Acceptance**
- Every proposed entry is human-approved before write; convergence signalled by
  successive NOOP-heavy batches.
- All four directive modes select the correct source material.

---

## M7 — Execute + exec-review

**Problem.** `planner` produces `plan.json` and stops; `mode: execute` is
documented but unimplemented. No skill turns a plan into code under review.

**Files**
- `skills/planner/workflow.mjs` — **edit.** Implement `mode: execute`: for each
  wave, dispatch the **executor** (M1 developer protocol) over the plan's
  `code_changes`; collect deviation reports.
- New `exec-review` phase — paired review gate using M2 rewrite-or-loop-back
  semantics: internal findings fixed in place, structural findings loop back to
  the executor.
- `agents/developer.md` — consumes the existing `plan_based_workflow` block;
  extend with deviation-report emission (shared with M1).

**Acceptance**
- `/planner ... mode: execute` applies a plan's code_changes in worktree
  isolation and emits a deviation report per executor.
- `exec-review` gates the result; internal findings are fixed in place.
- Phase trust: execute/exec-review tagged `execute`; resume consent gate fires.

---

## M8 — Milestone loop with cross-milestone learning

**Problem.** `plan.json` lists milestones but nothing iterates them or carries
forward what each milestone established.

**Files**
- `skills/planner/workflow.mjs` (or a new `skills/initiative/workflow.mjs`) —
  **edit/new.** Looping pipeline: for each milestone
  `plan → execute (M7) → exec-review (M7)`, then **UPDATE** a `milestones`
  artifact with an **Outcome** section per milestone — *integration points
  created / patterns established / constraints discovered / deviations from
  plan*. The next milestone's planning phase reads prior Outcome sections.
- `conventions/milestones.md` — **new.** Milestone soundness criteria
  (independently deliverable; grounded in the dependency graph, not tickets;
  one plan-session; one executor-session) + the Outcome schema.

**Acceptance**
- A multi-milestone run updates `milestones` after each `exec-review` and the
  next milestone's planning prompt includes prior Outcomes.
- Milestones are validated against the soundness criteria before execution.

---

## Explicitly out of scope (substrate — already built)

- Step-first injection (koan Shape B)
- Any-to-any phase graph + guided transitions (Shape K)
- events.jsonl → fold → projection, phase-aware resume, Agent-Teams bridge,
  run-aware statusline

## Provenance

- Gap diff and shape catalogs: two fresh-eyes mapper agents (koan-mapper,
  config-mapper), this session.
- Prerequisite already landed: `42667af fix(planner): thread args.request into
  context-capture and design prompts` — closes the planner's own args-threading
  hole (a degenerate instance of gap #1) so `/planner` can act on real requests.
