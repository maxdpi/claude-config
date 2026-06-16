---
name: deepthink
description: Invoke IMMEDIATELY to run structured divergent reasoning on an open-ended analytical question. You (the lead) orchestrate it — clarify context, design sub-questions, dispatch divergent-reasoner workers, then synthesize a confidence-rated answer. Do NOT explore first; run the workflow.
---

# DeepThink

When this skill activates, **you are the lead.** You run the 14-step structured
reasoning workflow below: perform context clarification, abstraction, and planning
yourself, then dispatch divergent-reasoner workers in parallel for the fan-out
phase, aggregate their outputs, and synthesize a confidence-rated answer.

## How to run it

The divergent-reasoner workers (step 9 fan-out, Full mode only) run in parallel.
Pick the dispatch mechanism by environment:

- **Agent Teams enabled** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`): spawn them as
  **teammates** — "Spawn a teammate using the `developer` agent type as
  *divergent-reasoner-1* …", "Spawn a teammate using the `developer` agent type as
  *divergent-reasoner-2* …", "Spawn a teammate using the `developer` agent type as
  *divergent-reasoner-3* …". Each receives a distinct sub-question framing so they
  explore different solution spaces independently. The durable hooks
  (TaskCreated / TaskCompleted / TeammateIdle / SubagentStop) mirror progress into
  the substrate. On resume, re-spawn a fresh team for the remaining work (teammates
  are ephemeral).
- **Agent Teams disabled** (default): spawn them as **Agent-tool subagents** in one
  parallel batch — `Agent(subagent_type='developer', …)` for each divergent-reasoner.
  Same prompts, same durable events (via the SubagentStart/Stop hooks). This is the
  normal path.

Either way: the worker role is the registered subagent type `developer`
(divergent-reasoner); you (the lead / `architect` perspective) own steps 1–8 and
10–14. Put the step 9 instructions below into each worker's spawn prompt.

**Mode selection:**
- **Full mode** (default): all 14 steps, including parallel divergent fan-out
  (steps 6–11) with 3 `developer` teammates/subagents.
- **Quick mode**: skips steps 6–11; proceeds directly from planning (step 5) to
  initial synthesis (step 12). Use when the question is straightforward.

> Do NOT pre-author anything under `~/.claude/teams` or `~/.claude/tasks` — those are
> runtime-owned and reaped/overwritten by Claude Code.

## DeepThink — 14-Step Methodology

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

### Step 9 — Dispatch  *(divergent-reasoner workers — developer — Full mode only)*
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

## Cross-run knowledge

`memory:` frontmatter is NOT applied to teammates (Claude Code limitation), so
cross-run knowledge is NOT carried via teammate memory. If accumulated reasoning
patterns are useful across runs, the lead reads/writes a curated `.md` note in the
run dir at start/end (substrate-owned), not teammate `memory:`.
