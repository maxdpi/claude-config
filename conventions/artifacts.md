# Artifact Lifecycle: Frozen / Additive-Forward / Disposable

The single source of truth for artifact lifetime classes in this repo. Each
per-artifact convention doc cross-links here rather than redefining the classes
inline. Referenced by `skills/planner/workflow.mjs` and the initiative-mode
convention docs (`conventions/core-flows.md`, `conventions/intake.md`,
`conventions/tech-plan.md`, `conventions/milestones.md`).

## Lifetime Taxonomy

Every artifact produced by a planner phase belongs to exactly one lifetime class.
The class determines who may write the artifact after it is first produced and how
downstream phases relate to it.

### Frozen

Written once by its producer phase, then never rewritten by any downstream phase.
Downstream phases read it as authoritative truth. If execution reveals an error in
a frozen artifact, that error is recorded in the relevant Outcome or Decisions
section — not by editing the artifact itself.

Example: the `brief` produced by `intake-summarize`. Every downstream phase reads
it; none may rewrite it.

### Additive-Forward

Rewritten in place by its producer across the lifecycle, but with a strict
constraint: Outcome sections are **append-only**. Prior Outcome sections are
preserved intact when the artifact is updated. This preserves the learning history
across milestone iterations while allowing the living artifact to reflect the
current state of the work.

Example: the `milestones` artifact, updated after each exec-review via the UPDATE
cycle. Each milestone's Outcome section accumulates; earlier Outcomes are never
overwritten.

### Disposable

Written once by its producer phase, read by its reviewer and by downstream phases,
then superseded by a downstream artifact that compresses what was actually built.
Do not treat a disposable artifact as the ground truth once execution has begun;
milestone Outcomes become the ground truth.

Example: the `tech-plan` artifact. Its reviewer may rewrite it in place during
review, but once milestone execution begins, the milestone Outcome sections
progressively supersede it.

## Per-Artifact Lifecycle Table

Producers own writes. Downstream phases read but do not write frozen or disposable
artifacts. Additive-forward Outcome sections are append-only — every prior Outcome
is preserved when the artifact is updated.

| Artifact        | Lifetime          | Producer phase(s)                              | Reader phase(s)                                                     |
| --------------- | ----------------- | ---------------------------------------------- | ------------------------------------------------------------------- |
| `brief`         | Frozen            | `intake-summarize`                             | `plan-design-work`, `core-flows`, `tech-plan-spec`, `tech-plan-review`, `milestone-validate`, `milestone-plan` |
| `core-flows`    | Frozen            | `core-flows`                                   | `tech-plan-spec`, `tech-plan-review`, `milestone-validate`, `milestone-plan`, `execute`, `exec-review` |
| `tech-plan`     | Disposable        | `tech-plan-spec`; reviewer rewrites in `tech-plan-review` | `milestone-validate`, `milestone-plan`; superseded by milestone Outcomes |
| `milestones`    | Additive-Forward  | `milestone-validate` (initial); `milestone-plan`, `milestone-outcome`, `milestone-propagate` (updates) | `milestone-plan`, `execute`, `exec-review`, `milestone-propagate` |
| `plan` / milestone plan | Frozen    | `plan-design-work`, `plan-code-work`, `plan-docs-work` (and their QR phases) | `execute`, `exec-review` |

## Ownership Rule

The producer phase that first writes an artifact owns all subsequent writes to
that artifact. For frozen and disposable artifacts, "subsequent writes" means
only the reviewer's in-place corrections during the dedicated review phase —
no other phase may edit them. For additive-forward artifacts, the owning phases
(milestone-outcome, milestone-propagate) append to Outcome sections but must
not alter prior Outcome sections.

## Referenced by

`conventions/core-flows.md` (frozen artifact), `conventions/intake.md` (frozen
brief), `conventions/tech-plan.md` (disposable artifact), `conventions/milestones.md`
(additive-forward UPDATE cycle).
