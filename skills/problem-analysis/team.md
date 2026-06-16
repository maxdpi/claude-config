---
# Agent Teams definition for problem-analysis.
# Gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS (DL-007/DL-009).
# When unset, the skill falls back to Workflow tool + Agent-tool subagents.
#
# DUAL-PATH NOTE (DL-023 / R-009 — read carefully):
#   On the Agent Teams TEAMMATE path, only `tools`, `model`, and the definition
#   BODY (appended to the system prompt) are applied. `skills:` frontmatter is
#   INERT on teammates — they load skills from project/user settings, not from
#   this file. Therefore the adversarial domain content (the 5-step root cause
#   methodology below) is embedded in this BODY so it reaches teammates on the
#   teams path. The `skills:` entry below is a fallback-path mechanism only,
#   retained so the Workflow+subagent path loads this skill correctly.
#
# `memory: project` teammate applicability is UNVERIFIED (DL-023).
#   Gate: teammate_memory_probe.py; when CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
#   is unset the probe records honored=null/unverifiable and selects the
#   curated-.md fallback. `memory:` is not listed here pending the probe result.
#
# `Agent(type)` parenthesized list is IGNORED inside a definition body.
#   Use bare `Agent`; teammates cannot spawn teammates.
skills:
  - problem-analysis
tools:
  - Read
  - Bash
  - Glob
  - Grep
model: claude-sonnet-4-6
---

# Problem Analysis — Agent Teams Definition

<!-- Gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS; fallback = Workflow tool + Agent-tool subagents. (ref: DL-009) -->
<!-- Resume: re-spawns fresh team from incomplete tasks in durable store. (ref: DL-007) -->

## Team Shape

**Lead:** architect — orchestrates the 5-step root cause workflow, performs
  gate (step 1), hypothesize (step 2), formulate (step 4), and output (step 5).

**Teammates:**
- `investigator` (developer agent) — runs iterative evidence gathering (step 3,
  up to 5 iterations). Uses Read/Glob/Grep to gather evidence per hypothesis and
  reports back to the lead with structured findings.

Agent definitions referenced: `../../agents/architect.md`, `../../agents/developer.md`.

**This skill identifies root causes, NOT solutions.**
It ends when the root cause is identified with supporting evidence.
Solution discovery is downstream.

## Task Graph

```
gate         (lead/architect, step 1)
   └── hypothesize  (lead/architect, step 2)
          └── investigate × N  (investigator/developer, step 3, up to 5 iterations)
                 └── formulate  (lead/architect, step 4)
                        └── output  (lead/architect, step 5)
```

Each investigate iteration is a separate task so the durable store can record
progress; a crash mid-investigation resumes at the next iteration (DL-007).

**Durable mirroring:** Each task transition (TaskCreated / TaskCompleted) is
written to events.jsonl by run_event_hook.py via the SubagentStop hook (M-003).
Never pre-author team/task dirs — they are runtime-owned (DL-002).

## Team Configuration

```yaml
teammates:
  - name: investigator
    agentFile: ../../agents/developer.md
    description: Evidence gathering per hypothesis; reads code, tests, logs
```

---

## Adversarial Domain Content

This section is the BODY of this definition and IS applied to teammates on the
Agent Teams path (DL-023). `skills:` above is retained only for the fallback path.

### Problem Analysis — 5-Step Methodology

**MAX_ITERATIONS for step 3:** 5.

#### Step 1: Gate (lead)
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

#### Step 2: Hypothesize (lead)
GENERATE 2-4 DISTINCT HYPOTHESES. Each must:
- Differ on mechanism or location (not just phrasing)
- Be framed as a CONDITION THAT EXISTS, not an absence
- Predict something examinable

FRAMING RULES (critical):
- WRONG: "The validation is missing"
- RIGHT: "User input reaches the database query without sanitization"

RANK BY PLAUSIBILITY. Include INVESTIGATION PLAN.

#### Step 3: Investigate (investigator/developer teammate — up to 5 iterations)
SELECT what to examine: highest-priority OPEN hypothesis, OR deepen SUPPORTED, OR explore unexplored aspect.

EXAMINE specific code, configuration, or documentation. Note exact files and line numbers.

ASSESS findings: SUPPORTS / CONTRADICTS / NEITHER (be specific with file:line references).

UPDATE hypothesis status: SUPPORTED / CONTRADICTED / OPEN.

ANSWER READINESS QUESTIONS:
- Q1 EVIDENCE: Can you cite specific code/config/docs? [YES/PARTIAL/NO]
- Q2 ALTERNATIVES: Did you examine at least one alternative? [YES/PARTIAL/NO]
- Q3 EXPLANATION: Does root cause fully explain the symptom? [YES/PARTIAL/NO]
- Q4 FRAMING: Is root cause a positive condition (not absence)? [YES/NO]

COMPUTE CONFIDENCE: 4 pts = HIGH (proceed); 3-3.5 = MEDIUM; 2-2.5 = LOW; <2 = INSUFFICIENT.

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

#### Step 4: Formulate (lead)
STATE THE ROOT CAUSE: `The system exhibits [symptom] because [condition exists]`

The condition must be:
- Specific enough to locate (points to code/config)
- General enough to allow multiple remediation approaches

TRACE THE CAUSAL CHAIN: `[root cause] -> [intermediate] -> [intermediate] -> [symptom]`

VALIDATE FRAMING (critical):
- CHECK 1 — Positive framing: No "lack of", "missing", "no X"? WRONG: "system lacks validation" RIGHT: "user input flows directly to SQL without sanitization"
- CHECK 2 — Solution independence: Does not prescribe exactly one solution?

DOCUMENT UNCERTAINTIES.

#### Step 5: Output (lead)
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

---

## Fallback Path (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS unset)

`select_orchestration_mode()` in `team_mode.py` detects the unset env var and
returns `mode="workflow"`. The skill then runs via:

```
python3 -m skills.problem_analysis.analyze --step 1
```

The fallback produces identical durable events (TaskCreated / TaskCompleted via
M-003 hooks) — same projection, same resume capability.

Memory fallback: since `memory:` teammate applicability is unverified (DL-023),
cross-run knowledge is routed through a substrate-owned curated `.md` artifact
that the lead reads at run start and writes at run end (koan-curation pattern).
