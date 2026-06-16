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
 * permissionMode / maxTurns / skills live on agents/explorer.md (DL-023).
 */

export const meta = {
  name: "codebase-analysis",
  description: "Understanding-focused codebase comprehension workflow",
  phases: ["scope", "survey", "deepen", "synthesize"],
};

const MAX_DEEPEN_ITERATIONS = 4;

export async function run() {
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
    { label: "scope", phase: "scope" },
  );

  // ── Phase 2: SURVEY ─────────────────────────────────────────────────────
  phase("Survey");

  // Determine focus areas from scope (parse JSON or use defaults)
  let focusAreas;
  try {
    const parsed = JSON.parse(scopeResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    focusAreas = parsed.focus_areas ?? [];
  } catch {
    focusAreas = [];
  }

  // Default to 3 parallel survey agents if scope didn't produce focus areas
  if (focusAreas.length === 0) {
    focusAreas = [
      "overall directory structure, entry points, and module organization",
      "core business logic, data models, and primary abstractions",
      "configuration, dependencies, integration points, and technology stack",
    ];
  }

  const surveyContext = `Scope analysis:\n${scopeResult}`;

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
        { label: `survey-${area.slice(0, 30)}`, phase: "survey", agentType: "explorer" },
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

ASSESS confidence (output exactly one of these on the last line):
  CONFIDENCE: certain
  CONFIDENCE: high
  CONFIDENCE: medium
  CONFIDENCE: low
  CONFIDENCE: exploring`,
      { label: `deepen-${iteration}`, phase: "deepen" },
    );

    deepenFindings += `\n\n## Iteration ${iteration}\n${deepenResult}`;

    // Parse confidence from the result
    const confidenceMatch = deepenResult.match(/CONFIDENCE:\s*(certain|high|medium|low|exploring)/i);
    confidence = confidenceMatch ? confidenceMatch[1].toLowerCase() : "medium";

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
}
