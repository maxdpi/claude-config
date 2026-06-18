# Intake: Requirements Elicitation

The shape for gathering complete context before planning or building. Referenced
by `skills/planner/workflow.mjs` (the intake phases) and reusable by any skill
that needs to elicit requirements. Ported from koan's intake phase
(`docs/intake-loop.md`).

## Why Intake Is the Most Consequential Phase

Intake's output — verified understanding of the task and codebase — is the
foundation every downstream phase builds on. Gaps compound: a missed decision
becomes a wrong plan becomes wrong code. An assumption made without verifying
becomes a fact downstream phases treat as decided.

> **A question you don't ask is an answer you're making up.**

## The Three Steps

| Step | Name | Purpose |
| ---- | ---- | ------- |
| 1 | **Gather** | Read the task, orient in the codebase (≤5 files), dispatch scouts for unfamiliar subsystems. |
| 2 | **Deepen** | Process scout findings, verify by reading files, classify unknowns, ask the user, deepen on each answer. |
| 3 | **Summarize** | Synthesize a frozen `brief` artifact. |

Gather has a tight read budget — orientation, not investigation — enough to write
scout prompts that name real paths and symbols. Scouts (read-only investigators,
see `agents/scout.md`) cover what direct reading cannot reach.

## The ASK / SAFE Rubric

In Deepen, map knowns and unknowns per area, then classify **each unknown**:

| Class | Meaning | Action |
| ----- | ------- | ------ |
| **ASK** | User input needed — affects scope, approach, or sequencing. | Ask the user. |
| **SAFE** | Genuinely an implementation detail with no scope impact. | Decide downstream; do not ask. |

The test: *if I assume wrong, does it change the approach or scope, or would the
executor hit a surprise that forces re-planning?* If yes → ASK.

## Default-Ask Framing

Question-asking is the **default**; skipping is what requires justification. This
inverts the typical LLM bias toward advancing the workflow.

- For **every** ASK-class unknown, ask — via `AskUserQuestion` (or the skill's
  elicitation tool).
- Prefer bounded multiple-choice; ground each question in a specific finding
  ("scout found X — should this follow the same pattern?").
- Do not add "Other" / "None of the above" meta-options — the UI supplies a
  free-text input.
- Each answer is a thread to pull: read newly-referenced files, surface new
  unknowns, ask follow-ups. Repeat until no ASK-class unknowns remain.
- **No per-round question cap.** Completion is defined by depth of understanding,
  not question count; multiple rounds are expected for non-trivial tasks.
- When there are no ASK-class unknowns, skip questioning and proceed cleanly.

## The Brief Schema

Summarize writes a `brief` with **exactly these six sections**. If a section has
no content, write `(none)` — never omit a section; downstream phases parse the
structure.

| Section | Content |
| ------- | ------- |
| **Scope** | In-scope and out-of-scope bullets. Out-of-scope matters most — it prevents downstream scope growth. |
| **Affected subsystems** | Concrete file paths/modules with one-line descriptions, grounded in real code. |
| **Decisions** | Numbered. Each: the choice + rejected alternatives + rationale. Each is a constraint downstream plans must respect. |
| **Constraints** | Cross-cutting technical/architectural/operational boundaries. |
| **Assumptions** | Things assumed without verifying, stated so they are falsifiable downstream. |
| **Open questions** | Caution zones surfaced but not resolved. |

The brief is **frozen** at intake exit: it is the authoritative initiative context
and is not rewritten downstream. If execution reveals an assumption is wrong, that
is recorded in the relevant milestone Outcome or as a note — not by silently
editing the brief.
See `conventions/artifacts.md` for the frozen lifetime class definition and the brief's place in the per-artifact lifecycle table.

## What Intake Does NOT Do

Intake gathers and describes what exists and what was said. It does not design,
plan, or implement; it does not infer decisions that were not explicitly stated;
it does not define deliverables or scope boundaries — those belong to downstream
phases. If something is unclear, it is captured as an Open question, not invented.
