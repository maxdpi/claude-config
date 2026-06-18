/**
 * Codebase Analysis — Workflow-tool port (M-006, CI-M-006-001).
 *
 * Replaces the --step re-invocation loop with native sequential phases
 * + parallel() fan-out via the Workflow tool.
 *
 * Phases (unchanged domain logic from skills/scripts/skills/codebase_analysis/analyze.py):
 *   1. Scope      — define understanding goals
 *   2. Survey     — parallel Explore agents per focus area
 *   3. Deepen     — iterative direct exploration (up to 4 iterations)
 *   4. Synthesize — structured summary output
 *
 * CAVEAT (DL-008, DL-021): durable phase-boundary event emission for
 * codebase-analysis is EXPLICITLY DEFERRED — cross-session resumability
 * is not yet met. This port replaces the Python --step CLI but does not
 * yet emit events to events.jsonl at phase boundaries.
 *
 * Explore fan-out uses agentType:"scout" (read-only, no worktree isolation on any
 * path). No explorer.md agent is referenced (DL-023, DL-018).
 */

export const meta = {
  name: "codebase-analysis",
  description: "Understanding-focused codebase comprehension workflow",
  phases: ["scope", "survey", "deepen", "synthesize"],
  /**
   * Phase trust manifest (DL-014, DL-006).
   * Consumed by the hook-driven bridge (workflow_bridge.py) to populate manifest.json.
   * NOTE: the AUTHORITATIVE phase record is the hook bridge, not the DURABLE_EVENT
   * log() lines below. The log lines are human breadcrumbs only.
   *
   * All phases are read_only (exploration/analysis; no filesystem writes).
   */
  phaseTrust: {
    "scope":      "read_only",
    "survey":     "read_only",
    "deepen":     "read_only",
    "synthesize": "read_only",
  },
};

