/**
 * Refactor — Workflow-tool port with durable phase-boundary events (M-006, CI-M-006-002).
 *
 * Replaces the 8-step --step re-invocation loop with native sequential phases
 * + parallel() fan-out. Cross-session resume is supported via the journal bridge.
 *
 * Phases (unchanged domain logic from skills/scripts/skills/refactor/refactor.py):
 *   1. mode_selection   — detect design/code/both mode from user request
 *   2. dispatch         — select N code smell categories + parallel Explore fan-out
 *   3. triage           — review findings, structure as smells with IDs
 *   4. cluster          — group smells by shared root cause
 *   5. contextualize    — extract user intent, prioritize issues
 *   6. synthesize       — generate actionable work items
 *
 * Durable events: emitted at each phase boundary so cross-session resume
 * can replay from the last completed phase (refactor MUST be resumable, DL-008).
 *
 * permissionMode:plan and maxTurns live on agents/explorer.md (DL-023).
 * isolation:worktree lives on the synthesize worker path only (DL-018).
 */

export const meta = {
  name: "refactor",
  description: "Category-based code smell detection and synthesis workflow",
  phases: [
    "mode_selection",
    "dispatch",
    "triage",
    "cluster",
    "contextualize",
    "synthesize",
  ],
  /**
   * Phase trust manifest (DL-014, DL-006).
   * Consumed by the hook-driven bridge (workflow_bridge.py) to populate manifest.json.
   * NOTE: the AUTHORITATIVE phase record is the hook bridge, not the DURABLE_EVENT
   * log() lines. The log lines are human breadcrumbs only.
   *
   * All phases are read_only (analysis/exploration; no filesystem writes).
   */
  phaseTrust: {
    "mode_selection":  "read_only",
    "dispatch":        "read_only",
    "triage":          "read_only",
    "cluster":         "read_only",
    "contextualize":   "read_only",
    "synthesize":      "read_only",
  },
};

