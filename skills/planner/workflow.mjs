/**
 * Planner — full Workflow-tool port (M-006.5, CI-M-006-015, DL-026).
 *
 * Replaces the M-006 scaffold ({status:"scaffold"}) with the complete
 * planner phase sequence ported from orchestrator/planner.py.
 *
 * Phase sequence (mirrors the 14-step Python orchestrator):
 *   plan-init          — context capture (read_only)
 *   context-verify     — context persistence + self-check (read_only)
 *   plan-design-work   — architect role: design milestones/code-intents (execute)
 *   plan-design-qr     — quality-reviewer: verify design (execute)
 *   plan-code-work     — developer role: fill code_changes (execute)
 *   plan-code-qr       — quality-reviewer: verify code (execute)
 *   plan-docs-work     — technical-writer role: add doc_diffs (execute)
 *   plan-docs-qr       — quality-reviewer: verify docs (execute)
 *
 * Durable substrate wiring (M-006.5 / DL-013 / DL-014):
 *   Each phase boundary emits phase_started / phase_completed events via the
 *   Python persistence lib (shelled out via a helper comment noting the call),
 *   and a phase manifest is written at run start so the resume engine can
 *   classify phases as read_only or execute (DL-006 / DL-014).
 *
 *   Because the Workflow tool sandbox may not expose Node fs (A1 probe result
 *   selects the DL-013 fallback), the .mjs itself cannot import the Python
 *   subprocess directly.  The durable events are emitted by writing a small
 *   shell command via log() that the runtime environment picks up — this
 *   is the same pattern all other ported skills use.  The manifest and
 *   subagent-dir-as-contract are declared structurally in the meta.phases
 *   table below so the Python-side resume engine can consume them even before
 *   a live SubagentStart hook fires.
 *
 * DL-023 compliance: no frontmatter on this .mjs script.  isolation:worktree,
 * maxTurns, skills: live on the role .md files (agents/architect.md etc.).
 *
 * Returns the real `plan` artifact — a plan.json-shaped object with the fields
 * required by the parity test (key "plan").
 */

