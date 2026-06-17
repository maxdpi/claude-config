# DeepThink — 14-Step Methodology

Loaded just-in-time by the lead at Step 1 (kept out of `SKILL.md`'s always-on
context so the entry point stays small). The lead follows all 14 steps; each
divergent-reasoner worker receives only its per-step task text in its spawn
prompt, not this whole file.

**Research grounding:** System 2 Attention (S2A) bias removal; structured
divergent-reasoning fan-out with aggregation and iterative refinement.

**MAX_ITERATIONS for step 13:** 5.

### Step 1 — Context Clarification  *(lead)*

You are an expert analytical reasoner tasked with systematic deep analysis.

PART 0 — CONTEXT SUFFICIENCY:
Before analyzing, assess whether you have sufficient context:
- A. EXISTING CONTEXT: What relevant information is already in this conversation?
- B. SUFFICIENCY JUDGMENT: SUFFICIENT / PARTIAL / INSUFFICIENT
- C. IF NOT SUFFICIENT: Use Read/Glob/Grep to gather necessary context; stop when enough.

PART A — CLARIFIED QUESTION: Restate the core question in neutral, objective terms.
PART B — EXTRACTED CONTEXT: List factual context relevant to answering.
PART C — NOTED BIASES: Identify framing effects and embedded assumptions.

### Step 2 — Abstraction  *(lead)*
Identify: DOMAIN, FIRST PRINCIPLES (underlying laws), KEY CONCEPTS (2–4 central ideas).

### Step 3 — Characterization  *(lead)*
Determine QUESTION TYPE (causal / comparative / design / predictive / evaluative).
Determine ANSWER STRUCTURE (argument / explanation / recommendation / analysis).
Determine MODE: Full (complex, multi-perspective) or Quick (straightforward).

### Step 4 — Analogical Recall  *(lead)*
- DIRECT ANALOGIES: Same domain instances with known outcomes.
- CROSS-DOMAIN ANALOGIES: Structurally similar problems in other fields.
- ANTI-PATTERNS: Approaches that failed; extract why.

### Step 5 — Planning  *(lead)*
Decompose into SUB-QUESTIONS (2–4 targeted questions).
Define SUCCESS CRITERIA (what a complete answer must cover).

### Step 6 — Sub-Agent Design  *(lead — Full mode only)*
Generate distinct sub-agent task definitions. Each task must:
- Address a distinct sub-question from step 5
- Have non-overlapping scope from other tasks
- Specify exactly what to research and what output format to produce

### Step 7 — Design Critique  *(lead — Full mode only)*
Evaluate the sub-agent design for:
- COVERAGE: Does the task set span all sub-questions?
- OVERLAP: Do any tasks duplicate effort?
- APPROPRIATENESS: Is complexity matched to the question?

### Step 8 — Design Revision  *(lead — Full mode only)*
Revise sub-agent tasks based on step 7 critique. Confirm final task definitions.

### Step 9 — Dispatch  *(divergent-reasoner workers — `researcher` (read-only) — Full mode only)*
Each `divergent-reasoner` worker executes ONE assigned sub-question task.
Use Read/Glob/Grep to gather evidence. Produce structured findings.
DO NOT coordinate with other divergent-reasoner workers.

### Step 10 — Quality Gate  *(lead — Full mode only)*
Review each worker output. Filter low-quality outputs.
Mark each: ACCEPTED / REJECTED (with reason) / PARTIAL (note gap).

### Step 11 — Aggregation  *(lead — Full mode only)*
Produce AGREEMENT MAP (claims all workers support) and
DISAGREEMENT MAP (claims workers contradict; note the conflict).

### Step 12 — Initial Synthesis  *(lead)*
Integrate all findings (or step 5 planning if Quick mode) into a first-pass answer.
Address each sub-question. Identify remaining gaps.

### Step 13 — Iterative Refinement  *(lead — up to 5 iterations)*
Loop until CONFIDENT or MAX_ITERATIONS reached:
- Identify the weakest claim or biggest gap in step 12
- Research or reason further to address it
- Update the synthesis

CONFIDENCE levels: exploring / low / medium / high / certain.
Proceed to step 14 when HIGH or CERTAIN, or at iteration cap.

### Step 14 — Formatting and Output  *(lead)*
```
ANSWER:
[direct response to the clarified question]

REASONING:
[step-by-step chain of logic, citing evidence]

CONFIDENCE: [HIGH / MEDIUM / LOW]
  Evidence (specific citations): [YES / PARTIAL / NO]
  Alternatives considered:       [YES / PARTIAL / NO]
  Explanation complete:          [YES / PARTIAL / NO]

REMAINING UNCERTAINTIES:
- [what wasn't resolved]
```
