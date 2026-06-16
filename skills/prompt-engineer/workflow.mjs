/**
 * Prompt Engineer — Workflow-tool port (M-006, CI-M-006-013).
 *
 * Replaces scope-adaptive --step re-invocation with native control flow
 * branching on triaged scope. Linear/convergent — Workflow-tool port.
 *
 * Domain logic from skills/scripts/skills/prompt_engineer/optimize.py:
 *
 * Scopes (four-way branch after triage):
 *   - single-prompt: One file + 'improve/optimize' request → 7-step workflow
 *   - ecosystem:     Multiple related prompts interacting  → 8-step workflow
 *   - greenfield:    No existing prompt, designing from requirements → 7-step
 *   - problem:       Existing prompt with specific failure → 7-step workflow
 *
 * Research grounding (preserved from Python source):
 *   - Self-Refine (Madaan 2023): Separate feedback from refinement
 *   - CoVe (Dhuliawala 2023): Factored verification with OPEN questions
 *
 * No separate subagent .md needed — this is a single-agent linear workflow.
 * The optimization workers run inline (no agentType dispatch needed).
 */

export const meta = {
  name: "prompt-engineer",
  description: "Scope-adaptive prompt optimization workflow",
  phases: ["triage", "assess", "plan", "draft", "refine", "approve", "execute"],
  /**
   * Phase trust manifest (DL-014, DL-006).
   * Consumed by the hook-driven bridge (workflow_bridge.py) to populate manifest.json.
   * NOTE: the AUTHORITATIVE phase record is the hook bridge, not the DURABLE_EVENT
   * log() lines. The log lines are human breadcrumbs only.
   *
   * Analysis/planning phases are read_only. Draft/refine/approve are write (produce
   * artifacts). Execute writes to target files.
   */
  phaseTrust: {
    "triage":  "read_only",
    "assess":  "read_only",
    "plan":    "read_only",
    "draft":   "write",
    "refine":  "write",
    "approve": "write",
    "execute": "execute",
  },
};

const REFINE_INSTRUCTIONS = `VERIFY each proposed technique (factored verification):

  For each technique you claimed APPLICABLE:
  1. Close your proposal. Answer from reference ONLY:
     Q: 'What is the EXACT trigger condition for [technique]?'
  2. Close the reference. Answer from target prompt ONLY:
     Q: 'What text appears at line [N]?'
  3. Compare: Does quoted text match quoted trigger?

  Cross-check: CLAIMED vs VERIFIED
    CONSISTENT -> keep
    INCONSISTENT -> revise or remove

META-CONSTRAINT VERIFICATION:
  For EACH proposed change:
  Q: Does this change modify PROMPT TEXT STRUCTURE or add OUTPUT INSTRUCTIONS?

  PROMPT TEXT STRUCTURE changes include:
    - Shortening/compressing existing prompt text
    - Removing sections or examples from prompt
    - Refactoring code structure

  If ANY changes modify prompt text structure:
    -> VIOLATION of meta-constraint
    -> REMOVE these changes
    -> REVISE to add output instructions instead`;

