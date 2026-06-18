/**
 * Incoherence Detector — Workflow-tool port (M-006, CI-M-006-011).
 *
 * Replaces the 21-step --step-number re-invocation with native sequential phases
 * + parallel() fan-out for broad-sweep and deep-dive waves.
 *
 * Phases (unchanged domain logic from skills/scripts/skills/incoherence/incoherence.py):
 *
 *   DETECTION PHASE:
 *     1. survey           — gather codebase overview
 *     2. dimension_select — choose dimensions from catalog (A-M)
 *     3. broad_sweep      — parallel explorer fan-out per dimension
 *     4. synthesize_candidates — score + rank candidate incoherences
 *     5. deep_dive        — parallel verification agents per candidate
 *     6. verdict_analysis — tally, deduplicate, group related issues
 *
 *   RESOLUTION PHASE:
 *     7. resolution       — interactive AskUserQuestion loop
 *
 *   APPLICATION PHASE:
 *     8. application      — parallel apply agents per resolved file
 *     9. report           — present final summary
 *
 * permissionMode:plan + maxTurns on agents/explorer.md (DL-023).
 * Write-phase application workers use isolation:worktree in their agent opts.
 */

export const meta = {
  name: "incoherence",
  description: "Multi-phase incoherence detection and resolution workflow",
  phases: [
    "survey",
    "dimension_select",
    "broad_sweep",
    "synthesize_candidates",
    "deep_dive",
    "verdict_analysis",
    "resolution",
    "application",
    "report",
  ],
  /**
   * Phase trust manifest (DL-014, DL-006).
   * Consumed by the hook-driven bridge (workflow_bridge.py) to populate manifest.json.
   * NOTE: the AUTHORITATIVE phase record is the hook bridge, not the DURABLE_EVENT
   * log() lines. The log lines are human breadcrumbs only.
   *
   * Detection phases are read_only. Resolution is write (user decides).
   * Application is execute (writes files). Report is read_only.
   */
  phaseTrust: {
    "survey":                "read_only",
    "dimension_select":      "read_only",
    "broad_sweep":           "read_only",
    "synthesize_candidates": "read_only",
    "deep_dive":             "read_only",
    "verdict_analysis":      "read_only",
    "resolution":            "write",
    "application":           "execute",
    "report":                "read_only",
  },
};

