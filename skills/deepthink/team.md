---
# Agent Teams definition for deepthink.
# Gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS (DL-007/DL-009).
# When unset, the skill falls back to Workflow tool + Agent-tool subagents.
#
# DUAL-PATH NOTE (DL-023 / R-009 — read carefully):
#   On the Agent Teams TEAMMATE path, only `tools`, `model`, and the definition
#   BODY (appended to the system prompt) are applied. `skills:` frontmatter is
#   INERT on teammates — they load skills from project/user settings, not from
#   this file. Therefore the adversarial domain content (the 14-step reasoning
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
  - deepthink
tools:
  - Read
  - Bash
  - Glob
  - Grep
model: claude-sonnet-4-6
---

# DeepThink — Agent Teams Definition

<!-- Gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS; fallback = Workflow tool + Agent-tool subagents. (ref: DL-009) -->
<!-- Resume: re-spawns fresh team from incomplete tasks in durable store. (ref: DL-007) -->

## Team Shape

**Lead:** architect — orchestrates the 14-step reasoning workflow, performs
  context clarification (steps 1-5), sub-agent design (steps 6-8), quality
  gate (step 10), aggregation (step 11), and synthesis (steps 12-14).

**Teammates:**
- `divergent-reasoner` (developer agent) × 3 — divergent reasoning sub-agents
  for step 9 Dispatch (Full mode only). Each receives a distinct sub-question
  framing so they explore different solution spaces independently.

Agent definitions referenced: `../../agents/architect.md`, `../../agents/developer.md`.

**Modes:**
- **Full mode** (default): all 14 steps, including parallel divergent fan-out (steps 6-11).
- **Quick mode**: skips steps 6-11 (the parallel developer fan-out); proceeds
  directly from planning (step 5) to initial synthesis (step 12).

## Task Graph

```
context-clarify   (lead/architect, steps 1-5)
   └── sub-agent-design  (lead/architect, steps 6-8)  [Full mode only]
          ├── divergent-reasoner-1  (developer, step 9)   ← parallel [Full]
          ├── divergent-reasoner-2  (developer, step 9)   ← parallel [Full]
          └── divergent-reasoner-3  (developer, step 9)   ← parallel [Full]
                 └── quality-gate    (lead/architect, step 10)  [Full mode only]
                        └── aggregation  (lead/architect, step 11)  [Full mode only]
                               └── synthesize  (lead/architect, steps 12-14)
```

Quick mode skips the parallel developer fan-out (steps 6-11).

**Durable mirroring:** Each task transition (TaskCreated / TaskCompleted) is
written to events.jsonl by run_event_hook.py via the SubagentStop hook (M-003).
Never pre-author team/task dirs — they are runtime-owned (DL-002).

## Team Configuration

```yaml
teammates:
  - name: divergent-reasoner
    agentFile: ../../agents/developer.md
    description: One divergent reasoning sub-agent; receives a unique sub-question framing
    count: 3
```

---

## Adversarial Domain Content

This section is the BODY of this definition and IS applied to teammates on the
Agent Teams path (DL-023). `skills:` above is retained only for the fallback path.

### DeepThink — 14-Step Methodology

**Research grounding:** System 2 Attention (S2A) bias removal; structured
  divergent-reasoning fan-out with aggregation and iterative refinement.

**MAX_ITERATIONS for step 13:** 5.

#### Step 1: Context Clarification (lead)
You are an expert analytical reasoner tasked with systematic deep analysis.

PART 0 — CONTEXT SUFFICIENCY:
Before analyzing, assess whether you have sufficient context:
- A. EXISTING CONTEXT: What relevant information is already in this conversation?
- B. SUFFICIENCY JUDGMENT: SUFFICIENT / PARTIAL / INSUFFICIENT
- C. IF NOT SUFFICIENT: Use Read/Glob/Grep to gather necessary context; stop when enough.

PART A — CLARIFIED QUESTION: Restate the core question in neutral, objective terms.
PART B — EXTRACTED CONTEXT: List factual context relevant to answering.
PART C — NOTED BIASES: Identify framing effects and embedded assumptions.

#### Step 2: Abstraction (lead)
Identify: DOMAIN, FIRST PRINCIPLES (underlying laws), KEY CONCEPTS (2-4 central ideas).

#### Step 3: Characterization (lead)
Determine QUESTION TYPE (causal / comparative / design / predictive / evaluative).
Determine ANSWER STRUCTURE (argument / explanation / recommendation / analysis).
Determine MODE: Full (complex, multi-perspective) or Quick (straightforward).

#### Step 4: Analogical Recall (lead)
- DIRECT ANALOGIES: Same domain instances with known outcomes.
- CROSS-DOMAIN ANALOGIES: Structurally similar problems in other fields.
- ANTI-PATTERNS: Approaches that failed; extract why.

#### Step 5: Planning (lead)
Decompose into SUB-QUESTIONS (2-4 targeted questions).
Define SUCCESS CRITERIA (what a complete answer must cover).

#### Step 6: Sub-Agent Design (lead — Full mode only)
Generate distinct sub-agent task definitions. Each task must:
- Address a distinct sub-question from step 5
- Have non-overlapping scope from other tasks
- Specify exactly what to research and what output format to produce

#### Step 7: Design Critique (lead — Full mode only)
Evaluate the sub-agent design for:
- COVERAGE: Does the task set span all sub-questions?
- OVERLAP: Do any tasks duplicate effort?
- APPROPRIATENESS: Is complexity matched to the question?

#### Step 8: Design Revision (lead — Full mode only)
Revise sub-agent tasks based on step 7 critique. Confirm final task definitions.

#### Step 9: Dispatch (divergent-reasoner teammates — Full mode only)
Each `divergent-reasoner` teammate executes ONE assigned sub-question task.
Use Read/Glob/Grep to gather evidence. Produce structured findings.
DO NOT coordinate with other divergent-reasoner teammates.

#### Step 10: Quality Gate (lead — Full mode only)
Review each sub-agent output. Filter low-quality outputs.
Mark each: ACCEPTED / REJECTED (with reason) / PARTIAL (note gap).

#### Step 11: Aggregation (lead — Full mode only)
Produce AGREEMENT MAP (claims all sub-agents support) and
DISAGREEMENT MAP (claims sub-agents contradict; note the conflict).

#### Step 12: Initial Synthesis (lead)
Integrate all findings (or step 5 planning if Quick mode) into a first-pass answer.
Address each sub-question. Identify remaining gaps.

#### Step 13: Iterative Refinement (lead — up to 5 iterations)
Loop until CONFIDENT or MAX_ITERATIONS reached:
- Identify the weakest claim or biggest gap in step 12
- Research or reason further to address it
- Update the synthesis

CONFIDENCE levels: exploring / low / medium / high / certain.
Proceed to step 14 when HIGH or CERTAIN, or at iteration cap.

#### Step 14: Formatting and Output (lead)
FORMAT:
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

---

## Fallback Path (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS unset)

`select_orchestration_mode()` in `team_mode.py` detects the unset env var and
returns `mode="workflow"`. The skill then runs via:

```
python3 -m skills.deepthink.think --step 1
```

The fallback produces identical durable events (TaskCreated / TaskCompleted via
M-003 hooks) — same projection, same resume capability.

Memory fallback: since `memory:` teammate applicability is unverified (DL-023),
cross-run knowledge is routed through a substrate-owned curated `.md` artifact
that the lead reads at run start and writes at run end (koan-curation pattern).
