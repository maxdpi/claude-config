# Platform Assumptions (M-000 wave-0 gating spike)

This document is the **citation/validation anchor** the rest of the persistence plan
references. M-000 is a read-only spike: it empirically validates the load-bearing
platform behaviors the substrate is built on **before** any architecture depends on
them, and records each with a confidence tag, the probe/test that validates it, and
the fallback if it is falsified.

- **Validated in:** session `6bc18a41-f3f2-41d9-b403-9d8da5aaad51`, on
  `2026-06-16`, Claude Code on macOS (Darwin 25.5.0).
- **Environment note (load-bearing):** `~/.claude/settings.json` sets
  `permissions.defaultMode = "auto"`, and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is
  **unset** (Agent Teams disabled). Both materially affect A3 and the DL-021
  permission-precedence finding below.
- **Proof anchors:**
  `skills/scripts/skills/lib/workflow/persistence/probe/` (probes) and
  `subagent_transcript_probe_result.json` (captured A4 evidence), exercised by
  `tests/test_platform_assumptions.py`.

| Assumption | Verdict | Confidence | Probe / proof anchor | Fallback if false |
|---|---|---|---|---|
| **A1** Workflow journal is Python-readable; format/location capturable | ✅ Confirmed | **High** | `workflow_journal_probe.mjs`; run `wf_f423bb66-344` | DL-013 (skills emit durable events directly) — **not** selected |
| **A2** `resumeFromRunId` same-session-only; journals `agent()` calls | ✅ Confirmed (docs + structural) | **High** | `test_resume_from_run_id_same_session`; journal `key` field | none needed |
| **A3** `~/.claude/teams` & `tasks` reaped at session end | ⚠️ Partially falsified — reframe | **Medium** | `teams_dir_probe.py` | C-003 holds via "runtime-owned/clobbered" not "reaped" |
| **A4** native subagent transcript path/format; agentId join | ✅ Confirmed | **High** | `subagent_transcript_probe.py` + result JSON | DL-020 (unresolved path → assume cleaned, not resumable) |

---

## A1 — Workflow tool journal is Python-readable (DL-010, DL-013)

**Verdict: CONFIRMED. Confidence: High. DL-013 fallback NOT selected.**

A minimal workflow (one `agent()` call returning `PONG`) was run via the Workflow
tool (run `wf_f423bb66-344`). Its journal was located and every line parsed cleanly
as JSON.

**On-disk layout (confirmed):**

```
~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/journal.jsonl
~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/agent-{agentId}.jsonl
~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/agent-{agentId}.meta.json
~/.claude/projects/{project}/{sessionId}/workflows/{runId}.json          # run-state projection
~/.claude/projects/{project}/{sessionId}/workflows/scripts/{name}-{runId}.js
```

**`journal.jsonl` line schema** (the resume journal):

```json
{"type":"started","key":"v2:<sha256>","agentId":"afea4dc57083c426a"}
{"type":"result","key":"v2:<sha256>","agentId":"afea4dc57083c426a","result":"PONG"}
```

- `key` is a **content hash** (`v2:` + sha256) of the `agent()` call's `(prompt, opts)`.
  It is the mechanism `resumeFromRunId` matches on: same script + same args → same
  keys → cache hit.
- The run-state file `{runId}.json` is already a **workflow-level projection**:
  `runId, status, result, agentCount, totalTokens, logs, phases[], workflowProgress[]`
  (each agent: `agentId, model, state, tokens, resultPreview, durationMs`). The
  substrate's journal bridge (M-006 / DL-011) can read this directly.

**Implication:** the journal bridge of DL-011 is viable; durability does not have to
fall back to DL-013. (Per DL-011 the bridge is still treated as *best-effort* — on
resume, reconcile journal-vs-eventlog and prefer the authoritative journal on a gap.)

---

## A2 — `resumeFromRunId` is same-session-only and journals `agent()` calls (DL-010)

**Verdict: CONFIRMED (documented + structural corroboration). Confidence: High.**

**Documented semantics** (Claude Code Workflow tool, `resumeFromRunId`):

> "Same-session only. The longest unchanged prefix of `agent()` calls returns cached
> results instantly; the first edited/new call and everything after it runs live.
> Same script + same args → 100% cache hit."

**Empirical corroboration:**

- `agent()` calls **are** journaled — each call writes a `started`/`result` pair
  keyed by the content hash (see A1). That is the replay cache `resumeFromRunId` uses.
- **Same-session-only** is consistent with the on-disk layout: the journal lives
  **under `{sessionId}/`**. A different session does not share that path and cannot
  see the journal unless explicitly handed it. (A within-session round-trip was run;
  a true cross-session negative cannot be driven from inside one session, hence the
  reliance on the documented restriction plus the path-namespacing evidence.)

**Implication for the plan:** this is exactly the gap DL-001/DL-008 cite — native
resume is session-scoped, so **cross-session, workflow-level resume still requires
the substrate.**

---

## A3 — `~/.claude/teams` and `~/.claude/tasks` ephemerality (DL-010, DL-002, R-002)

**Verdict: PARTIALLY FALSIFIED as literally stated — reframe. Confidence: Medium.**
**Action: revisit DL-002 / DL-005 wording (acceptance criterion triggered).**

Observed in this environment:

- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is **unset** → Agent Teams disabled →
  **`~/.claude/teams` does not exist at all.** A3's *teams* half is unobservable
  here (nothing to reap). When the feature is enabled, re-run the probe.