const MAX_DEEPEN_ITERATIONS = 4;

  // ── Phase 1: SCOPE ──────────────────────────────────────────────────────
  phase("Scope");

  const scopeResult = await agent(
    `CODEBASE ANALYSIS — Scope

PARSE user intent:
  - What codebase(s) are we analyzing?
  - What is the user trying to understand?
  - Are there specific areas of interest mentioned?

IDENTIFY focus areas:
  - Architecture/structure understanding
  - Specific component/feature deep-dive
  - Technology stack assessment
  - Integration patterns
  - Data flows

DEFINE goals (1-3 specific objectives):
  - 'Understand how [system X] processes [Y]'
  - 'Map dependencies between [A] and [B]'
  - 'Document data flow from [input] to [output]'

DO NOT seek user confirmation. Goals are internal guidance.

Output your analysis as structured JSON:
{
  "codebase": "<path or description>",
  "user_intent": "<what the user wants to understand>",
  "focus_areas": ["area1", "area2", ...],
  "goals": ["goal1", "goal2", "goal3"]
}`,
    {
      label: "scope",
      phase: "scope",
      schema: {
        type: "object",
        properties: {
          codebase:    { type: "string" },
          user_intent: { type: "string" },
          focus_areas: { type: "array", items: { type: "string" } },
          goals:       { type: "array", items: { type: "string" } },
        },
        required: ["focus_areas", "goals"],
      },
    },
  );

  // ── Phase 2: SURVEY ─────────────────────────────────────────────────────
  phase("Survey");

  // Derive focus areas from the structured scope result; fall through to defaults
  // when the agent returns an empty array (schema guarantees shape, not content).
  let focusAreas = scopeResult?.focus_areas ?? [];

  // Default to 3 parallel survey agents if scope didn't produce focus areas
  if (focusAreas.length === 0) {
    focusAreas = [
      "overall directory structure, entry points, and module organization",
      "core business logic, data models, and primary abstractions",
      "configuration, dependencies, integration points, and technology stack",
    ];
  }

  const surveyContext = `Scope analysis:\n${JSON.stringify(scopeResult, null, 2)}`;

  const surveyResults = await parallel(
    focusAreas.map((area) => () =>
      agent(
        `CODEBASE ANALYSIS — Survey Explorer

Focus area: ${area}

Context from scope phase:
${surveyContext}

You are exploring the codebase to understand this specific focus area.
Use Read, Glob, and Grep tools to survey the codebase.

Report your findings covering:
- STRUCTURE: How this area is organized
- PATTERNS: Coding and architectural patterns observed
- FLOWS: How data or requests move through this area
- DECISIONS: Key technology/design choices
- CONNECTIONS: How this area interfaces with others`,
        { label: `survey-${area.slice(0, 30)}`, phase: "survey", agentType: "scout" },
      )
    ),
  );

  const surveyFindings = surveyResults.join("\n\n---\n\n");

  // ── Phase 3: DEEPEN ──────────────────────────────────────────────────────
  phase("Deepen");

  let deepenFindings = "";
  let confidence = "exploring";
  let iteration = 0;

  while (confidence !== "certain" && iteration < MAX_DEEPEN_ITERATIONS) {
    iteration++;

    const deepenResult = await agent(
      `CODEBASE ANALYSIS — Deepen (Iteration ${iteration} of ${MAX_DEEPEN_ITERATIONS})

Survey findings so far:
${surveyFindings}

${deepenFindings ? `Prior deepen findings:\n${deepenFindings}\n` : ""}

DEEPEN understanding through direct exploration.

DO NOT dispatch sub-agents. Use Read, Glob, Grep tools directly in this step.

IDENTIFY areas needing deep understanding. Prioritize by:
  - COMPLEXITY: Non-obvious behavior, intricate logic
  - NOVELTY: Unfamiliar patterns, unique approaches
  - CENTRALITY: Core to user's goals

SELECT 1-3 targets for this iteration. Explore each:
  - Read key files directly
  - Trace execution paths
  - Understand data transformations
  - Map dependencies

ASSESS confidence — ground it in what you actually READ this iteration, not in a
general feeling of understanding. A claim you have not verified against a file
caps confidence at "medium". Only report "high"/"certain" for areas where you read
the relevant source directly. If your understanding still rests on unread code,
say "low"/"exploring" and keep iterating.
Set the confidence field to exactly one of: certain, high, medium, low, exploring`,
      {
        label: `deepen-${iteration}`,
        phase: "deepen",
        schema: {
          type: "object",
          properties: {
            confidence: {
              type: "string",
              enum: ["certain", "high", "medium", "low", "exploring"],
            },
            findings: { type: "string" },
          },
          required: ["confidence"],
        },
      },
    );

    // findings may be a string field or absent; fall back to the stringified object
    // so the accumulation stays human-readable in logs.
    const iterationFindings = deepenResult?.findings ?? JSON.stringify(deepenResult ?? {});
    deepenFindings += `\n\n## Iteration ${iteration}\n${iterationFindings}`;

    confidence = (deepenResult?.confidence ?? "medium").toLowerCase();

    log(`Deepen iteration ${iteration}: confidence=${confidence}`);

    if (confidence === "certain") {
      log("Confidence reached 'certain' — advancing to Synthesize");
      break;
    }
  }

  if (iteration >= MAX_DEEPEN_ITERATIONS && confidence !== "certain") {
    log(`Maximum deepen iterations reached (${MAX_DEEPEN_ITERATIONS}) — forcing Synthesize`);
  }

  // ── Phase 4: SYNTHESIZE ───────────────────────────────────────────────────
  phase("Synthesize");

  const synthesis = await agent(
    `CODEBASE ANALYSIS — Synthesize

Survey findings:
${surveyFindings}

Deep-dive findings:
${deepenFindings}

OUTPUT structured summary:

# Codebase Understanding Summary

## Structure
[Directory organization, module boundaries, component relationships]

## Patterns
[Architectural patterns, design patterns, code organization]

## Flows
[Request flows, data flows, integration patterns]

## Decisions
[Technology choices, framework selections, architectural decisions]

## Context
[Purpose, constraints, trade-offs, evolution]

Ensure:
  - Summary addresses user's original intent
  - All sections present with concrete findings
  - Framing is understanding-focused (not auditing)
  - Facts and observations (not judgments)`,
    { label: "synthesize", phase: "synthesize" },
  );

  return { synthesis };
