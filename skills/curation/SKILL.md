---
name: curation
description: Invoke IMMEDIATELY to propose durable memory entries for human approval — deliberate cross-run learning. You (the lead) run a batch loop: inventory candidates, self-critique each draft against the memory-entry gate, propose, and write ONLY what the user approves. Do NOT write memory silently; nothing is written without explicit user approval.
argument-hint: [mode: postmortem | review | document <source> | bootstrap]
allowed-tools: Read Glob Grep Bash(ls *) Bash(cat *)
---

# Curation

When this skill activates, **you are the lead.** You maintain a small,
high-quality memory that helps agents work effectively across runs. Your one
job is to write durable memory — but only entries a human has approved.

This skill is **interactive**, not a fan-out workflow. There is no
`workflow.mjs`: each batch ends with you handing control back to the user for
approval before anything is written. Review and bootstrap modes MAY dispatch
read-only **scout** workers to verify facts, but the drafting, critique, and
write decisions stay with you.

## Hard invariant — propose, then write

You propose; the user approves; then you write. **Every** memory mutation
(ADD / UPDATE / DEPRECATE) is presented to the user and approved before you
call any write tool. End your turn with the proposal — no write tool call in
the same turn — so the loop hands back and waits. There are **no silent
writes**. This invariant overrides every other instruction here.

## The memory stores (reuse; never rebuild)

Curation writes into one of the two stores that already exist. It never
invents storage. Read `conventions/memory-entry.md` for the entry schema, the
store layout, and the self-critique gate before drafting.

- **User auto-memory** — `~/.claude/projects/<project-slug>/memory/`, indexed
  by `MEMORY.md`. One fact per file plus a one-line `MEMORY.md` pointer. This
  is the default target for cross-session facts about the user, the project,
  feedback, and references.
- **Agent project-memory** — `.claude/agent-memory/<role>/MEMORY.md`. Durable
  per-role knowledge (e.g. `quality-reviewer`). Target this only when the
  invocation is curating a specific agent's review knowledge.

If the project slug or store path is ambiguous, ask the user which store to
target before drafting. Read the target store in full at the start (step 1) so
your classifications are accurate.

## Directive modes — the invocation selects the source

The argument selects WHERE the candidate facts come from. Default to
**postmortem** if no mode is given inside a session that has done work;
otherwise ask.

| Mode          | Source material                                          | Codebase reads | Scouts | User interview |
| ------------- | ------------------------------------------------------- | -------------- | ------ | -------------- |
| **postmortem** | THIS session's transcript above                        | No             | No     | No             |
| **review**    | The existing memory corpus (audit it)                   | Only to verify | Yes    | No             |
| **document**  | A user-pointed source (file / dir / URL)               | The source only | If large | No           |
| **bootstrap** | The codebase + an interview with the user              | Yes            | Yes    | Yes            |

- **postmortem** — walk your own conversation history. Extract decisions made,
  lessons learned (especially user corrections), procedures established, and
  durable context surfaced. No codebase reads; everything is already in context.
- **review** — read the existing entries directly and audit them for
  staleness, contradictions, gaps, and entries that should merge or deprecate.
  Dispatch `scout` workers (`agentType: "scout"`) to verify a suspect entry
  against the current code before proposing an UPDATE or DEPRECATE. If memory
  is empty, pivot to bootstrap.
- **document** — read the source the user named. Each distinct piece of
  durable knowledge becomes its own self-contained entry (never one entry that
  says "X documents Y"). Dispatch scouts for broad multi-file sources.
- **bootstrap** — seed an empty memory: read README / CLAUDE.md / AGENTS.md,
  dispatch scouts across the codebase, and interview the user for the
  invisible knowledge that is not in any file (team facts, constraints,
  rationale behind choices).

## Step 1 — Inventory

Build a numbered candidate list. Nothing is written in this step.

1. **Load the target store.** Read its `MEMORY.md` index and the existing
   entries so you know what is already captured. This is your duplicate-detection
   baseline.