- **`~/.claude/tasks` PERSISTS across sessions.** It held subdirectories dated days
  before the probe (one per task-list id, each with `.lock` + `.highwatermark`).
  It is therefore **NOT reaped at session end** in this configuration.

**Why the load-bearing conclusion still holds.** C-003 ("the durable store MUST live
outside `~/.claude/teams` and `~/.claude/tasks`") is **still required**, but the
*justification* must change:

- ❌ "reaped at session end" — environment-dependent; **not** observed for `tasks`.
- ✅ **"runtime-owned and clobbered-while-live" (C-007)** — the correct, stronger
  reason: the runtime owns and overwrites these dirs while live, so authoring state
  into them is unsafe regardless of eventual reaping.

**Recommended edits (for a later plan revision, not done in M-000):** soften
DL-002/DL-005's "reaped at session end" to "runtime-owned / clobbered-while-live (and
reaped on session end when Agent Teams is enabled)"; keep R-002's flush-as-final-
reconciliation mitigation. This does not change any milestone's design — only the
rationale wording.

---

## A4 — Native subagent transcript path, format, and the correlation join (native-first)

**Verdict: CONFIRMED. Confidence: High.** Proof anchor:
`subagent_transcript_probe_result.json` (DL-015, DL-016, DL-017, DL-020, DL-021).

**Self-bootstrap:** a minimal subagent was spawned via the Agent tool; its
`agentId` (`ab73a631269d58310`) was captured from the spawn result, and its
transcript was then located **by that id**.

**Transcript path pattern (confirmed exactly):**

```
~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl
```

resolved to
`~/.claude/projects/-Users-ethnet/6bc18a41-.../subagents/agent-ab73a631269d58310.jsonl`.

**The correlation join (the thing M-001/DL-016/DL-020 rely on): CONFIRMED.**

```
filename agentId  == in-record agentId  == spawn-result agentId   →  ab73a631269d58310  ✅
in-record sessionId == path sessionId                              →  6bc18a41-...        ✅
```

**Format:** JSONL; every record carries both `agentId` and `sessionId`. Record keys:
`parentUuid, isSidechain, promptId, agentId, type, message, uuid, timestamp,
sessionKind, userType, entrypoint, cwd, sessionId, version, gitBranch`. Record
`type`s observed: `user`, `assistant`, `attachment`. `isSidechain` is `true`.

**`cleanupPeriodDays`:** unset in `settings.json`/`settings.local.json` → **default
30 days**. *Medium confidence* that it governs subagent transcripts specifically (it
governs `~/.claude/projects` transcript retention; subagent transcripts live under
that tree). Retention (M-002) must reconcile against this default.

**`SendMessage`:** available — the Agent tool result offered
`"use SendMessage with to: 'ab73a631269d58310' to continue this agent"` even with
Agent Teams **disabled**. The `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` gate governs
the **teammate/team** path, not subagent continuation. *Presence is
necessary-but-not-sufficient — pin a min-CLI-version when the substrate hard-depends
on it.*

**`permissionMode` (values `plan` / `default` / `acceptEdits` / `bypassPermissions`
/ `auto`):** a direct `permissionMode: "plan"` spawn was **not exercisable** from the
Agent tool or Workflow `agent()` opts — `permissionMode` lives on a subagent **`.md`
frontmatter** (DL-017/DL-023), not on those call sites. So plan-mode spawn is tagged
**medium confidence** (mechanism documented; not directly exercised in M-000).

> **PARENT PRECEDENCE (DL-021) — LIVE in this environment, not hypothetical.**
> `settings.json` sets `defaultMode = "auto"`. `auto` is one of the parent modes
> (`{bypassPermissions, acceptEdits, auto}`) that **overrides** a child's
> `permissionMode`. Therefore, in this user's configuration, a child's `plan` mode
> is **not** enforced: `classify_phases` MUST default-deny (auto-replay **no**
> phase; every phase → needs_confirmation) and `/resume` MUST warn that
> `permissionMode` enforcement is overridden. R-007's mitigation is the default case
> here, not an edge case.

**Session-scoped resume (restated):** native subagent transcripts live under
`{sessionId}/` and `resumeFromRunId` reads them **only within the same session**.
**Cross-session, workflow-level resume is NOT provided by the native runtime and
still requires the substrate** (DL-001).

**Fallback when the transcript path is not found (DL-020):** if the path cannot be
resolved from the run's stored `session_id` + `native_agent_id`, `is_resumable()`
returns **False** (assume cleaned) — never a `started_at` proxy.

---

## Net effect on the plan

| Outcome | Effect |
|---|---|
| A1, A2, A4 confirmed (High) | The substrate's journal bridge, session-scoped-resume premise, and native-transcript correlation join are all sound. **M-001/M-002/M-003/M-006 may proceed.** |
| A3 reframed (Medium) | No design change; **rationale wording** for DL-002/DL-005 should move from "reaped at session end" to "runtime-owned/clobbered-while-live". C-003 unchanged. |
| DL-021 found LIVE | This environment runs parent `defaultMode=auto`; phase-trust via `permissionMode` is **overridden by default here** → resume must default-deny. M-004/resume work must treat this as the common case. |
| DL-013 | **Not** triggered (A1 holds). Journal bridge remains a correctness-capable option, used best-effort per DL-011. |