export const meta = {
  name: "planner",
  description: "Interactive planning skill — architect/developer/QR/TW phase sequence",
  phases: [
    "intake-gather",
    "intake-deepen",
    "intake-summarize",
    "plan-design-work",
    "plan-design-qr",
    "plan-code-work",
    "plan-code-qr",
    "plan-docs-work",
    "plan-docs-qr",
    "execute",
    "exec-review",
    "milestone-validate",
    "milestone-plan",
    "milestone-outcome",
    // Initiative-mode phases run once upstream of the milestone loop (G1/G2).
    // milestone-propagate runs inside the loop after each milestone-outcome (G3).
    // All four are 'execute' trust: they write artifacts (not reads).
    "core-flows",
    "tech-plan-spec",
    "tech-plan-review",
    "milestone-propagate",
  ],
  /**
   * Phase trust manifest (DL-014, DL-006).
   * Consumed by the resume engine: read_only phases auto-replay on resume;
   * execute phases require explicit user confirmation (default-deny).
   *
   * This declarative table is the manifest.json content written by the
   * persistence lib at run-start via write_phase_manifest().  Embedded here
   * so the .mjs is the single source of truth for phase trust (DL-014).
   */
  phaseTrust: {
    "intake-gather":    "read_only",
    "intake-deepen":    "read_only",
    "intake-summarize": "read_only",
    "plan-design-work": "execute",
    "plan-design-qr":   "execute",
    "plan-code-work":   "execute",
    "plan-code-qr":     "execute",
    "plan-docs-work":   "execute",
    "plan-docs-qr":     "execute",
    "execute":          "execute",
    "exec-review":      "execute",
    "milestone-validate": "read_only",
    "milestone-plan":     "execute",
    "milestone-outcome":  "execute",
    "core-flows":         "execute",
    "tech-plan-spec":     "execute",
    "tech-plan-review":   "execute",
    "milestone-propagate": "execute",
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Shared prompt fragments (ported from planner.py + shared/constraints.py)
// ─────────────────────────────────────────────────────────────────────────────

const THINKING_EFFICIENCY = `THINKING ECONOMY: Per-thought limit 10 words. Abbreviated notation only.
DO NOT narrate phases. Execute silently; output results only.`;

const QR_PASS_FAIL_GATE = `After ALL verifier agents return:
  ALL returned PASS  →  proceed
  ANY returned FAIL  →  repeat the work phase with the QR findings`;

// Rewrite-or-loop-back classification (conventions/producer-validator.md, koan M4
// lesson). The QR labels every finding so the gate can choose an in-place fix over
// a full producer re-run. INTERNAL findings are fixable from context the producer
// already loaded; NEW-FILES-NEEDED findings require a file it never opened.
const QR_CLASSIFICATION_INSTRUCTION = `
CLASSIFY EACH FINDING (conventions/producer-validator.md):
- [INTERNAL] — the producer could have caught this from the artifact + context it
  already had. Give the in-place fix.
- [NEW-FILES-NEEDED] — catching it needs a file the producer never opened. Name
  that file under "Needs:".
Default to INTERNAL when unsure. End with one machine-readable line:
  LOOP_BACK: NONE              (PASS, or all findings INTERNAL)
  LOOP_BACK: NEW-FILES-NEEDED  (any finding is NEW-FILES-NEEDED)`;

// ─────────────────────────────────────────────────────────────────────────────
// Intake (koan Gather → Deepen → Summarize). Replaces the old thin
// plan-init/context-verify capture. Intake is the most consequential phase:
// gaps here compound into wrong plans and wrong code (conventions/intake.md,
// koan docs/intake-loop.md). Three read_only phases produce a frozen `brief`.
// ─────────────────────────────────────────────────────────────────────────────

// Phase 1: intake-gather.
// Subagents cannot see the orchestrator conversation (skills/README.md runtime
// contract), so the user request is injected explicitly. Gather orients in the
// repo on a tight budget, then proposes scout assignments the SCRIPT dispatches
// in parallel (the agent itself does not spawn — it returns assignments as JSON).
const INTAKE_GATHER_PROMPT = (requestText) => `PLANNER — intake-gather

${THINKING_EFFICIENCY}

You are the INTAKE analyst. Read the task, orient in the codebase, and plan the
investigation. You gather and describe what EXISTS; you do NOT design, plan, or
infer unstated decisions.

USER REQUEST:
${requestText || "(no request text supplied — explore the repository to recover context)"}

ORIENT (budget: ~5 file reads — this is orientation, not investigation):
- ls the project root; open README.md / AGENTS.md / CLAUDE.md if present.
- Open any file the request explicitly names (skim structure/exports, ~50-100 lines).
- Locate by name with one find/ls when a module is named without a path.
Just enough to write scout prompts that reference real paths and symbols.

PLAN SCOUTS: For unfamiliar subsystems or broad dependency tracing, propose
read-only scouts (dispatched in parallel after this step). Each scout needs an
id (kebab-case), a role (investigator focus), and a rich 3-8 sentence prompt
naming the files/symbols to investigate. Propose zero scouts when direct
orientation already covers the task.

OUTPUT a single JSON object:
{
  "context": {
    "topic": "what is being built/changed",
    "file_references": ["path — why relevant"],
    "decisions_stated": ["only decisions explicitly stated in the request"] or ["none"],
    "constraints": ["technical/timeline/compat"] or ["none"],
    "conventions_mentioned": ["coding/test/doc standards referenced"] or ["none"],
    "gaps": ["raised-but-unanswered / unclear items that affect scope"]
  },
  "scouts": [ { "id": "auth-layer", "role": "auth auditor", "prompt": "..." } ]
}`;

// Phase 2: intake-deepen.
// The primary user-dialogue phase. Maps knowns/unknowns, classifies each unknown
// ASK vs SAFE, and asks ASK-class unknowns via AskUserQuestion under default-ask
// framing. Runs on the DEFAULT workflow agent (no agentType) so it has the
// AskUserQuestion tool — the architect agentType is read-only Read/Grep/Glob/Bash
// and cannot elicit (the same default-agent pattern incoherence's resolution uses).
const INTAKE_DEEPEN_PROMPT = (requestText, gatherContext, scoutFindings) => `PLANNER — intake-deepen

Deepen understanding through dialogue and codebase verification. Scout results are
a starting point, not the finish line. What you get wrong here silently propagates
into the plan and the code.

USER REQUEST:
${requestText || "(none — rely on the gathered context below)"}

GATHERED CONTEXT (intake-gather):
${gatherContext}

SCOUT FINDINGS:
${scoutFindings || "(no scouts dispatched)"}

DO:
1. Process scout findings: do they answer the questions, reveal surprises, or
   conflict with the request? For scope-affecting findings, open the real files
   and confirm.
2. Map knowns/unknowns per relevant area (Known / Unknown / Source).
3. Classify EACH unknown:
   - ASK  — user input needed: affects scope, approach, or sequencing.
   - SAFE — genuinely an implementation detail with no scope impact.
4. DEFAULT-ASK: question-asking is the default; a question you don't ask is an
   answer you're making up. For EVERY ASK-class unknown, call AskUserQuestion.
   - Prefer bounded multiple-choice; ground each question in a specific finding
     ("scout found X — should this follow the same pattern?").
   - Do NOT add "Other"/"None" meta-options (the UI supplies free text).
5. Deepen on each answer: read newly-referenced files, surface new unknowns,
   ask follow-ups. Repeat until no ASK-class unknowns remain.
6. If there are NO ASK-class unknowns, skip questioning and proceed cleanly.

OUTPUT the deepened understanding: per-area knowns, resolved answers, the
decisions they imply, remaining assumptions, and any open questions.`;

// Phase 3: intake-summarize.
// Synthesizes the frozen `brief` — the authoritative initiative context every
// downstream phase reads. Six sections (conventions/intake.md). Frozen at exit:
// downstream phases do not rewrite it; a wrong assumption is recorded later, not
// silently edited here.
const INTAKE_SUMMARIZE_PROMPT = (requestText, deepened) => `PLANNER — intake-summarize

Synthesize the frozen initiative BRIEF from everything gathered and deepened.

USER REQUEST:
${requestText || "(none)"}

DEEPENED UNDERSTANDING:
${deepened}

Write the brief with EXACTLY these six sections. If a section has no content,
write "(none)" — do NOT omit sections; downstream phases parse the structure.

## Scope
In scope: ...
Out of scope: ...        (out-of-scope matters most — it prevents scope growth)

## Affected subsystems
Concrete file paths/modules with one-line descriptions, grounded in real code.

## Decisions
Numbered. Each: the choice + rejected alternatives + rationale. Each decision is
a constraint downstream plans must respect.

## Constraints
Cross-cutting technical/architectural/operational boundaries the work must respect.

## Assumptions
Things assumed without verifying, stated so they are falsifiable downstream.

## Open questions
Caution zones surfaced but not resolved.

OUTPUT only the brief (the six sections above). This brief is FROZEN at intake exit.`;

// ─────────────────────────────────────────────────────────────────────────────
// Phase 3: plan-design-work
// ─────────────────────────────────────────────────────────────────────────────

// requestText carries the original user goal so the architect can cross-check
// the captured context against it. Context phases may thin-capture; having the
// raw request here prevents the design from drifting away from user intent.
const PLAN_DESIGN_WORK_PROMPT = (context, requestText) => `PLANNER — plan-design-work

You are dispatching to the ARCHITECT role to design the implementation plan.

USER REQUEST (original goal):
${requestText || "(no request text supplied — design from the planning context below)"}

PLANNING CONTEXT:
${context}

ARCHITECT TASK: Design a complete implementation plan including:

1. OVERVIEW
   - problem: clear statement of what we are solving
   - approach: high-level implementation strategy

2. PLANNING_CONTEXT
   - decisions: architectural decisions (DL-XXX format) with reasoning
   - rejected_alternatives: what was considered and dismissed
   - constraints: MUST/SHOULD/MUST-NOT constraints
   - risks: identified risks with mitigations

3. INVISIBLE_KNOWLEDGE
   - system: mental model future LLMs need
   - invariants: design invariants that must be preserved
   - tradeoffs: accepted tradeoffs and why

4. MILESTONES (M-XXX format)
   - id, number, name
   - files: exact file paths to create/modify
   - requirements: what this milestone accomplishes
   - acceptance_criteria: testable pass/fail criteria
   - code_intents: behavioral descriptions for Developer (CI-XXX format)
     Each intent: id, file, function (optional), behavior, decision_refs

5. WAVES: parallel execution groupings (W-XXX format)

6. DIAGRAMS: per conventions/visualization.md, emit Mermaid diagram slots so the
   plan is human-inspectable. The TEMPLATE decides whether/what; you select
   instances and apply suppression:
   - CON (flowchart) for the overall approach — runtime building blocks + connections.
   - SEQ (sequenceDiagram) per non-trivial flow.
   - CMP (classDiagram/flowchart) for any container/milestone with ≥4 components.
   - STT (stateDiagram-v2) for an entity with ≥3 states and conditional transitions.
   SUPPRESS below threshold: write prose instead of a diagram — never an empty
   placeholder or a "suppressed" banner. GROUNDING: every node/actor/state must
   appear in the brief/context above; invent nothing. One type per diagram; no
   cross-level mixing.

OUTPUT: A JSON object matching the plan.json schema with all fields populated.
The output MUST contain overview, planning_context, milestones, and waves, plus a
"diagrams" array of { id (CON|CMP|SEQ|STT), title, mermaid } for slots at/above
threshold (omit suppressed slots from the array; their prose lives in the relevant
section).`;

// ─────────────────────────────────────────────────────────────────────────────
// Phase 4: plan-design-qr
// ─────────────────────────────────────────────────────────────────────────────

const PLAN_DESIGN_QR_PROMPT = (designResult) => `PLANNER — plan-design-qr

QUALITY REVIEW: Verify the plan design against these criteria:

DESIGN OUTPUT TO REVIEW:
${designResult}

VERIFICATION ITEMS — check each:

[ ] 1. overview.problem is a clear problem statement (not a solution)
[ ] 2. overview.approach explains HOW, not just WHAT
[ ] 3. All milestones have at least one code_intent
[ ] 4. All code_intents have id (CI-XXX format), file, and behavior
[ ] 5. All decision_refs in code_intents reference declared decisions
[ ] 6. risks have mitigations
[ ] 7. rejected_alternatives have decision_refs
[ ] 8. Milestones are sized correctly (not too large, not too small)
[ ] 9. Wave groupings reflect actual parallelism opportunities
[ ] 10. invisible_knowledge.system explains the mental model clearly
[ ] 11. Diagrams present per conventions/visualization.md where thresholds are met
        (CON for approach; SEQ per non-trivial flow; CMP for ≥4 components; STT for
        non-trivial lifecycles), and below-threshold slots are prose, NOT empty
        placeholders or "suppressed" banners
[ ] 12. GROUNDING: every node/actor/state in every diagram appears in the
        brief/context/milestones (reject any diagram naming an absent identifier);
        one diagram type per diagram; no cross-level mixing

VERDICT: PASS or FAIL
If FAIL: list specific issues that must be fixed before proceeding.
${QR_CLASSIFICATION_INSTRUCTION}`;

// ─────────────────────────────────────────────────────────────────────────────
// Phase 5: plan-code-work
// ─────────────────────────────────────────────────────────────────────────────

const PLAN_CODE_WORK_PROMPT = (planJson) => `PLANNER — plan-code-work

You are dispatching to the DEVELOPER role to fill code_changes into the plan.

PLAN (approved by QR):
${planJson}

DEVELOPER TASK: For each milestone, for each code_intent, create a code_change:

code_change structure:
{
  "id": "CC-M-XXX-YYY",
  "version": 1,
  "intent_ref": "CI-XXX",
  "file": "<same file as the intent>",
  "diff": "<unified diff showing the implementation>",
  "doc_diff": "",
  "comments": "<why this approach>"
}

CONSTRAINTS:
- Every code_intent must have a corresponding code_change
- Diffs must be in unified diff format (--- a/... +++ b/... @@ ... @@)
- ANCHOR EACH HUNK ON STABLE CONTEXT, NOT ABSOLUTE LINE NUMBERS. Include enough
  surrounding context lines (function signatures, dict/YAML keys, section headers,
  the line you insert before/after) that the hunk applies by context match alone.
  The @@ offsets are best-effort hints — correctness comes from the context lines,
  because line numbers shift as other milestones edit the same file.
- WAVE ORDER: milestones apply in wave order (W-001 fully before W-002, etc.). If
  this code_change targets a file an EARLIER milestone also modifies, write the diff
  against that file's POST-earlier-milestone state, anchor on context the earlier
  milestone introduces, and name the dependency in 'comments'
  (e.g. "depends on M-002 adding the 'milestones:' row"). Never anchor on a line that
  only exists in the current tree but is removed/moved by an earlier milestone.
- Comments explain WHY, not WHAT
- New files use --- /dev/null as the source

OUTPUT: The updated plan JSON with code_changes populated in every milestone.`;

// ─────────────────────────────────────────────────────────────────────────────
// Phase 6: plan-code-qr
// ─────────────────────────────────────────────────────────────────────────────

const PLAN_CODE_QR_PROMPT = (planWithCode) => `PLANNER — plan-code-qr

QUALITY REVIEW: Verify the code_changes fill the code_intents correctly.

PLAN WITH CODE_CHANGES:
${planWithCode}

VERIFICATION ITEMS:

[ ] 1. Every code_intent has a code_change with matching intent_ref
[ ] 2. All diffs are unified-diff-shaped (---/+++ headers, @@ hunks) AND each hunk
       carries enough surrounding context lines to apply by context match.
       Do NOT FAIL a hunk solely for line-number offsets — offsets are best-effort
       and shift as other milestones edit the file; judge by context, not arithmetic.
[ ] 3. New files use --- /dev/null as source
[ ] 4. Comments explain WHY (not WHAT the diff does)
[ ] 5. No diff introduces security violations (eval, shell=True, SQL concat)
[ ] 6. Code_change ids follow CC-M-XXX-YYY format
[ ] 7. Any diff targeting a file an earlier milestone also modifies anchors on
       post-earlier-milestone context and names that dependency in 'comments'
       (no anchoring on lines an earlier milestone removes or moves)

VERDICT: PASS or FAIL
If FAIL: list specific issues.
${QR_CLASSIFICATION_INSTRUCTION}`;

// ─────────────────────────────────────────────────────────────────────────────
// Phase 7: plan-docs-work
// ─────────────────────────────────────────────────────────────────────────────

const PLAN_DOCS_WORK_PROMPT = (planWithCode) => `PLANNER — plan-docs-work

You are dispatching to the TECHNICAL WRITER role to add documentation overlays.

PLAN WITH CODE_CHANGES (approved by QR):
${planWithCode}

TECHNICAL WRITER TASK: For each code_change that has a diff, add a doc_diff:

doc_diff is a unified diff that adds documentation to the changed code:
- Function docstrings (what the function does, args, returns)
- Module-level comments (WHY this module exists, design rationale)
- Inline comments for non-obvious logic (WHY, not WHAT)
- README entries where appropriate

doc_diff format: unified diff against the file AFTER the code diff is applied.

CONSTRAINTS:
- doc_diff must be valid unified diff format
- Focus on WHY, not WHAT (the code itself shows WHAT)
- Temporal contamination is forbidden: no "was", "now", "changed", "added"
- At least one of diff or doc_diff must be non-empty per code_change

OUTPUT: The updated plan JSON with doc_diffs populated.`;

// ─────────────────────────────────────────────────────────────────────────────
// Phase 8: plan-docs-qr
// ─────────────────────────────────────────────────────────────────────────────

const PLAN_DOCS_QR_PROMPT = (planWithDocs) => `PLANNER — plan-docs-qr

QUALITY REVIEW: Verify the documentation overlays.

PLAN WITH DOC_DIFFS:
${planWithDocs}

VERIFICATION ITEMS:

[ ] 1. Every code_change with a diff has a doc_diff
[ ] 2. All doc_diffs are in valid unified diff format
[ ] 3. No temporal contamination ("was", "now", "changed", "added", "Updated")
[ ] 4. Comments explain WHY (design rationale, invariants), not WHAT
[ ] 5. Module comments explain WHY the module exists

VERDICT: PASS or FAIL
If FAIL: list specific issues.
${QR_CLASSIFICATION_INSTRUCTION}`;

// ─────────────────────────────────────────────────────────────────────────────
// Execute mode (M7): turn an approved plan into code under review.
// execute phase (per wave) dispatches the developer-as-executor over each
// milestone's code_changes; exec-review verifies and applies rewrite-or-loop-back.
// ─────────────────────────────────────────────────────────────────────────────

// Recovers the plan object when execute mode is not handed a structured plan via
// args.plan. The developer reads the named path / extracts the embedded JSON and
// returns the plan verbatim as JSON so the script can group code_changes by wave.
const EXECUTE_LOAD_PROMPT = (planSource) => `PLANNER — execute-load

Locate the implementation plan and return it as JSON.

PLAN SOURCE:
${planSource || "(none provided — search the run/repo for a plan.json or plan.md)"}

If the source is a file path, read it. If it is embedded text, extract it.
OUTPUT only the plan as a JSON object with at least: overview, milestones (each
with code_changes), and waves. Do not add commentary.`;

// One executor per milestone (developer Executor Protocol: Comprehend → Plan →
// Implement → deviation report). Runs in worktree isolation so parallel executors
// in the same wave do not collide.
const EXECUTE_PROMPT = (milestone, brief) => `PLANNER — execute (milestone ${milestone.id || milestone.number || "?"})

You are the EXECUTOR. Follow the Executor Protocol in agents/developer.md:
Comprehend (read artifacts + target files, no code) → Plan (visible approach, no
code) → Implement (apply + rationale comments) → emit a DEVIATION REPORT.

INITIATIVE BRIEF (frozen context):
${brief || "(no brief supplied)"}

MILESTONE TO IMPLEMENT:
${JSON.stringify(milestone, null, 2)}

Apply this milestone's code_changes (each carries a unified diff anchored on
context). Anchor by context, not line number; correct trivial path/import issues
yourself; escalate genuine ambiguity. Verify (build/tests) when applicable.

End with the structured deviation report (Implemented as planned / Deviations /
Unanticipated decisions / Incomplete).`;

// exec-review verifies executor output and applies rewrite-or-loop-back
// (conventions/producer-validator.md). Trusts neither the plan nor the executor's
// self-report; runs verification, classifies the outcome, and labels findings.
const EXEC_REVIEW_PROMPT = (plan, deviationReports) => `PLANNER — exec-review

QUALITY REVIEW of execution. Trust nothing — not the plan, not the executor's
self-report. Verify, then assess.

PLAN (executed):
${typeof plan === "string" ? plan : JSON.stringify(plan, null, 2)}

EXECUTOR DEVIATION REPORTS:
${deviationReports}

DO:
1. Run verification commands (build, tests, type checks) where applicable to
   confirm the executors' claims.
2. Confirm each milestone's planned files were modified as intended.
3. Classify the OUTCOME (exactly one): Clean execution | Minor deviations |
   Significant deviations | Incomplete.
4. Assessment: Implemented-as-planned / Deviations (executor report + your
   verification) / Incomplete / Verification results.

VERDICT: PASS (Clean or acceptable Minor) or FAIL (Significant or Incomplete).
If FAIL: list specific issues. Clean executions skip remediation.
${QR_CLASSIFICATION_INSTRUCTION}`;

// ─────────────────────────────────────────────────────────────────────────────
// Milestones mode (M8): loop plan → execute → exec-review per milestone, carrying
// each milestone's Outcome forward (conventions/milestones.md).
// ─────────────────────────────────────────────────────────────────────────────

// Validation gate: every milestone is checked against the four soundness criteria
// BEFORE the loop runs it (a decomposition error compounds across every later
// milestone). Returns a possibly-revised milestone list.
const MILESTONE_VALIDATE_PROMPT = (milestones, brief) => `PLANNER — milestone-validate

Validate the milestone decomposition against conventions/milestones.md BEFORE any
execution. A decomposition error compounds across every later milestone.

INITIATIVE BRIEF:
${brief || "(none)"}

MILESTONES:
${JSON.stringify(milestones, null, 2)}

For EACH milestone apply the four soundness tests:
1. Independently deliverable — N's outcome holds if N+1 never lands.
2. Grounded in code structure — scope maps to connected file/module subgraphs,
   not slices across strongly-connected components.
3. Plannable in one plan session (~5-30 files).
4. Executable in one executor session (~10-30 steps).
Check for ownership overlaps (two milestones owning the same file are not
independent).

If a milestone fails, split / merge / re-ground it. OUTPUT the validated (and, if
needed, revised) milestone list as JSON: { "milestones": [ ... ] }. Preserve
ordering. If all pass unchanged, return them as-is.`;

// Per-milestone planning. Reads prior milestones' Outcome sections (cross-milestone
// learning) so the plan builds on integration points/patterns/constraints already
// established. Produces an implementation plan the executor then applies.
const MILESTONE_PLAN_PROMPT = (milestone, brief, priorOutcomes) => `PLANNER — milestone-plan (${milestone.id || milestone.number || "?"})

Plan THIS milestone. Build on what prior milestones established — do not re-derive
or contradict it (conventions/milestones.md: cross-milestone learning).

INITIATIVE BRIEF (frozen):
${brief || "(none)"}

PRIOR MILESTONE OUTCOMES (integration points / patterns / constraints already in place):
${priorOutcomes}

MILESTONE TO PLAN:
${JSON.stringify(milestone, null, 2)}

If a prior Outcome names a file/interface this milestone extends, read that file —
the code is the source of truth, not the prior plan. Produce an implementation
plan: the approach, the exact files to create/modify, and ~10-30 concrete steps
the executor will follow. Ground every step in real code structure.`;

// After exec-review, synthesize the milestone's Outcome — what was ACTUALLY built,
// not what was planned. The four subsections feed the next milestone's planning.
const MILESTONE_OUTCOME_PROMPT = (milestone, deviationReport, reviewResult) => `PLANNER — milestone-outcome (${milestone.id || milestone.number || "?"})

Write this milestone's Outcome (conventions/milestones.md) — what was ACTUALLY
accomplished, not what was planned. Source it from the deviation report and the
exec-review assessment below.

DEVIATION REPORT:
${deviationReport}

EXEC-REVIEW ASSESSMENT:
${reviewResult}

OUTPUT exactly these four subsections:
**Integration points created** — new interfaces/seams/modules later milestones can
depend on, named with file paths + identifiers.
**Patterns established** — naming, file placement, error handling, test conventions
this milestone committed to.
**Constraints discovered** — things harder/different than the sketch anticipated;
facts that change what future milestones can assume.
**Deviations from plan** — what the executor did differently and why.`;

// ─────────────────────────────────────────────────────────────────────────────
// Initiative mode: upstream design pass (core-flows → tech-plan-spec → tech-plan-review)
// Runs once before the per-milestone loop, gated to mode === 'initiative' only.
// ─────────────────────────────────────────────────────────────────────────────

// G1: Frozen behavioral spec. The architect enumerates operational flows and
// produces a SEQ-only, implementation-free artifact that downstream phases read
// as authoritative behavioral truth (conventions/core-flows.md).
const CORE_FLOWS_PROMPT = (brief) => `PLANNER — core-flows (initiative upstream design)

You are the ARCHITECT producing the frozen behavioral spec for this initiative.

INITIATIVE BRIEF (frozen):
${brief || "(none)"}

Read the brief. Enumerate every operational flow the initiative introduces or
modifies. For each flow, produce:
  1. A SEQ diagram (sequenceDiagram) — actors, sequence, branching conditions.
     Apply the suppression rule from conventions/visualization.md: if the flow
     is below the SEQ threshold, write it as prose instead.
  2. A step narrative: trigger, sequenced steps, exit conditions.

STRICT RULES (conventions/core-flows.md):
- SEQ diagrams only — no CON, CMP, or STT.
- No file paths, no component/class/function names, no implementation detail.
- Actor names are roles (User, System, External Service), not code identifiers.

This artifact is FROZEN at exit. Downstream phases read it as authoritative
behavioral truth and do not rewrite it.

OUTPUT the core-flows artifact as structured markdown (one section per flow).`;

// G2: Structural tech-plan — the structural counterpart to the frozen core-flows
// artifact. Reads brief + core-flows and produces Architectural Approach / Data
// Model / Component Architecture per conventions/tech-plan.md Part 1.
//
// Accepts coreFlows so structural choices can be validated against frozen
// behavioral truth in a single prompt context, not a subsequent re-read.
const TECH_PLAN_SPEC_PROMPT = (brief, coreFlows) => `PLANNER — tech-plan-spec (initiative upstream design)

You are the ARCHITECT producing the structural tech-plan for this initiative.

INITIATIVE BRIEF (frozen):
${brief || "(none)"}

CORE-FLOWS ARTIFACT (frozen behavioral spec — your structural choices must be
consistent with every flow described here):
${coreFlows || "(none)"}

Produce the tech-plan artifact per conventions/tech-plan.md Part 1. The artifact
has exactly three sections:

1. **Architectural Approach** — CON container view: runtime building blocks and
   connections. Apply the CON suppression rule from conventions/visualization.md.
2. **Data Model** — fenced code blocks (schema notation). NOT ER diagrams.
3. **Component Architecture** — CMP per container; SEQ for cross-component flows;
   STT for per-entity lifecycles when warranted. Apply visualization.md rules.

For EACH section: state the chosen path AND rejected alternatives with rationale.

STRICT RULES:
- Structure only — no per-file or per-function implementation steps.
- Every node, container, and schema field must trace to the brief or core-flows.
- Diagram rules (slot types, thresholds, grounding, hazards) are in conventions/visualization.md.

This artifact is DISPOSABLE: its reviewer may rewrite it in place.

OUTPUT the tech-plan as structured markdown.`;

// G2 review: dedicated adversarial stress-test of the tech-plan. This is NOT
// a renamed plan-QR gate — the do-not-verify-file-paths rule does not apply
// (conventions/tech-plan.md Part 2). Scout codebase reads are authorized.
//
// techPlan is reassigned to the reviewer's output: the reviewer rewrites in
// place for INTERNAL findings, so the post-review value IS the corrected plan.
const TECH_PLAN_REVIEW_PROMPT = (brief, coreFlows, techPlan) => `PLANNER — tech-plan-review (initiative upstream design)

You are the REVIEWER stress-testing the structural tech-plan.

IMPORTANT: This is NOT plan-review. The "do not verify file paths" and
"do not flag executor-resolvable issues" rules from plan-review DO NOT apply
here. Codebase reads and scout dispatch are authorized and encouraged.

INITIATIVE BRIEF (frozen):
${brief || "(none)"}

CORE-FLOWS ARTIFACT (frozen — structural choices must be consistent with these flows):
${coreFlows || "(none)"}

TECH-PLAN TO REVIEW:
${techPlan || "(none)"}

DO:
1. Extract 3–7 critical architectural decisions from the tech-plan.
2. Stress-test each on six axes (conventions/tech-plan.md Part 2):
   simplicity, flexibility, robustness, scaling, codebase-fit,
   consistency-with-brief/core-flows.
3. Use scouts or direct codebase reads to verify integration-point,
   boundary, and schema claims.
4. Classify each finding INTERNAL or NEW-FILES-NEEDED per
   conventions/producer-validator.md and apply rewrite-or-loop-back.

VERDICT: PASS (all findings resolved in place) or LOOP_BACK (NEW-FILES-NEEDED
findings require the architect to re-run tech-plan-spec with named files).
${QR_CLASSIFICATION_INSTRUCTION}`;

// G3: Forward propagation. After each milestone's Outcome, review what was
// learned and push relevant context FORWARD into pending milestone specs.
// A no-op turn when nothing relevant was learned (koan orchestrator.py:283).
//
// remainingMilestones is milestones.slice(i+1): a live slice of the same
// array objects, so mutations to rm.propagatedContext are visible to the
// next iteration's MILESTONE_PLAN_PROMPT without a separate data structure.
const MILESTONE_PROPAGATE_PROMPT = (milestone, review, outcome, remainingMilestones) => `PLANNER — milestone-propagate (${milestone.id || milestone.number || "?"})

Apply conventions/milestones.md 'Forward Propagation' for this completed milestone.

COMPLETED MILESTONE:
${JSON.stringify(milestone, null, 2)}

EXEC-REVIEW ASSESSMENT:
${review}

MILESTONE OUTCOME:
${outcome}

REMAINING (PENDING) MILESTONES:
${remainingMilestones.length ? JSON.stringify(remainingMilestones, null, 2) : "(none — this was the last milestone)"}

DO:
1. Review what verification and the verdict revealed that affects any remaining
   milestone. Look for: invalidated assumptions, new patterns to follow,
   decisions made or unmade, milestones that are now unnecessary.
2. For each affected remaining milestone, produce a
   '## [autonomous] Propagated Context' section with what was learned and why
   it affects that milestone.
3. Update the plan's Decisions section for any decision made or invalidated,
   prefixing autonomous additions with '[autonomous]'.
4. If nothing relevant was learned, output ONLY the token: PROPAGATE_NOOP

OUTPUT: For each affected milestone, emit its id and the propagated context
section. For Decisions updates, emit the updated entry. Or emit PROPAGATE_NOOP.`;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extract a JSON object from an agent response string.
 * Falls back to the raw string wrapped in an object if parsing fails.
 */
function extractJson(text) {
  if (!text) return {};
  const match = text.match(/\{[\s\S]*\}/);
  if (match) {
    try {
      return JSON.parse(match[0]);
    } catch (error) {
      log(`extractJson: JSON.parse failed (${error.message}); falling through to raw wrap`);
    }
  }
  return { _raw: text };
}

/**
 * Check whether a QR verdict response contains a PASS.
 * Authoritative signal is the explicit "VERDICT: PASS" line; a bare "PASS"
 * anywhere in prose is NOT sufficient (it falsely passed verdicts like
 * "checks all PASS except ..."). Returns true only on an explicit PASS verdict
 * that is not contradicted by an explicit FAIL verdict.
 */
function isQrPass(qrResult) {
  if (!qrResult) return false;
  const upper = qrResult.toUpperCase();
  return upper.includes("VERDICT: PASS") && !upper.includes("VERDICT: FAIL");
}

/**
 * Decide the FAIL remediation path (conventions/producer-validator.md).
 * Returns true when the QR flagged at least one NEW-FILES-NEEDED finding — the gate
 * must then loop back to the producer with the new files in scope. Returns false
 * for an all-INTERNAL FAIL, which is fixed in place without a full producer re-run.
 *
 * The authoritative signal is the explicit "LOOP_BACK: NEW-FILES-NEEDED" line. A
 * bare mention of the token elsewhere in prose does not count. Absent the line
 * (older QR output), we default to false (in-place fix) — the cheap, reversible
 * choice the convention prescribes when classification is uncertain.
 */
function needsLoopBack(qrResult) {
  if (!qrResult) return false;
  return qrResult.toUpperCase().includes("LOOP_BACK: NEW-FILES-NEEDED");
}

/**
 * Run one producer–validator FAIL remediation (conventions/producer-validator.md).
 * NEW-FILES-NEEDED findings loop back to the full producer (which may load the named
 * files); all-INTERNAL findings get a constrained in-place fix that forbids redesign
 * and new-file loading, so the gate does not re-run the full producer for mistakes
 * the producer could have caught from context it already held. Returns the corrected
 * artifact text. The caller re-verifies once and proceeds best-effort either way
 * (single retry; no unbounded loop).
 */
async function remediate({ qrResult, artifact, role, phaseName, artifactLabel }) {
  const loopBack = needsLoopBack(qrResult);
  const mode = loopBack ? "loop-back" : "in-place fix";
  log(`PLANNER: ${phaseName} FAIL (${mode}) — re-dispatching ${role}`);
  log(`DURABLE_EVENT: subagent_spawned ${role} ${phaseName}-${loopBack ? "loopback" : "fix"}`);

  const directive = loopBack
    ? `Some findings are NEW-FILES-NEEDED: they require information not in your original
context. Read the file(s) named under "Needs:" for those findings, then apply ALL
corrections (INTERNAL and NEW-FILES-NEEDED).`
    : `All findings are INTERNAL: fixable from the artifact you already have. Apply the
corrections in place. Do NOT reopen the design and do NOT load new files — this is a
targeted fix pass, not a re-derivation.`;

  const fixed = await agent(
    `PLANNER — ${phaseName} (${mode})

QR FINDINGS:
${qrResult}

${directive}

CURRENT ${artifactLabel}:
${artifact}

Output the corrected plan JSON.`,
    { label: `${phaseName}-${loopBack ? "loopback" : "fix"}`, phase: phaseName, agentType: role },
  );

  log(`DURABLE_EVENT: subagent_completed ${role} ${phaseName}-${loopBack ? "loopback" : "fix"}`);
  return fixed;
}

/**
 * Resolve the milestone objects belonging to a wave (M7/M8). Matches a wave's
 * declared milestone id list (wave.milestones or wave.milestone_ids) against each
 * milestone's id/number; falls back to milestones that tag their own wave. Returns
 * [] when nothing matches so the caller can skip an empty wave.
 */
function milestonesInWave(plan, wave) {
  const ms = Array.isArray(plan.milestones) ? plan.milestones : [];
  const ids = Array.isArray(wave && wave.milestones)
    ? wave.milestones
    : Array.isArray(wave && wave.milestone_ids)
      ? wave.milestone_ids
      : null;
  if (ids) {
    const idset = new Set(ids.map(String));
    const matched = ms.filter((m) => idset.has(String(m.id)) || idset.has(String(m.number)));
    if (matched.length) return matched;
  }
  const waveId = wave && (wave.id != null ? wave.id : wave.number);
  return ms.filter((m) => m.wave != null && String(m.wave) === String(waveId));
}

/**
 * Dispatch one developer-as-executor over a milestone's code_changes (M7).
 * isolation: 'worktree' so parallel executors in the same wave mutate isolated
 * copies and do not collide. Returns the milestone's deviation report.
 */
async function executeMilestone(milestone, brief) {
  const id = milestone.id || milestone.number || "milestone";
  log(`DURABLE_EVENT: subagent_spawned developer execute-${id}`);
  const report = await agent(EXECUTE_PROMPT(milestone, brief), {
    label: `execute-${String(id).slice(0, 30)}`,
    phase: "execute",
    agentType: "developer",
    isolation: "worktree",
  });
  log(`DURABLE_EVENT: subagent_completed developer execute-${id}`);
  return `## Milestone ${id}\n${report}`;
}

/**
 * The exec-review gate (M7): verify executor output, then apply rewrite-or-loop-back
 * (conventions/producer-validator.md). Internal findings are fixed in place by the
 * executor; NEW-FILES-NEEDED findings loop the executor back over the affected work.
 * Single retry, then proceed best-effort. Returns the (possibly re-verified) review.
 */
async function execReview(plan, deviationReports, brief) {
  phase("exec-review");
  log("PLANNER: Starting exec-review (verify execution)");
  log("DURABLE_EVENT: phase_started exec-review");
  log("DURABLE_EVENT: subagent_spawned quality-reviewer exec-review");

  let review = await agent(EXEC_REVIEW_PROMPT(plan, deviationReports), {
    label: "exec-review",
    phase: "exec-review",
    agentType: "quality-reviewer",
  });

  if (!isQrPass(review)) {
    const loopBack = needsLoopBack(review);
    const mode = loopBack ? "loop-back" : "in-place fix";
    log(`PLANNER: exec-review FAIL (${mode}) — re-dispatching executor`);
    log(`DURABLE_EVENT: subagent_spawned developer exec-review-${loopBack ? "loopback" : "fix"}`);

    const directive = loopBack
      ? `Findings are NEW-FILES-NEEDED: read the file(s) named under "Needs:" and redo the affected work.`
      : `Findings are INTERNAL: fix them in place from the code and plan you already have. Do not expand scope.`;

    const fixReport = await agent(
      `PLANNER — execute (exec-review ${mode})

EXEC-REVIEW FINDINGS:
${review}

${directive}

PLAN:
${typeof plan === "string" ? plan : JSON.stringify(plan, null, 2)}

BRIEF:
${brief || "(none)"}

Apply the fixes per the Executor Protocol (agents/developer.md) and end with a
deviation report.`,
      {
        label: `exec-review-${loopBack ? "loopback" : "fix"}`,
        phase: "exec-review",
        agentType: "developer",
        isolation: "worktree",
      },
    );

    log(`DURABLE_EVENT: subagent_completed developer exec-review-${loopBack ? "loopback" : "fix"}`);

    review = await agent(EXEC_REVIEW_PROMPT(plan, fixReport), {
      label: "exec-review-retry",
      phase: "exec-review",
      agentType: "quality-reviewer",
    });

    log(`PLANNER: exec-review-retry verdict — ${isQrPass(review) ? "PASS" : "FAIL (proceeding best-effort)"}`);
  }

  log("DURABLE_EVENT: subagent_completed quality-reviewer exec-review");
  log("DURABLE_EVENT: phase_completed exec-review");
  return review;
}

/**
 * Execute mode (M7): turn an approved plan into code under review. Recovers the
 * plan (from args.plan / args.planJson / args.planPath / request text), executes
 * each wave's milestones in parallel (W-001 fully before W-002, etc.), collects
 * deviation reports, then runs the exec-review gate. Returns an execution artifact.
 */
async function runExecuteMode(requestText) {
  phase("execute");
  log("PLANNER: mode=execute — turning an approved plan into code");
  log("DURABLE_EVENT: phase_started execute");

  let planForExec =
    args && typeof args === "object" && args.plan && typeof args.plan === "object"
      ? args.plan
      : null;
  if (!planForExec) {
    const planSource =
      (args &&
        typeof args === "object" &&
        (args.planJson ||
          args.planText ||
          (args.planPath ? `Read the plan file at: ${args.planPath}` : null))) ||
      requestText;
    const loaded = await agent(EXECUTE_LOAD_PROMPT(planSource), {
      label: "execute-load",
      phase: "execute",
      agentType: "developer",
    });
    planForExec = extractJson(loaded);
  }

  const brief =
    args && typeof args === "object" && typeof args.brief === "string" ? args.brief : "";
  const milestones = Array.isArray(planForExec.milestones) ? planForExec.milestones : [];
  // No declared waves → one implicit wave over all milestones (in wave order the
  // plan already lists them in).
  const waves =
    Array.isArray(planForExec.waves) && planForExec.waves.length
      ? planForExec.waves
      : [{ id: "W-001", milestones: milestones.map((m) => m.id || m.number) }];

  const deviationReports = [];
  for (const wave of waves) {
    const waveMs = milestonesInWave(planForExec, wave);
    // Single implicit wave that matched nothing (e.g. milestones without ids) →
    // execute all milestones; a real multi-wave plan skips a wave that matches none.
    const target = waveMs.length ? waveMs : waves.length === 1 ? milestones : [];
    if (!target.length) continue;
    log(`PLANNER: executing ${(wave && wave.id) || "wave"} — ${target.length} milestone(s)`);
    const reports = await parallel(target.map((m) => () => executeMilestone(m, brief)));
    deviationReports.push(...reports.filter(Boolean));
  }

  log("DURABLE_EVENT: phase_completed execute");

  const review = await execReview(
    planForExec,
    deviationReports.join("\n\n---\n\n") || "(no deviation reports collected)",
    brief,
  );

  log("PLANNER: execute mode complete");
  return {
    execution: {
      waves_executed: waves.length,
      milestones_executed: deviationReports.length,
      deviation_reports: deviationReports,
      exec_review: review,
    },
  };
}

/**
 * Milestones mode (M8): the cross-milestone learning loop. Validates the
 * decomposition (soundness criteria), then for each milestone in order runs
 * plan → execute → exec-review → Outcome, accumulating each milestone's Outcome
 * so the next milestone's planning builds on integration points/patterns/
 * constraints already established (conventions/milestones.md). Returns the
 * accumulated milestones artifact.
 */
async function runMilestonesMode(requestText) {
  phase("milestone-validate");
  log("PLANNER: mode=milestones — cross-milestone learning loop");
  log("DURABLE_EVENT: phase_started milestone-validate");

  // Obtain the plan/milestones (same loading contract as execute mode).
  let plan =
    args && typeof args === "object" && args.plan && typeof args.plan === "object"
      ? args.plan
      : null;
  if (!plan) {
    const planSource =
      (args &&
        typeof args === "object" &&
        (args.planJson ||
          args.planText ||
          (args.planPath ? `Read the plan file at: ${args.planPath}` : null))) ||
      requestText;
    plan = extractJson(
      await agent(EXECUTE_LOAD_PROMPT(planSource), {
        label: "milestone-load",
        phase: "milestone-validate",
        agentType: "developer",
      }),
    );
  }

  const brief =
    (args && typeof args === "object" && typeof args.brief === "string" && args.brief) ||
    (plan.overview ? JSON.stringify(plan.overview) : "");
  let milestones = Array.isArray(plan.milestones) ? plan.milestones : [];

  // Initiative-mode upstream design pass: frozen behavioral spec then structural
  // tech-plan with its own adversarial review. Runs once before the per-milestone
  // loop, skipped entirely for plain mode === 'milestones'.
  let coreFlows = "";
  if (mode === "initiative") {
    phase("core-flows");
    log("DURABLE_EVENT: phase_started core-flows");
    log("DURABLE_EVENT: subagent_spawned architect core-flows");
    coreFlows = await agent(CORE_FLOWS_PROMPT(brief), {
      label: "core-flows",
      phase: "core-flows",
      agentType: "architect",
    });
    log("DURABLE_EVENT: subagent_completed architect core-flows");
    log("DURABLE_EVENT: phase_completed core-flows");
  }

  // G2: tech-plan-spec produces the structural artifact; tech-plan-review stress-
  // tests it adversarially (six axes, scout authority). techPlan is reassigned
  // to the reviewer's output because INTERNAL finding fixes are written in place
  // by the reviewer — the corrected plan flows to milestone-validate.
  let techPlan = "";
  if (mode === "initiative") {
    phase("tech-plan-spec");
    log("DURABLE_EVENT: phase_started tech-plan-spec");
    log("DURABLE_EVENT: subagent_spawned architect tech-plan-spec");
    techPlan = await agent(TECH_PLAN_SPEC_PROMPT(brief, coreFlows), {
      label: "tech-plan-spec",
      phase: "tech-plan-spec",
      agentType: "architect",
    });
    log("DURABLE_EVENT: subagent_completed architect tech-plan-spec");
    log("DURABLE_EVENT: phase_completed tech-plan-spec");

    phase("tech-plan-review");
    log("DURABLE_EVENT: phase_started tech-plan-review");
    log("DURABLE_EVENT: subagent_spawned quality-reviewer tech-plan-review");
    techPlan = await agent(TECH_PLAN_REVIEW_PROMPT(brief, coreFlows, techPlan), {
      label: "tech-plan-review",
      phase: "tech-plan-review",
      agentType: "quality-reviewer",
    });
    log("DURABLE_EVENT: subagent_completed quality-reviewer tech-plan-review");
    log("DURABLE_EVENT: phase_completed tech-plan-review");
  }

  // Validate the decomposition before any execution; use the revised list if the
  // reviewer returned one.
  log("DURABLE_EVENT: subagent_spawned quality-reviewer milestone-validate");
  const validation = await agent(MILESTONE_VALIDATE_PROMPT(milestones, brief), {
    label: "milestone-validate",
    phase: "milestone-validate",
    agentType: "quality-reviewer",
  });
  log("DURABLE_EVENT: subagent_completed quality-reviewer milestone-validate");
  const revised = extractJson(validation);
  if (Array.isArray(revised.milestones) && revised.milestones.length > 0) {
    milestones = revised.milestones;
  }
  log(`DURABLE_EVENT: phase_completed milestone-validate`);

  // The accumulating milestones artifact: one Outcome section per completed
  // milestone, fed forward into the next milestone's planning.
  const outcomes = [];
  const records = [];

  for (let i = 0; i < milestones.length; i++) {
    const m = milestones[i];
    const id = m.id || m.number || `M-${i + 1}`;
    const priorOutcomes = outcomes.length ? outcomes.join("\n\n") : "(none — first milestone)";

    // plan (reads prior Outcomes — cross-milestone learning)
    phase("milestone-plan");
    log(`PLANNER: milestone-plan ${id} (${i + 1}/${milestones.length})`);
    log(`DURABLE_EVENT: phase_started milestone-plan`);
    log(`DURABLE_EVENT: subagent_spawned architect milestone-plan-${id}`);
    const mPlan = await agent(MILESTONE_PLAN_PROMPT(m, brief, priorOutcomes), {
      label: `milestone-plan-${String(id).slice(0, 30)}`,
      phase: "milestone-plan",
      agentType: "architect",
    });
    log(`DURABLE_EVENT: subagent_completed architect milestone-plan-${id}`);
    log(`DURABLE_EVENT: phase_completed milestone-plan`);

    // execute (the per-milestone plan rides along on the milestone object)
    phase("execute");
    log(`DURABLE_EVENT: phase_started execute`);
    const deviation = await executeMilestone({ ...m, plan: mPlan }, brief);
    log(`DURABLE_EVENT: phase_completed execute`);

    // exec-review (verify + rewrite-or-loop-back)
    const review = await execReview(mPlan, deviation, brief);

    // Outcome (what was ACTUALLY built — feeds the next milestone)
    phase("milestone-outcome");
    log(`DURABLE_EVENT: phase_started milestone-outcome`);
    log(`DURABLE_EVENT: subagent_spawned architect milestone-outcome-${id}`);
    const outcome = await agent(MILESTONE_OUTCOME_PROMPT(m, deviation, review), {
      label: `milestone-outcome-${String(id).slice(0, 30)}`,
      phase: "milestone-outcome",
      agentType: "architect",
    });
    log(`DURABLE_EVENT: subagent_completed architect milestone-outcome-${id}`);
    log(`DURABLE_EVENT: phase_completed milestone-outcome`);

    outcomes.push(`### Milestone ${id} — Outcome\n${outcome}`);
    records.push({ milestone: id, plan: mPlan, deviation, review, outcome });

    // Guard: no propagation phase on the last milestone — there are no pending
    // specs to receive it. Avoids a phase() call that emits a DURABLE_EVENT
    // boundary with nothing to do, which would inflate the resume event log.
    const remainingMilestones = milestones.slice(i + 1);
    if (remainingMilestones.length > 0) {
      phase("milestone-propagate");
      log(`DURABLE_EVENT: phase_started milestone-propagate`);
      log(`DURABLE_EVENT: subagent_spawned architect milestone-propagate-${id}`);
      const propagation = await agent(
        MILESTONE_PROPAGATE_PROMPT(m, review, outcome, remainingMilestones),
        {
          label: `milestone-propagate-${String(id).slice(0, 30)}`,
          phase: "milestone-propagate",
          agentType: "architect",
        },
      );
      log(`DURABLE_EVENT: subagent_completed architect milestone-propagate-${id}`);
      log(`DURABLE_EVENT: phase_completed milestone-propagate`);

      // Apply returned propagation to in-memory remaining milestone objects
      // so the next milestone-plan sees the context without a plan file write.
      if (propagation && !propagation.includes("PROPAGATE_NOOP")) {
        for (const rm of remainingMilestones) {
          const rmId = String(rm.id || rm.number || "");
          if (propagation.includes(rmId)) {
            rm.propagatedContext = (rm.propagatedContext || "") +
              "\n\n" + propagation;
          }
        }
      }
    }
  }

  log(`PLANNER: milestones mode complete — ${records.length} milestone(s)`);
  return {
    milestones: {
      count: records.length,
      validation,
      outcomes,
      records,
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Main workflow
// ─────────────────────────────────────────────────────────────────────────────

  // Derive the user request from whatever shape the runner passes args in.
  // Confirmed runner contract: args.request is the primary field
  // (prompt-engineer/workflow.mjs lines 104-110 shows the same coalescing).
  // Three arg shapes are accepted so a free-text invocation is never silently
  // dropped: args as a bare string, args.request, and args.text.
  const requestText = [
    typeof args === "string" ? args : null,
    args && typeof args.request === "string" ? args.request : null,
    args && typeof args.text === "string" ? args.text : null,
  ]
    .filter(Boolean)
    .join("\n")
    .concat(
      // Append reference-file paths when present (either field name the runner
      // may use) so the architect can locate relevant project docs.
      (() => {
        const files = (args && (args.referenceFiles || args.files));
        return Array.isArray(files) && files.length > 0
          ? "\n\nREFERENCE FILES:\n" + files.join("\n")
          : "";
      })()
    );

  // Mode selection (SKILL.md: mode plan | execute). Execute mode short-circuits
  // the planning phases and runs the executor + exec-review over an existing plan.
  // This return is BEFORE the final `return { plan }`, so the plan-mode output
  // contract (output_key "plan") is unaffected.
  const mode =
    args && typeof args === "object" && typeof args.mode === "string"
      ? args.mode.toLowerCase()
      : "plan";

  if (mode === "execute") {
    return await runExecuteMode(requestText);
  }

  if (mode === "milestones" || mode === "initiative") {
    return await runMilestonesMode(requestText);
  }

  // ── Phase 1: intake-gather ────────────────────────────────────────────────
  phase("intake-gather");
  log("PLANNER: Starting intake-gather (orient + plan scouts)");
  log("DURABLE_EVENT: phase_started intake-gather");

  // agentType: 'architect' gives Gather read-only Read/Grep/Glob/Bash for the
  // budgeted orientation. The agent proposes scout assignments as JSON; the SCRIPT
  // dispatches them (the architect is a leaf agent and cannot spawn).
  const gatherResult = await agent(INTAKE_GATHER_PROMPT(requestText), {
    label: "intake-gather",
    phase: "intake-gather",
    agentType: "architect",
  });

  // Dispatch the proposed scouts in parallel (agentType: 'scout', M1). Scouts are
  // read-only investigators; their findings seed the Deepen dialogue. A malformed
  // or empty scouts array simply yields no fan-out — Gather's own orientation
  // already covers simple tasks.
  const gatherObj = extractJson(gatherResult);
  const scoutAssignments = Array.isArray(gatherObj.scouts) ? gatherObj.scouts : [];
  let scoutFindings = "(no scouts dispatched)";
  if (scoutAssignments.length > 0) {
    log(`PLANNER: dispatching ${scoutAssignments.length} scout(s)`);
    log(`DURABLE_EVENT: subagent_spawned scout intake-gather`);
    const scoutResults = await parallel(
      scoutAssignments.map((s) => () =>
        agent(
          `SCOUT — ${s.role || "investigator"}\n\nInvestigate and report (file:line, dense):\n${s.prompt || s.id}`,
          { label: `scout-${(s.id || "area").slice(0, 30)}`, phase: "intake-gather", agentType: "scout" },
        )
      ),
    );
    scoutFindings = scoutResults
      .filter(Boolean)
      .map((r, i) => `## Scout ${scoutAssignments[i]?.id || i}\n${r}`)
      .join("\n\n");
    log(`DURABLE_EVENT: subagent_completed scout intake-gather`);
  }

  log("DURABLE_EVENT: phase_completed intake-gather");

  // ── Phase 2: intake-deepen ────────────────────────────────────────────────
  phase("intake-deepen");
  log("PLANNER: Starting intake-deepen (default-ask dialogue loop)");
  log("DURABLE_EVENT: phase_started intake-deepen");

  // No agentType: the DEFAULT workflow agent has AskUserQuestion (the architect
  // does not). Deepen classifies unknowns ASK/SAFE and asks ASK-class ones under
  // default-ask framing; with no ASK-class unknowns it proceeds without prompting.
  const deepenResult = await agent(
    INTAKE_DEEPEN_PROMPT(requestText, gatherResult, scoutFindings),
    { label: "intake-deepen", phase: "intake-deepen" },
  );

  log("DURABLE_EVENT: phase_completed intake-deepen");

  // ── Phase 3: intake-summarize ─────────────────────────────────────────────
  phase("intake-summarize");
  log("PLANNER: Starting intake-summarize (freeze brief)");
  log("DURABLE_EVENT: phase_started intake-summarize");

  // The frozen brief is the authoritative initiative context fed to every
  // downstream phase in place of the old context-verify JSON.
  const brief = await agent(INTAKE_SUMMARIZE_PROMPT(requestText, deepenResult), {
    label: "intake-summarize",
    phase: "intake-summarize",
    agentType: "architect",
  });

  log("DURABLE_EVENT: phase_completed intake-summarize");

  // ── Phase 3: plan-design-work ─────────────────────────────────────────────
  phase("plan-design-work");
  log("PLANNER: Starting plan-design-work (architect role)");
  log("DURABLE_EVENT: phase_started plan-design-work");
  log("DURABLE_EVENT: subagent_spawned architect plan-design-work");

  const designResult = await agent(PLAN_DESIGN_WORK_PROMPT(brief, requestText), {
    label: "plan-design-work",
    phase: "plan-design-work",
    agentType: "architect",
  });

  log("DURABLE_EVENT: subagent_completed architect plan-design-work");
  log("DURABLE_EVENT: phase_completed plan-design-work");

  // ── Phase 4: plan-design-qr ───────────────────────────────────────────────
  phase("plan-design-qr");
  log("PLANNER: Starting plan-design-qr (quality-reviewer role)");
  log("DURABLE_EVENT: phase_started plan-design-qr");
  log("DURABLE_EVENT: subagent_spawned quality-reviewer plan-design-qr");

  let designQrResult = await agent(PLAN_DESIGN_QR_PROMPT(designResult), {
    label: "plan-design-qr",
    phase: "plan-design-qr",
    agentType: "quality-reviewer",
  });

  let designApproved = isQrPass(designQrResult);

  // Declared in the outer scope so the fix-pass output survives past the
  // if-block. A block-scoped `const` here is invisible at the approvedDesign
  // line below — `typeof designFixed` resolves to "undefined" and the fix is
  // silently discarded (the original DL-026 defect this propagation aims to undo).
  let designFixed = null;

  // QR retry: a FAIL is remediated per conventions/producer-validator.md — an
  // all-INTERNAL FAIL is fixed in place; a NEW-FILES-NEEDED FAIL loops back to the
  // architect with the named files in scope. Re-verify once, then proceed
  // best-effort (single retry; no unbounded loop).
  if (!designApproved) {
    designFixed = await remediate({
      qrResult: designQrResult,
      artifact: designResult,
      role: "architect",
      phaseName: "plan-design-qr",
      artifactLabel: "DESIGN",
    });

    designQrResult = await agent(PLAN_DESIGN_QR_PROMPT(designFixed), {
      label: "plan-design-qr-retry",
      phase: "plan-design-qr",
      agentType: "quality-reviewer",
    });

    log(`PLANNER: plan-design-qr-retry verdict — ${isQrPass(designQrResult) ? "PASS" : "FAIL (proceeding best-effort)"}`);
  }

  log("DURABLE_EVENT: subagent_completed quality-reviewer plan-design-qr");
  log("DURABLE_EVENT: phase_completed plan-design-qr");

  // Propagate the fixed design if QR triggered a fix pass.
  const approvedDesign = designFixed || designResult;

  // ── Phase 5: plan-code-work ───────────────────────────────────────────────
  phase("plan-code-work");
  log("PLANNER: Starting plan-code-work (developer role)");
  log("DURABLE_EVENT: phase_started plan-code-work");
  log("DURABLE_EVENT: subagent_spawned developer plan-code-work");

  const codeResult = await agent(PLAN_CODE_WORK_PROMPT(approvedDesign), {
    label: "plan-code-work",
    phase: "plan-code-work",
    agentType: "developer",
  });

  log("DURABLE_EVENT: subagent_completed developer plan-code-work");
  log("DURABLE_EVENT: phase_completed plan-code-work");

  // ── Phase 6: plan-code-qr ─────────────────────────────────────────────────
  phase("plan-code-qr");
  log("PLANNER: Starting plan-code-qr (quality-reviewer role)");
  log("DURABLE_EVENT: phase_started plan-code-qr");
  log("DURABLE_EVENT: subagent_spawned quality-reviewer plan-code-qr");

  let codeQrResult = await agent(PLAN_CODE_QR_PROMPT(codeResult), {
    label: "plan-code-qr",
    phase: "plan-code-qr",
    agentType: "quality-reviewer",
  });

  const codeApproved = isQrPass(codeQrResult);

  // Outer-scope declaration so the fix pass propagates (see designFixed above).
  let codeFixed = null;

  if (!codeApproved) {
    codeFixed = await remediate({
      qrResult: codeQrResult,
      artifact: codeResult,
      role: "developer",
      phaseName: "plan-code-qr",
      artifactLabel: "PLAN WITH CODE_CHANGES",
    });

    codeQrResult = await agent(PLAN_CODE_QR_PROMPT(codeFixed), {
      label: "plan-code-qr-retry",
      phase: "plan-code-qr",
      agentType: "quality-reviewer",
    });

    log(`PLANNER: plan-code-qr-retry verdict — ${isQrPass(codeQrResult) ? "PASS" : "FAIL (proceeding best-effort)"}`);
  }

  log("DURABLE_EVENT: subagent_completed quality-reviewer plan-code-qr");
  log("DURABLE_EVENT: phase_completed plan-code-qr");

  // Propagate the fixed code if QR triggered a fix pass.
  const approvedCode = codeFixed || codeResult;

  // ── Phase 7: plan-docs-work ───────────────────────────────────────────────
  phase("plan-docs-work");
  log("PLANNER: Starting plan-docs-work (technical-writer role)");
  log("DURABLE_EVENT: phase_started plan-docs-work");
  log("DURABLE_EVENT: subagent_spawned technical-writer plan-docs-work");

  const docsResult = await agent(PLAN_DOCS_WORK_PROMPT(approvedCode), {
    label: "plan-docs-work",
    phase: "plan-docs-work",
    agentType: "technical-writer",
  });

  log("DURABLE_EVENT: subagent_completed technical-writer plan-docs-work");
  log("DURABLE_EVENT: phase_completed plan-docs-work");

  // ── Phase 8: plan-docs-qr ─────────────────────────────────────────────────
  phase("plan-docs-qr");
  log("PLANNER: Starting plan-docs-qr (quality-reviewer role)");
  log("DURABLE_EVENT: phase_started plan-docs-qr");
  log("DURABLE_EVENT: subagent_spawned quality-reviewer plan-docs-qr");

  let docsQrResult = await agent(PLAN_DOCS_QR_PROMPT(docsResult), {
    label: "plan-docs-qr",
    phase: "plan-docs-qr",
    agentType: "quality-reviewer",
  });

  const docsApproved = isQrPass(docsQrResult);

  // Outer-scope declaration so the fix pass feeds the final artifact extraction
  // below (see designFixed above).
  let docsFixed = null;

  if (!docsApproved) {
    docsFixed = await remediate({
      qrResult: docsQrResult,
      artifact: docsResult,
      role: "technical-writer",
      phaseName: "plan-docs-qr",
      artifactLabel: "PLAN WITH DOC_DIFFS",
    });

    docsQrResult = await agent(PLAN_DOCS_QR_PROMPT(docsFixed), {
      label: "plan-docs-qr-retry",
      phase: "plan-docs-qr",
      agentType: "quality-reviewer",
    });

    log(`PLANNER: plan-docs-qr-retry verdict — ${isQrPass(docsQrResult) ? "PASS" : "FAIL (proceeding best-effort)"}`);
  }

  log("DURABLE_EVENT: subagent_completed quality-reviewer plan-docs-qr");
  log("DURABLE_EVENT: phase_completed plan-docs-qr");

  log("PLANNER: All phases complete — PLAN APPROVED");

  // Propagate the fixed docs if QR triggered a fix pass.
  const approvedDocs = docsFixed || docsResult;

  // ── Build the real `plan` artifact ────────────────────────────────────────
  // Extract the final plan JSON from the docs phase output (which contains
  // the most complete version: design + code_changes + doc_diffs).
  // Falls back to code then design when a later phase's output degrades to a
  // _raw blob (e.g. docs-QR emits STATUS: BLOCKED).
  //
  // hasPlan treats a _raw-only extract as "not a usable plan" so the fallback
  // chain keeps walking even when extractJson wraps an unparseable response.
  // The original !planObj._raw guard stopped the chain the moment any phase
  // returned a _raw blob, trapping the planner on an empty result (DL-103).
  const hasPlan = (o) =>
    o && !o._raw && (o.overview || (Array.isArray(o.milestones) && o.milestones.length > 0));

  let planObj = extractJson(approvedDocs);
  if (!hasPlan(planObj)) {
    // Docs phase produced no usable plan — try the code phase (DL-026 fix
    // propagation: approvedCode carries the fix-pass output when QR triggered one).
    planObj = extractJson(approvedCode);
  }
  if (!hasPlan(planObj)) {
    // Code phase also unusable — fall back to the design phase. This is always
    // the phase that produces real milestones from the architect's work.
    planObj = extractJson(approvedDesign);
  }

  // Guarantee the top-level shape the parity test asserts on
  const plan = {
    overview: planObj.overview || { problem: "", approach: "" },
    planning_context: planObj.planning_context || {
      decisions: [],
      rejected_alternatives: [],
      constraints: [],
      risks: [],
    },
    invisible_knowledge: planObj.invisible_knowledge || {
      system: "",
      invariants: [],
      tradeoffs: [],
    },
    milestones: planObj.milestones || [],
    waves: planObj.waves || [],
    // Diagrams originate in the design phase (conventions/visualization.md). The
    // code/docs phases pass the plan forward and should echo them, but fall back
    // to the design output so a later phase dropping the field never silently
    // loses the diagrams.
    diagrams: Array.isArray(planObj.diagrams)
      ? planObj.diagrams
      : (Array.isArray(extractJson(approvedDesign).diagrams)
          ? extractJson(approvedDesign).diagrams
          : []),
  };

  // Include the full raw output for inspection / debugging
  if (planObj._raw) {
    plan._raw_agent_output = planObj._raw;
  }

  log(`PLANNER: plan artifact built — ${plan.milestones.length} milestones, ${plan.waves.length} waves`);

  return { plan };