const DIMENSION_CATALOG = `
ABSTRACT DIMENSION CATALOG
==========================

CATEGORY A: SPECIFICATION VS BEHAVIOR
  README/docs claim X, but code does Y

CATEGORY B: INTERFACE CONTRACT INTEGRITY
  Type definitions vs actual runtime values

CATEGORY C: CROSS-REFERENCE CONSISTENCY
  Same concept described differently in different docs

CATEGORY D: TEMPORAL CONSISTENCY (Staleness)
  Outdated comments referencing removed code

CATEGORY E: ERROR HANDLING CONSISTENCY
  Documented error codes vs actual error responses

CATEGORY F: CONFIGURATION & ENVIRONMENT
  Documented env vars vs actual env var usage

CATEGORY G: AMBIGUITY & UNDERSPECIFICATION
  Vague statements that could be interpreted multiple ways

CATEGORY H: POLICY & CONVENTION COMPLIANCE
  Architectural decisions violated by implementation

CATEGORY I: COMPLETENESS & DOCUMENTATION GAPS
  Public API endpoints with no documentation

CATEGORY J: COMPOSITIONAL CONSISTENCY
  Claims individually valid but jointly impossible

CATEGORY K: IMPLICIT CONTRACT INTEGRITY
  Names/identifiers promise behavior the code doesn't deliver

CATEGORY L: DANGLING SPECIFICATION REFERENCES
  Entity A references entity B, but B is never defined anywhere

CATEGORY M: INCOMPLETE SPECIFICATION DEFINITIONS
  Entity is defined but missing components required for implementation

SELECTION RULES:
- Select ALL categories relevant to info sources
- Typical selection is 5-8 dimensions
- G, H, I, K are especially relevant for LLM-assisted coding
- J requires cross-referencing multiple claims (more expensive)
- L, M are critical for design-phase docs and specs-to-be-implemented
`;

  // ── Phase 1: Survey ───────────────────────────────────────────────────────
  phase("survey");

  const surveyResult = await agent(
    `INCOHERENCE — Codebase Survey

Gather MINIMAL context (README first 50 lines, CLAUDE.md, dir listing).
Do NOT read detailed docs, source code, configs, or tests.

Identify:
  - Codebase type and primary language
  - Doc locations
  - Info source types present (README, API docs, comments, types, configs,
    schemas, ADRs, style guides, tests)

Output a brief survey summary.`,
    { label: "survey", phase: "survey" },
  );

  // ── Phase 2: Dimension Selection ──────────────────────────────────────────
  phase("dimension_select");

  const dimensionResult = await agent(
    `INCOHERENCE — Dimension Selection

Survey results:
${surveyResult}

${DIMENSION_CATALOG}

Select dimensions from catalog (A-M) based on the survey's info sources.
Do NOT read files. Do NOT create domain-specific dimensions.

Output JSON:
{
  "dimensions": [
    {"letter": "A", "name": "Specification vs Behavior", "rationale": "README + code present"}
  ]
}`,
    { label: "dimension-select", phase: "dimension_select" },
  );

  let dimensions = [];
  try {
    const parsed = JSON.parse(dimensionResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    dimensions = parsed.dimensions ?? [];
  } catch (error) {
    log(`Dimension parse failed (${error.message}); using defaults`);
    dimensions = [
      { letter: "A", name: "Specification vs Behavior" },
      { letter: "C", name: "Cross-Reference Consistency" },
      { letter: "I", name: "Documentation Gaps" },
    ];
  }

  log(`Selected ${dimensions.length} dimensions: ${dimensions.map((d) => d.letter).join(", ")}`);

  // ── Phase 3: Broad Sweep (parallel per dimension) ────────────────────────
  phase("broad_sweep");

  const broadSweepResults = await parallel(
    dimensions.map((dim) => () =>
      agent(
        `INCOHERENCE — Broad Sweep

DIMENSION: ${dim.letter} - ${dim.name}
${dim.rationale ? `Rationale: ${dim.rationale}` : ""}

Survey context:
${surveyResult}

Cast WIDE NET. Prioritize recall over precision.

SEARCH: docs/, README, src/, configs, schemas, types, tests.

FOR L/M DIMENSIONS: Build entity registry first:
  - DEFINED: tables, endpoints, types (entity_name, file:line, components)
  - REFERENCED: FKs, type usages, API calls (entity_name, file:line)
  - Cross-ref: referenced-not-defined=L, defined-but-incomplete=M

PER FINDING: Location A, Location B, conflict, confidence (low OK).
Bias: Report more. Track searched locations.

Output:
DIMENSION ${dim.letter} | TOTAL: N | AREAS SEARCHED: [list]
FINDING 1: A=[file:line] B=[file:line] Conflict=[desc] Confidence=[h/m/l]
...`,
        {
          label: `broad-sweep-${dim.letter}`,
          phase: "broad_sweep",
          agentType: "scout",
          model: "haiku",
        },
      )
    ),
  );

  const broadSweepFindings = dimensions
    .map((dim, i) => `## Dimension ${dim.letter}: ${dim.name}\n${broadSweepResults[i]}`)
    .join("\n\n");

  // ── Phase 4: Synthesize Candidates ───────────────────────────────────────
  phase("synthesize_candidates");

  const candidatesResult = await agent(
    `INCOHERENCE — Synthesize Candidates

Broad sweep findings:
${broadSweepFindings}

For each finding:
1. Score (0-10): Impact + Confidence + Specificity + Fixability
2. Assign candidate ID: C1, C2, ...
3. Output: candidate ID, location, summary, score, dimension

Pass ALL candidates (no limits). Deduplication after deep-dive verification.

Output JSON:
{
  "candidates": [
    {
      "id": "C1",
      "dimension": "A",
      "location_a": "file:line",
      "location_b": "file:line",
      "summary": "Description of potential incoherence",
      "score": 7
    }
  ]
}`,
    { label: "synthesize-candidates", phase: "synthesize_candidates" },
  );

  let candidates = [];
  try {
    const parsed = JSON.parse(candidatesResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    candidates = parsed.candidates ?? [];
  } catch (error) {
    log(`Candidate parsing failed (${error.message})`);
  }

  log(`${candidates.length} candidates for deep-dive verification`);

  // ── Phase 5: Deep Dive (parallel per candidate) ──────────────────────────
  phase("deep_dive");

  const deepDiveResults = await parallel(
    candidates.map((cand) => () =>
      agent(
        `INCOHERENCE — Deep-Dive Verification

CANDIDATE: ${cand.id} at ${cand.location_a} vs ${cand.location_b}
DIMENSION: ${cand.dimension}
Claimed: ${cand.summary}

1. Read both sources with 100+ lines context, extract exact quotes
2. Analyze by dimension type:
   - A,B,C,E,F,J,K (contradiction): genuinely conflicting? -> TRUE_INCOHERENCE
   - G (ambiguity): two readers interpret differently? -> SIGNIFICANT_AMBIGUITY
   - H (policy): orphaned ref -> DOC_GAP, active violation -> TRUE_INCOHERENCE
   - I (completeness): missing needed info? -> DOCUMENTATION_GAP
   - L,M (omission): undefined/incomplete entity? -> SPECIFICATION_GAP
3. Verdict: TRUE_INCOHERENCE | SIGNIFICANT_AMBIGUITY | DOCUMENTATION_GAP |
   SPECIFICATION_GAP | FALSE_POSITIVE

Output:
CANDIDATE: ${cand.id} | VERDICT: {verdict} | SEVERITY: {c/h/m/l}
SOURCE A: {file}:{line} "{quote}" Claims: {claim}
SOURCE B: {file}:{line} "{quote}" Claims: {claim}
ANALYSIS: {why conflict} | RECOMMENDATION: {fix}`,
        {
          label: `deep-dive-${cand.id}`,
          phase: "deep_dive",
          agentType: "scout",
          model: "sonnet",
        },
      )
    ),
  );

  const deepDiveFindings = candidates
    .map((c, i) => `## Candidate ${c.id}\n${deepDiveResults[i]}`)
    .join("\n\n");

  // ── Phase 6: Verdict Analysis ─────────────────────────────────────────────
  phase("verdict_analysis");

  const verdictsResult = await agent(
    `INCOHERENCE — Verdict Analysis

Deep-dive findings:
${deepDiveFindings}

1. Tally by verdict type and severity
2. Quality check: each non-FALSE_POSITIVE has exact quotes
3. Deduplicate: merge identical source pairs, keep richer analysis
4. Group related issues:
   - SHARED ROOT CAUSE: same file, same outdated doc, same config
   - SHARED THEME: same dimension, same concept, same fix type
   Output: G1, G2... with member issues, relationship, unified resolution

Output JSON:
{
  "verdicts": [
    {
      "id": "C1",
      "verdict": "TRUE_INCOHERENCE",
      "severity": "high",
      "source_a": {"file": "...", "line": 42, "quote": "..."},
      "source_b": {"file": "...", "line": 88, "quote": "..."},
      "analysis": "...",
      "recommendation": "..."
    }
  ],
  "groups": [
    {"id": "G1", "members": ["C1", "C2"], "root_cause": "...", "unified_resolution": "..."}
  ]
}`,
    { label: "verdict-analysis", phase: "verdict_analysis" },
  );

  let verdicts = [];
  let groups = [];
  try {
    const parsed = JSON.parse(verdictsResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    verdicts = parsed.verdicts ?? [];
    groups = parsed.groups ?? [];
  } catch (error) {
    log(`Verdict parsing failed (${error.message})`);
  }

  const confirmedVerdicts = verdicts.filter((v) => v.verdict !== "FALSE_POSITIVE");
  log(
    `Verdicts: ${confirmedVerdicts.length} confirmed (${verdicts.length - confirmedVerdicts.length} false positives)`,
  );

  if (confirmedVerdicts.length === 0) {
    log("No confirmed incoherences. Presenting report.");
    return {
      verdicts: [],
      resolution: "No incoherences found",
      report: "No incoherences detected in the codebase.",
    };
  }

  // ── Phase 7: Interactive Resolution ──────────────────────────────────────
  phase("resolution");

  // Prepare resolution batches (max 4 per batch, group-aware)
  const resolutionResult = await agent(
    `INCOHERENCE — Interactive Resolution

Confirmed incoherences:
${JSON.stringify({ verdicts: confirmedVerdicts, groups }, null, 2)}

Prepare resolution batches (max 4 per batch):
1. Group-based: issues sharing G1/G2/... together
2. File-based: ungrouped issues affecting same file
3. Singletons: remaining unrelated issues

For each batch, use AskUserQuestion to get user decisions.

Group batch (2+ members): Ask for group decision first
  Options: unified_suggestion | 'Resolve individually' | 'Skip all'

Non-group or individual: Ask per-issue questions
  Options: suggestion_1 | suggestion_2 | 'Skip'

Collect all responses. Output:
{
  "resolutions": [
    {"issue_id": "C1", "action": "Update README to match implementation", "skip": false}
  ]
}`,
    { label: "resolution", phase: "resolution" },
  );

  let resolutions = [];
  try {
    const parsed = JSON.parse(resolutionResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    resolutions = parsed.resolutions ?? [];
  } catch (error) {
    log(`Resolution parsing failed (${error.message})`);
  }

  const activeResolutions = resolutions.filter((r) => !r.skip);
  log(`${activeResolutions.length} issues to apply`);

  // ── Phase 8: Application ──────────────────────────────────────────────────
  phase("application");

  // Group by file for parallel application
  const byFile = {};
  for (const res of activeResolutions) {
    const verdict = confirmedVerdicts.find((v) => v.id === res.issue_id);
    const file = verdict?.source_a?.file ?? "unknown";
    if (!byFile[file]) byFile[file] = [];
    byFile[file].push({ ...res, verdict });
  }

  const fileGroups = Object.entries(byFile);
  let applicationResults = [];

  if (fileGroups.length > 0) {
    applicationResults = await parallel(
      fileGroups.map(([file, issues]) => () =>
        agent(
          `INCOHERENCE — Apply Resolutions

TARGET FILE: ${file}
ISSUES: ${issues.map((i) => i.issue_id).join(", ")}

${issues
  .map(
    (i) =>
      `Issue ${i.issue_id}:
  Type: ${i.verdict?.verdict}
  Severity: ${i.verdict?.severity}
  Source A: ${i.verdict?.source_a?.file}:${i.verdict?.source_a?.line}
  Source B: ${i.verdict?.source_b?.file}:${i.verdict?.source_b?.line}
  Analysis: ${i.verdict?.analysis}
  Resolution: ${i.action}`,
  )
  .join("\n\n")}

Apply each resolution:
1. Locate the target file
2. Apply the change that resolves the incoherence
3. Verify the change addresses the issue
4. Report: ISSUE: {id} | STATUS: RESOLVED|SKIPPED | FILE: {path}`,
          {
            label: `apply-${file.replace(/[^a-zA-Z0-9]/g, "-")}`,
            phase: "application",
            isolation: "worktree",
          },
        )
      ),
    );
  }

  // ── Phase 9: Report ───────────────────────────────────────────────────────
  phase("report");

  await agent(
    `INCOHERENCE — Present Final Report

Detected: ${verdicts.length} candidates
Confirmed: ${confirmedVerdicts.length} incoherences
Resolved: ${activeResolutions.length} issues
Application results:
${applicationResults.join("\n\n")}

Output inline report (no file):
  Summary: detected N, confirmed M, resolved K, skipped J

  | ID | Severity | Verdict | Summary (~40 chars) | Status |
  |----|----------|---------|---------------------|--------|

  List ALL confirmed issues with their final status.`,
    { label: "report", phase: "report" },
  );

  return { verdicts: confirmedVerdicts };
