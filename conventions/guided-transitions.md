# Guided Phase Transitions: Auto-Advance vs Hand-Back

The discipline governing how a phase exits: auto-advance (the workflow moves
forward without user input) vs hand-back (the loop parks and waits for the user
to direct the next step). This doc states the design rationale and the override
invariant. It does not describe the machinery — the already-built phase-aware-resume
substrate is the mechanism (see below).

## The Two Transition Modes

| Mode | Meaning |
| ---- | ------- |
| **Auto-advance** | The phase completes and the workflow moves forward to its bound next phase without requiring explicit user input. Used on the happy path where the output of one phase is unambiguously the input of the next. |
| **Hand-back** | The phase completes and the loop parks, returning control to the user. The user directs what happens next — proceed, revise, redirect, or stop. |

Auto-advance is **guidance, not enforcement**. A phase whose default is auto-advance
may hand back when its output signals that a finding needs user direction: an
architectural concern surfaced during design, an ambiguity discovered during intake
deepen, a blocking deviation reported after execution. The discipline is about what
the happy path does, not a hard constraint on every exit.

## Override Discipline: Review and Interactive Phases Always Park

The following phases **always hand back**, regardless of whether their output looks
clean:

**Review phases:**
- `plan-design-qr` — quality review of the design artifact
- `plan-code-qr` — quality review of the code-change diffs
- `plan-docs-qr` — quality review of the documentation diffs
- `tech-plan-review` — adversarial stress-test of the structural tech-plan
- `milestone-validate` — soundness check before the milestone loop runs
- `exec-review` — post-execution verdict on a completed milestone

**Interactive phases:**
- `discovery` (frame loop) — open-ended exploration; exits only when the user
  negotiates one of the three explicit exits (promote / hand off / end)
- `curation` — human-approved memory proposal loop; every batch requires
  explicit user approval before writes

**Why this is an invariant, not a preference:**
Review and interactive phases exist precisely to surface signals that auto-advance
would bypass. A review phase's output is inherently variable: it may be a PASS
(proceed), a set of INTERNAL fixes applied in-place, or a loop-back requiring the
producer to reload files. Parking after review hands that signal directly to the
user rather than letting the workflow consume it silently. Interactive phases park
by design — they cannot auto-advance because their terminal condition is
negotiated, not computed.

Auto-advancing past a review phase would conflate a finding-free pass with an
unread finding, erasing the signal the review existed to produce.

## Mechanism

The transition classification and resume behavior are implemented in the
already-built **phase-aware-resume substrate** (`skills/scripts/skills/lib/workflow/persistence/`).
That substrate classifies phases as `read_only` or `execute`, drives the default-deny
resume gate, and parks the loop when a hand-back is warranted. The `phaseTrust`
table in `skills/planner/workflow.mjs` is the declarative contract the substrate
consumes.

This doc describes the **discipline** — the rationale for why phases are classified
the way they are. It does not specify the substrate's implementation.

## Referenced by

`conventions/producer-validator.md` (review phases hand back at the acceptance
moment), `skills/planner/workflow.mjs` (phaseTrust table),
`skills/discovery/SKILL.md` (frame loop parks for user),
`skills/curation/SKILL.md` (proposal loop parks for approval).