const APPROVE_FORMAT = `Present using this format:

PROPOSED CHANGES
================

| # | Location | Opportunity | Technique | Risk |
|---|----------|-------------|-----------|------|

Then each change in detail.

VERIFICATION SUMMARY:
  - Changes verified: N
  - Changes revised: M
  - Changes removed: K

CRITICAL: STOP. Do NOT proceed to Execute step.
Wait for explicit user approval before continuing.`;

  // ── Phase 1: Triage ───────────────────────────────────────────────────────
  phase("triage");

  const triageResult = await agent(
    `PROMPT ENGINEER — Triage

EXAMINE the input, request, AND any relevant prior conversation:
  - Problem descriptions stated earlier
  - Analysis or diagnosis already performed
  - User preferences or constraints mentioned

  FILES PROVIDED:
    - None: likely GREENFIELD
    - Single file with prompt: likely SINGLE-PROMPT
    - Multiple related files: likely ECOSYSTEM

  REQUEST TYPE:
    - General optimization ('improve this'): SINGLE-PROMPT or ECOSYSTEM
    - Specific problem ('fix X', 'it does Y wrong'): PROBLEM
    - Design request ('I want X to do Y'): GREENFIELD

DETERMINE SCOPE:
  SINGLE-PROMPT: One file + 'improve/optimize' request
    Boundary: If 2+ files interact -> ECOSYSTEM
  ECOSYSTEM: Multiple files with shared terminology or data flow
    Boundary: If no interaction between files -> multiple SINGLE-PROMPT
  GREENFIELD: No existing prompt + 'create/design/build' request
    Boundary: If modifying existing -> SINGLE-PROMPT or PROBLEM
  PROBLEM: Existing prompt + specific failure described
    Boundary: If no specific failure -> SINGLE-PROMPT or ECOSYSTEM

OUTPUT:
  SCOPE: [single-prompt | ecosystem | greenfield | problem]
  RATIONALE: [why this scope fits]`,
    { label: "triage", phase: "triage" },
  );

  const scopeMatch = triageResult.match(/SCOPE:\s*(single-prompt|ecosystem|greenfield|problem)/i);
  const scope = scopeMatch ? scopeMatch[1].toLowerCase() : "single-prompt";
  log(`Triaged scope: ${scope}`);

  // ── Phase 2: Assess / Understand ─────────────────────────────────────────
  phase("assess");

  let assessPrompt;
  if (scope === "single-prompt") {
    assessPrompt = `PROMPT ENGINEER (single-prompt) — Assess

PRIOR CONTEXT: Incorporate any relevant analysis already in this conversation.

READ the target prompt file.

ARTICULATE what this prompt accomplishes:
  - High-level goal
  - Inputs it expects
  - Outputs it should produce
  - What SUCCESS looks like

DIAGNOSE issues:
  Map current/anticipated issues to categories:
  - Reasoning: [skips steps, wrong decomposition, no visible trace]
  - Consistency: [different outputs each run]
  - Accuracy: [wrong facts, hallucinations]
  - Context: [ignores input, distracted by noise]
  - Format: [wrong structure, unparseable]

Output a diagnosis summary.`;
  } else if (scope === "ecosystem") {
    assessPrompt = `PROMPT ENGINEER (ecosystem) — Assess

READ all prompt-containing files in scope.

MAP the ecosystem:
  - What is the HIGH-LEVEL goal of this prompt system?
  - What end-to-end workflow do these prompts enable?

For EACH prompt, derive:
  - Its role in the ecosystem
  - Inputs/outputs
  - Data flow to/from other prompts
  - Current issues

CROSS-PROMPT ISSUES:
  - Inconsistent terminology?
  - Information leakage (passing too much/too little context)?
  - Coupling that should be decoupled?

Note which techniques apply to multiple prompts.`;
  } else if (scope === "greenfield") {
    assessPrompt = `PROMPT ENGINEER (greenfield) — Assess

UNDERSTAND the requirements:
  - What should the new prompt accomplish?
  - What inputs will it receive?
  - What outputs should it produce?
  - What failure modes must be prevented?

DETERMINE EXECUTION CONTEXT:
  STANDALONE: Top-level Claude invocation with system prompt
  SKILL: Injected into an existing Claude Code skill workflow
  SUB-AGENT: Spawned by a parent agent, receives structured input
  COMPONENT: Part of a multi-agent system

STRUCTURE DECISION:
  SINGLE-TURN when: discrete task, one input -> one output
  MULTI-TURN when: iterative refinement, clarification needed
  MULTI-STEP when: complex decomposition, phase-dependent outputs

Output design requirements summary.`;
  } else {
    // problem
    assertPrompt = `PROMPT ENGINEER (problem) — Diagnose

UNDERSTAND the problem:
  - What specific behavior is failing?
  - When does it fail? (always / certain inputs / certain conditions)
  - What is the expected vs actual output?

CLASSIFY the problem:
  - Reasoning failure: model skips steps, wrong decomposition, no trace
  - Consistency failure: different outputs for same input
  - Accuracy failure: wrong facts, hallucinations
  - Context failure: ignores key input, distracted by irrelevant context
  - Format failure: wrong structure, unparseable output
  (problem may span multiple categories)

Output problem diagnosis.`;
    assessPrompt = assertPrompt;
  }

  const assessResult = await agent(assessPrompt, { label: "assess", phase: "assess" });

  // ── Phase 3: Plan ──────────────────────────────────────────────────────────
  phase("plan");

  const planResult = await agent(
    `PROMPT ENGINEER (${scope}) — Plan Optimizations

Scope: ${scope}
Assessment/diagnosis:
${assessResult}

READ relevant technique references from the optimization library:
  - references/reasoning/ for reasoning improvements
  - references/consistency/ for consistency improvements
  - references/accuracy/ for accuracy improvements
  - references/context/ for context/grounding improvements
  - references/efficiency/ for output compression

CONTEXT GATHERING:
  For MULTIPLE RELATED PROMPTS:
    What is the HIGH-LEVEL goal of this prompt system?
    Then for EACH prompt, derive its purpose FROM the system goal.

  For A SINGLE PROMPT:
    What problem does this prompt solve?
    What inputs/outputs define its contract?

PROPOSE techniques:
  For each issue identified in the assessment:
  - Map to applicable technique(s)
  - State the trigger condition for each technique
  - Propose specific addition to the prompt

Output proposed changes with technique citations.`,
    { label: "plan", phase: "plan" },
  );

  // ── Phase 4: Draft ────────────────────────────────────────────────────────
  phase("draft");

  const draftResult = await agent(
    `PROMPT ENGINEER (${scope}) — Draft

Plan:
${planResult}

Apply the planned techniques to produce the optimized prompt(s).

META-CONSTRAINT: Add output instructions only.
  DO NOT compress or remove existing prompt text.
  DO NOT restructure code.
  DO add: chain-of-thought triggers, output format specs, verification steps.

For each change, annotate:
  [TECHNIQUE: name] at the location of application

For GREENFIELD: Write the complete new prompt from scratch.
For PROBLEM: Produce a diff showing the targeted fix.
For SINGLE-PROMPT/ECOSYSTEM: Show the full optimized version.`,
    { label: "draft", phase: "draft" },
  );

  // ── Phase 5: Refine (verification) ────────────────────────────────────────
  phase("refine");

  const refineResult = await agent(
    `PROMPT ENGINEER (${scope}) — Refine

Draft:
${draftResult}

${REFINE_INSTRUCTIONS}

${
  scope === "greenfield" || scope === "problem"
    ? `CONTEXT-CORRECTNESS VERIFICATION:
  Q: What is the execution context for this prompt?
  Q: Does the draft contain <system> wrapper or identity setup?
  Q: Should this execution context have <system>/identity?
  STANDALONE -> yes. SKILL/SUB-AGENT/COMPONENT -> no.
  If INCONSISTENT: flag for revision before Approve step.`
    : ""
}

Output the refined proposal.`,
    { label: "refine", phase: "refine" },
  );

  // ── Phase 6: Approve ──────────────────────────────────────────────────────
  phase("approve");

  const approveResult = await agent(
    `PROMPT ENGINEER (${scope}) — Approve

Refined proposal:
${refineResult}

${APPROVE_FORMAT}

Present to user and WAIT for explicit approval.`,
    { label: "approve", phase: "approve" },
  );

  // ── Phase 7: Execute ──────────────────────────────────────────────────────
  phase("execute");

  const optimized_prompt = await agent(
    `PROMPT ENGINEER (${scope}) — Execute

Approved changes:
${approveResult}

Apply ALL approved changes to the target file(s).
  - Make ONLY the approved changes
  - Preserve all non-changed content exactly
  - Verify by reading the updated file

Output the final optimized prompt text and a summary of changes applied.`,
    { label: "execute", phase: "execute" },
  );

  return { optimized_prompt };
