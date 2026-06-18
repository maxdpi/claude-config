# Producer–Validator: Rewrite-or-Loop-Back

How review phases relate to the artifacts a producer phase wrote. Referenced by
`agents/quality-reviewer.md` and `skills/planner/workflow.mjs`.

## The Core Principle

> **Rewrite-or-loop-back**: A review phase does not merely report findings. For
> each finding it decides whether to **fix in place** (rewrite the producer's
> artifact directly) or **loop back** (hand the finding to the producer because
> fixing it needs information the producer never loaded).

A review phase trusts nothing it reviews. Every other phase trusts the chain.
Re-verifying an artifact outside a designated review phase ("intrinsic
self-correction") is an anti-pattern: it duplicates the reviewer's job and wastes
turns. Verification happens once, in the review phase that owns it.

**Why this matters**: The naive gate re-runs the *whole* producer on any FAIL.
Most findings, though, are in-place mistakes the producer should have caught from
files it already had open — a missing field, a malformed diff hunk, a contradicted
decision-ref. Routing those through a full producer re-run is wasteful. Reserve
the round-trip for findings that genuinely need new information.

## The Classification Rule

For each finding, the reviewer asks one question:

> **Could the producer have caught this from the context it already loaded?**

The producer's loaded context is its own artifact body plus the frozen inputs it
was handed (e.g. the planning context / brief, the approved design when reviewing
code, the code_changes when reviewing docs).

| Answer | Class | Action |
| ------ | ----- | ------ |
| Yes — fixable from already-loaded context | **INTERNAL** | Fix in place: rewrite the artifact directly. No producer re-run. |
| No — catching it requires loading files the producer never opened | **NEW-FILES-NEEDED** | Loop back: surface the finding and re-dispatch the producer with the new files in scope. |

**Mixed verdicts** are normal: fix the INTERNAL findings in place *and* loop back
for the NEW-FILES-NEEDED ones. The producer then sees the partially-corrected
artifact plus the outstanding findings.

## Examples

| Finding | Class | Why |
| ------- | ----- | --- |
| `code_intent CI-003 has no matching code_change` | INTERNAL | The intent is in the artifact the producer wrote. |
| `decision_ref DL-009 in CI-005 references no declared decision` | INTERNAL | Both the ref and the decision list are in-artifact. |
| `diff hunk for auth.py anchors on a line that does not exist in the current file` | NEW-FILES-NEEDED | Verifying the anchor requires reading `auth.py`, which the design producer never opened. |
| `the proposed module duplicates logic already in utils/retry.py` | NEW-FILES-NEEDED | The producer cannot know about a file outside its handed context. |

When uncertain, default to **INTERNAL** and fix in place — an unnecessary in-place
rewrite is cheap; an unnecessary full producer re-run is not. Loop back only when
you can name the file the producer would have to open.

## The Acceptance Moment

There is no separate sign-off step. The **user's next-step decision** is the
implicit acceptance: when the corrected artifact is surfaced and the user chooses
to proceed (execute, continue, or accept), that is the approval. A review phase's
job ends at producing a corrected artifact plus any outstanding loop-back
recommendations — not at declaring the work "done."

## Verdict Format Obligation

A review phase that follows this convention MUST classify each finding. The
machine-readable line per finding is:

```
- [INTERNAL] <finding> — Fix: <in-place correction>
- [NEW-FILES-NEEDED] <finding> — Needs: <file/info the producer must load>
```

And the gate decision follows from the set of findings:

- All PASS → proceed; artifact is approved.
- FAIL, all findings INTERNAL → apply in-place fixes; do **not** re-run the full producer.
- FAIL, any finding NEW-FILES-NEEDED → loop back to the producer (carrying the
  already-applied internal fixes plus the outstanding new-files findings).