const DEFAULT_CATEGORY_COUNT = 10;

  const n = args?.n ?? DEFAULT_CATEGORY_COUNT;

  // ── Phase 1: Mode Selection ───────────────────────────────────────────────
  phase("mode_selection");

  const modeResult = await agent(
    `REFACTOR — Mode Selection

Analyze the user's request to determine the refactor mode:

STEP A — MODE DETECTION:
  Determine which mode fits the request:
  - design: User wants to review architecture, patterns, design decisions
  - code: User wants to review code quality, implementation issues (DEFAULT)
  - both: User wants both design and code review
  - custom: User described a specific problem or has custom requirements

STEP B — SCOPE EXTRACTION:
  Identify what to analyze:
  - Specific file(s) or directory mentioned?
  - Entire codebase?
  - Specific concern or component?

STEP C — PROBLEM STATEMENT (custom mode only):
  If mode=custom, extract the specific problem being described.

Output as JSON:
{
  "mode": "design|code|both|custom",
  "scope": "<path or null for codebase-wide>",
  "problem_statement": "<only for custom mode, else null>"
}`,
    { label: "mode-selection", phase: "mode_selection" },
  );

  let mode = "code";
  let scope = null;
  try {
    const parsed = JSON.parse(modeResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    mode = parsed.mode ?? "code";
    scope = parsed.scope ?? null;
  } catch (error) {
    log(`Mode selection parse failed (${error.message}); defaulting to code mode`);
  }

  log(`Mode: ${mode}, Scope: ${scope ?? "codebase-wide"}, N: ${n}`);

  // ── Phase 2: Dispatch — Category Selection + Parallel Explore ────────────
  phase("dispatch");

  const dispatchResult = await agent(
    `REFACTOR — Category Selection

Select ${n} code smell categories to investigate.

Mode: ${mode}
Scope: ${scope ?? "entire codebase"}

Available categories come from conventions/code-quality/ — these cover:
- Naming conventions, function complexity, duplication
- Error handling patterns, testing gaps, type safety
- Architecture violations, coupling, cohesion
- Performance anti-patterns, security concerns
- Documentation gaps, dead code

Select ${n} categories most relevant to the mode and scope.
Output as JSON:
{
  "categories": [
    {"id": "cat-1", "name": "Category Name", "description": "What to look for"},
    ...
  ]
}`,
    { label: "category-selection", phase: "dispatch" },
  );

  let categories = [];
  try {
    const parsed = JSON.parse(dispatchResult.match(/\{[\s\S]*\}/)?.[0] ?? "{}");
    categories = parsed.categories ?? [];
  } catch (error) {
    log(`Category parsing failed (${error.message}); using placeholder categories`);
    categories = Array.from({ length: Math.min(n, 5) }, (_, i) => ({
      id: `cat-${i + 1}`,
      name: `Category ${i + 1}`,
      description: "Code quality category",
    }));
  }

  // Parallel Explore agents — one per category (read-only, no worktree isolation)
  const exploreResults = await parallel(
    categories.map((cat) => () =>
      agent(
        `REFACTOR — Explore: ${cat.name}

Explore the codebase for this code smell category.

CATEGORY: ${cat.name}
DESCRIPTION: ${cat.description}
MODE: ${mode}
SCOPE: ${scope ?? "entire codebase"}

Cast a wide net. Search for instances of this code smell:
1. Use Glob to find relevant files
2. Use Grep to find pattern instances
3. Read key files for context
4. Record each instance: file:line, description, severity (critical/high/medium/low)

Output structured findings:
{
  "category": "${cat.name}",
  "smells": [
    {
      "smell_id": "smell-${cat.id}-1",
      "file": "<path>",
      "line": <number>,
      "description": "<what the smell is>",
      "severity": "critical|high|medium|low",
      "occurrence_count": <number>
    }
  ]
}`,
        {
          label: `explore-${cat.id}`,
          phase: "dispatch",
          agentType: "Explore",
          model: "haiku",
        },
      )
    ),
  );

  const allFindings = exploreResults.join("\n\n---\n\n");

  // ── Phase 3: Triage ───────────────────────────────────────────────────────
  phase("triage");

  const triageResult = await agent(
    `REFACTOR — Triage

Review all explore findings and structure them as validated smells.

Findings from explore phase:
${allFindings}

For each finding:
1. Validate it is a genuine code smell (not a false positive)
2. Assign a stable smell_id if missing
3. Rate impact: does it affect correctness, maintainability, performance, or readability?
4. Identify the SPECIFIC code construct that is problematic

Output JSON array of validated smells:
{
  "smells": [
    {
      "smell_id": "smell-X",
      "category": "Category Name",
      "file": "path/to/file.py",
      "line": 42,
      "description": "Description of the smell",
      "severity": "critical|high|medium|low",
      "impact": "What goes wrong because of this smell",
      "occurrence_count": 1
    }
  ],
  "rejected_smells": [
    {"smell_id": "smell-Y", "reason": "false positive — ..."}
  ]
}`,
    { label: "triage", phase: "triage" },
  );

  // ── Phase 4: Cluster ──────────────────────────────────────────────────────
  phase("cluster");

  const clusterResult = await agent(
    `REFACTOR — Cluster

Group the validated smells by shared root cause.

Triage results:
${triageResult}

Clustering rules:
1. SHARED ROOT CAUSE: smells that stem from the same underlying problem
   (e.g., all caused by missing abstraction, or all from same outdated pattern)
2. SHARED THEME: smells of the same type across multiple locations
3. STANDALONE: smells that don't fit a cluster

For clustered issues, identify:
- The shared root cause or theme
- A representative evidence example
- A unified fix strategy

Output:
{
  "issues": [
    {
      "issue_id": "I1",
      "title": "Short descriptive title",
      "smell_ids": ["smell-X", "smell-Y"],
      "is_cluster": true,
      "root_cause": "Description of root cause",
      "severity": "critical|high|medium|low",
      "representative_evidence": {"file": "...", "line": 42},
      "total_occurrences": 3
    }
  ]
}`,
    { label: "cluster", phase: "cluster" },
  );

  // ── Phase 5: Contextualize ────────────────────────────────────────────────
  phase("contextualize");

  const contextualizeResult = await agent(
    `REFACTOR — Contextualize

Given the clustered issues and the user's original request, prioritize and contextualize.

Clustered issues:
${clusterResult}

Mode: ${mode}
Scope: ${scope ?? "codebase-wide"}

Tasks:
1. Extract the user's REAL intent from their request
2. Prioritize issues by: user intent alignment > severity > occurrence count
3. Identify which issues are most actionable given the scope
4. Estimate effort for each issue (small/medium/large)

Output prioritized issues:
{
  "user_intent": "What the user really wants",
  "prioritized_issues": [
    {
      "issue_id": "I1",
      "title": "Title",
      "priority": 1,
      "effort": "small|medium|large",
      "rationale": "Why this is prioritized"
    }
  ]
}`,
    { label: "contextualize", phase: "contextualize" },
  );

  // ── Phase 6: Synthesize ────────────────────────────────────────────────────
  phase("synthesize");

  const synthesizeResult = await agent(
    `REFACTOR — Synthesize

Generate actionable work items from the prioritized issues.

Cluster analysis:
${clusterResult}

Prioritization:
${contextualizeResult}

For each issue (in priority order), produce a concrete work item:

## Refactoring Work Items

### [PRIORITY] Issue Title — Severity

**Problem**: What is wrong and why it matters

**Location(s)**:
- file:line — specific instance
- file:line — another instance

**Root Cause**: The underlying reason this smell exists

**Fix Strategy**:
1. Step-by-step fix instructions
2. Example of corrected code or pattern

**Effort**: small/medium/large
**Impact**: What improves after fixing this

---

Present ALL work items. The output drives the developer's refactoring plan.`,
    { label: "synthesize", phase: "synthesize" },
  );

  const work_items = synthesizeResult;
  return { work_items };
