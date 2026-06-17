---
name: problem-analysis
description: Invoke IMMEDIATELY to identify root causes via competing hypotheses and iterative investigation. You (the lead) orchestrate it — gate and hypothesize yourself, dispatch investigator workers to gather evidence, then formulate the root cause. Do NOT explore first; run the workflow.
argument-hint: [problem description]
allowed-tools: Read Glob Grep Bash(printenv *)
---

# Problem Analysis

When this skill activates, **you are the lead.** You run the 5-step root cause
workflow below: gate the problem and generate hypotheses yourself, dispatch
investigator workers to gather evidence per hypothesis (this skill's canonical
adversarial case — workers challenge each other's findings), then formulate and
output the root cause.

**This skill identifies root causes, NOT solutions.** It ends when the root cause
is identified with supporting evidence. Solution discovery is downstream.

## How to run it

The investigator workers (step 3 iterative investigation) challenge the hypothesis
space independently. Pick the dispatch mechanism by environment:

!`printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS | grep -q 1 && echo "AGENT_TEAMS=ON — spawn workers as teammates" || echo "AGENT_TEAMS=OFF — spawn workers as Agent-tool subagents"`

The line above is resolved **once at skill load** from the live process env, which
is authoritative — not `settings.json`'s committed value — so it reports the real
active mode without the model having to evaluate an env var it cannot observe. If it
instead reads `[shell command execution disabled by policy]`, default to OFF
(Agent-tool subagents). Scope note: this injection and the `allowed-tools` frontmatter
apply to the lead / Agent-tool path; both are **inert on the Agent Teams teammate
path**, where only `tools`/`model`/body apply.

- **Agent Teams enabled** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`): spawn
  **N investigator teammates** in parallel — "Spawn a teammate using the `developer`
  agent type as *investigator-H1* …" (one per top-ranked hypothesis). This is the
  canonical Agent Teams use case: teammates debate each other's findings when they
  contradict. The durable hooks (TaskCreated / TaskCompleted / TeammateIdle /
  SubagentStop) mirror progress into the substrate. On resume, re-spawn a fresh team
  for the remaining investigation iterations (teammates are ephemeral).
- **Agent Teams disabled** (default): spawn them as **Agent-tool subagents** in one
  parallel batch — `Agent(subagent_type='developer', …)` for each investigator. The
  lead synthesizes their potentially-contradictory findings and drives the next
  iteration. Same durable events (via the SubagentStart/Stop hooks). This is the
  normal path.

Either way: the worker role is the registered subagent type `developer`
(investigator); you (the lead / `architect` perspective) own steps 1–2 and 4–5.
Put the step 3 instructions below into each worker's spawn prompt with its
assigned hypothesis.

**Investigation count:** up to 5 iterations of step 3. Stop early when CONFIDENCE
reaches HIGH or CERTAIN with all four readiness checks satisfied.

> Do NOT pre-author anything under `~/.claude/teams` or `~/.claude/tasks` — those are
> runtime-owned and reaped/overwritten by Claude Code.

## Problem Analysis — 5-Step Methodology

**MAX_ITERATIONS for step 3:** 5.

### Step 1 — Gate  *(lead)*

CHECK FOR MULTIPLE PROBLEMS:
- Scan input for signs of multiple distinct issues (multiple symptoms, unrelated components)
- If multiple problems → STOP. Ask user to isolate ONE problem. Do not proceed.

CHECK FOR SUFFICIENT INFORMATION:
- Problem must include: what component is affected, expected behavior, actual observed behavior
- If missing or vague → Ask for clarification.

RESTATE THE PROBLEM in observable terms:
`When [conditions], [component] exhibits [observed behavior] instead of [expected behavior]`

SEPARATE KNOWN FROM ASSUMED:
- KNOWN: From user report or visible context
- ASSUMED: Things investigation must verify

OUTPUT FORMAT:
```
VALIDATION: [PASS / BLOCKED: reason]
REFINED PROBLEM STATEMENT: When [conditions], [component] exhibits [observed] instead of [expected]
KNOWN FACTS: - [fact 1]
ASSUMPTIONS TO VERIFY: - [assumption 1]
```

### Step 2 — Hypothesize  *(lead)*

GENERATE 2–4 DISTINCT HYPOTHESES. Each must:
- Differ on mechanism or location (not just phrasing)
- Be framed as a CONDITION THAT EXISTS, not an absence
- Predict something examinable

FRAMING RULES (critical):
- WRONG: "The validation is missing"
- RIGHT: "User input reaches the database query without sanitization"

RANK BY PLAUSIBILITY. Include INVESTIGATION PLAN.

### Step 3 — Investigate  *(investigator workers — developer — up to 5 iterations)*

Each investigator worker is assigned ONE hypothesis (or one unexplored aspect).
Workers investigate independently and their findings may contradict each other —
that conflict is intentional and useful (it is the adversarial signal).

SELECT what to examine: highest-priority OPEN hypothesis, OR deepen SUPPORTED,
OR explore unexplored aspect.

EXAMINE specific code, configuration, or documentation. Note exact files and line
numbers.

ASSESS findings: SUPPORTS / CONTRADICTS / NEITHER (be specific with file:line
references).

UPDATE hypothesis status: SUPPORTED / CONTRADICTED / OPEN.

ANSWER READINESS QUESTIONS:
- Q1 EVIDENCE: Can you cite specific code/config/docs? [YES/PARTIAL/NO]
- Q2 ALTERNATIVES: Did you examine at least one alternative? [YES/PARTIAL/NO]
- Q3 EXPLANATION: Does root cause fully explain the symptom? [YES/PARTIAL/NO]
- Q4 FRAMING: Is root cause a positive condition (not absence)? [YES/NO]

COMPUTE CONFIDENCE: 4 pts = HIGH (proceed); 3–3.5 = MEDIUM; 2–2.5 = LOW; <2 = INSUFFICIENT.

OUTPUT FORMAT:
```
ITERATION FINDINGS:
Examined: [which hypothesis or aspect]
Evidence sought: [what you looked for]
Evidence found: [what you found, with file:line references]
Assessment: [SUPPORTS / CONTRADICTS / INCONCLUSIVE] because [reason]
HYPOTHESIS STATUS: - H1: [status] - [brief reason]
READINESS CHECK: Q1/Q2/Q3/Q4
CONFIDENCE: [exploring/low/medium/high/certain]
```

### Step 4 — Formulate  *(lead)*

STATE THE ROOT CAUSE: `The system exhibits [symptom] because [condition exists]`

The condition must be:
- Specific enough to locate (points to code/config)
- General enough to allow multiple remediation approaches

TRACE THE CAUSAL CHAIN: `[root cause] -> [intermediate] -> [intermediate] -> [symptom]`

VALIDATE FRAMING (critical):
- CHECK 1 — Positive framing: No "lack of", "missing", "no X"? WRONG: "system lacks
  validation" RIGHT: "user input flows directly to SQL without sanitization"
- CHECK 2 — Solution independence: Does not prescribe exactly one solution?

DOCUMENT UNCERTAINTIES.

### Step 5 — Output  *(lead)*

Compile final analysis report:

```
================================================================================
                         PROBLEM ANALYSIS REPORT
================================================================================
ORIGINAL PROBLEM: [verbatim]
REFINED PROBLEM: [observable-framed version]
ROOT CAUSE: [validated statement]
CAUSAL CHAIN: [root cause] -> [intermediate] -> [symptom]
SUPPORTING EVIDENCE: - [file:line] -- [what it shows]
CONFIDENCE: [HIGH / MEDIUM / LOW / INSUFFICIENT]
  Evidence (specific citations exist):      [YES / PARTIAL / NO]
  Alternatives (others considered):         [YES / PARTIAL / NO]
  Explanation (fully accounts for symptom): [YES / PARTIAL / NO]
  Framing (positive, solution-independent): [YES / NO]
REMAINING UNCERTAINTIES: - [what wasn't verified]
INVESTIGATION LOG: [key findings from each Step 3 iteration]
================================================================================
```

This completes the problem analysis. The root cause and supporting evidence can
now be used as input for solution discovery.

## Cross-run knowledge

`memory:` frontmatter is NOT applied to teammates (Claude Code limitation), so
cross-run knowledge is NOT carried via teammate memory. If accumulated root-cause
patterns are useful across runs, the lead reads/writes a curated `.md` note in the
run dir at start/end (substrate-owned), not teammate `memory:`.