2. **Gather source material** per the directive mode above.
3. **Classify each candidate** against the existing corpus:
   - **ADD** — no existing entry covers this → draft a new entry.
   - **UPDATE** — an existing entry covers this but needs revision → draft the
     revision against the existing entry's slug.
   - **NOOP** — already adequately captured → skip.
   - **DEPRECATE** — this makes an existing entry obsolete → propose removal.
   When a candidate is close to an existing topic, open that entry and compare
   bodies before classifying.
4. For each candidate note: `name/slug`, one-line description, `type`
   (per the target store's taxonomy in `conventions/memory-entry.md`),
   classification, and target store.

Do not end step 1 until you have at least one ADD / UPDATE / DEPRECATE
candidate, OR you can state explicitly "all candidates were NOOPs because X"
(legitimate convergence — proceed to wrap-up with zero writes).

## Step 2 — Memorize (the per-batch loop)

Process candidates in batches of 3–5. For each batch, run these sub-operations
**in order**, each producing a visible committed output before the next begins.
Do not collapse or skip ahead — the committed-artifact structure is the quality
gate.

### A. Draft

Write each non-NOOP candidate as a complete entry per the schema in
`conventions/memory-entry.md`: name, description, type, body (with WHY, and
HOW-to-apply for feedback/project facts), and `[[links]]`. Output all drafts
for the batch as a visible list before moving on. Commit to the drafts as-is.

### B. Self-critique

For each draft, run the 9-item gate from `conventions/memory-entry.md`. Output
the result per draft in this exact format:

    Draft 1 ({slug}):
      1. Durable, not transient:        PASS / FAIL
      2. Non-obvious / not in code:     PASS / FAIL
      3. Grounded in evidence:          PASS / FAIL
      4. Timeless-present (temporal.md): PASS / FAIL
      5. Single fact:                   PASS / FAIL
      6. Description enables recall:    PASS / FAIL
      7. Self-contained, not a pointer: PASS / FAIL
      8. Concrete naming:               PASS / FAIL
      9. Right store and type:          PASS / FAIL

Do not merge this substep into A or C. The explicit checklist output is the
committed artifact that prevents simulated refinement.

### C. Revise

For every draft with any FAIL, rewrite the entry completely (do not patch in
place) and re-run the 9-item gate on the rewrite. Loop until **all nine items
PASS for all drafts in the batch**. You MAY NOT proceed to substep D while any
draft has an outstanding FAIL.

### D. Propose

Present the all-PASS batch to the user for approval. For each proposal show:
operation (ADD / UPDATE / DEPRECATE), target store, slug, type, description,
the full body, and for UPDATE a before/after. Then **end your turn** — no write
tool call — and wait for the user's decisions.

### E. Apply approved

When the user responds, branch per proposal:
- **approved, no feedback** → write it: ADD/UPDATE writes the entry file (and
  its `MEMORY.md` index pointer) or the agent-store section; DEPRECATE removes
  the entry and its index line.
- **approved with feedback** → incorporate the feedback into the body, then write.
- **rejected, no feedback** → drop it; write nothing.
- **rejected with feedback** → revise per the feedback and re-propose
  (single-item batch is fine); do not write until re-approved.

Honor the entry schema and index discipline in `conventions/memory-entry.md`
on every write. Honor `temporal.md` (timeless present, absolute dates) and
ASCII / no-emoji markdown hygiene.

### F. Cross off and converge

Cross written/dropped items off the candidate list and loop back to substep A
with the next batch. **Convergence**: stop when the candidate list is empty,
when successive batches are NOOP-heavy (the source yields no new durable
knowledge), or when the user says to stop.

## Wrap-up

Before ending, verify: did you write every approved ADD / UPDATE / DEPRECATE,
and update each `MEMORY.md` index pointer? If your step 1 list was non-empty
and you wrote nothing, you have not done the work — loop back. (Zero writes is
correct only when step 1 was explicitly all-NOOPs.)

Report the final counts inline: `{added: N, updated: N, deprecated: N, noop: N}`
plus a one-line note on anything deferred for a future run.
