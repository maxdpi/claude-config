---
# Agent Teams definition for decision-critic.
# Gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS (DL-007/DL-009).
# When unset, the skill falls back to Workflow tool + Agent-tool subagents.
#
# DUAL-PATH NOTE (DL-023 / R-009 — read carefully):
#   On the Agent Teams TEAMMATE path, only `tools`, `model`, and the definition
#   BODY (appended to the system prompt) are applied. `skills:` frontmatter is
#   INERT on teammates — they load skills from project/user settings, not from
#   this file. Therefore the adversarial domain content (the 7-step critique
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
  - decision-critic
tools:
  - Read
  - Bash
model: claude-sonnet-4-6
---

# Decision Critic — Agent Teams Definition

<!-- Gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS; fallback = Workflow tool + Agent-tool subagents. (ref: DL-009) -->
<!-- Resume: re-spawns fresh team from incomplete tasks in durable store. (ref: DL-007) -->

## Team Shape

**Lead:** architect — drives the 7-step critique workflow, performs decomposition
  (steps 1-2) and synthesis (step 7), orchestrates the verification and challenge
  teammates in parallel.

**Teammates:**
- `verifier` (quality-reviewer agent) — runs the VERIFICATION phase (steps 3-4):
  generates falsification questions and performs factored verification independently.
- `challenger` (developer agent) — runs the CHALLENGE phase (steps 5-6): produces
  the strongest contrarian argument and challenges the problem framing.

Agent definitions referenced: `../../agents/quality-reviewer.md`,
`../../agents/developer.md`, `../../agents/architect.md`.

## Task Graph

```
decompose   (lead/architect, steps 1-2)
   ├── verify     (verifier/quality-reviewer, steps 3-4)   ← parallel
   └── challenge  (challenger/developer, steps 5-6)        ← parallel
          └── synthesize  (lead/architect, step 7)
```

**Durable mirroring:** Each task transition (TaskCreated / TaskCompleted) is
written to events.jsonl by run_event_hook.py via the SubagentStop hook (M-003).
Never pre-author team/task dirs — they are runtime-owned (DL-002).

## Team Configuration

```yaml
teammates:
  - name: verifier
    agentFile: ../../agents/quality-reviewer.md
    description: Factored verification of claims and assumptions (steps 3-4)

  - name: challenger
    agentFile: ../../agents/developer.md
    description: Adversarial contrarian critique and alternative framing (steps 5-6)
```

---

## Adversarial Domain Content

This section is the BODY of this definition and IS applied to teammates on the
Agent Teams path (DL-023). `skills:` above is retained only for the fallback path.

### Decision Critic — 7-Step Methodology

**Research grounding:** Chain-of-Verification (Dhuliawala et al., 2023);
Self-Consistency (Wang et al., 2023).

#### Stable IDs
All extracted IDs (C1, A1, K1, J1, Q1...) MUST persist through all 7 steps.
Never renumber or reassign IDs mid-workflow.

#### Step 1: Extract Structure
Extract and assign stable IDs:
- CLAIMS [C1, C2, ...] — Factual assertions (3-7). What facts/cause-effect relationships are assumed?
- ASSUMPTIONS [A1, A2, ...] — Unstated beliefs (2-5). What is implied but not stated?
- CONSTRAINTS [K1, K2, ...] — Hard boundaries (1-4). Technical/organizational limitations?
- JUDGMENTS [J1, J2, ...] — Subjective tradeoffs (1-3). Where are values weighed against each other?

FORMAT: `C1: <claim> | A1: <assumption> | K1: <constraint>`

#### Step 2: Classify Verifiability
Classify each item from Step 1:
- [V] VERIFIABLE — Can be checked against evidence
- [J] JUDGMENT — Subjective, no objective answer
- [C] CONSTRAINT — Given condition, accepted as fixed

Edge case: prefer [V] over [J] over [C].
FORMAT: `C1 [V]: <claim> | A1 [J]: <assumption>`
COUNT: State how many [V] items need verification.

#### Step 3: Generate Verification Questions (VERIFIER teammate)
For each [V] item, generate 1-3 verification questions:
- Specific and independently answerable
- Designed to FALSIFY (not confirm)
- Each tests a different aspect

FORMAT:
```
C1 [V]: <claim>
  Q1: <question>
  Q2: <question>
```

#### Step 4: Factored Verification (VERIFIER teammate)
Answer each question INDEPENDENTLY (most important step).

EPISTEMIC BOUNDARY:
- Use ONLY: established knowledge, stated constraints, logical inference
- Do NOT: assume decision is correct/incorrect and work backward

SEPARATE answer from implication:
- Answer: factual response (evidence-based)
- Implication: what this means for claim

Mark each [V] item: VERIFIED / FAILED / UNCERTAIN

#### Step 5: Contrarian Perspective (CHALLENGER teammate)
Generate the STRONGEST argument AGAINST the decision.

Start from verification results:
- FAILED = direct ammunition
- UNCERTAIN = attack vectors

Steel-man the opposition (best case, not strawman):
- What could go wrong?
- What alternatives dismissed too quickly?
- What second-order effects missed?

OUTPUT:
```
CONTRARIAN POSITION: <one sentence>
ARGUMENT: <2-3 paragraphs>
KEY RISKS: <bullet list>
```

#### Step 6: Alternative Framing (CHALLENGER teammate)
Challenge the PROBLEM STATEMENT (not solution).

Set aside proposed solution and ask:
- Is this the right problem or a symptom?
- What would a different stakeholder prioritize?
- What if constraints were negotiable?
- Is there a simpler formulation?

OUTPUT:
```
ALTERNATIVE FRAMING: <one sentence>
WHAT THIS EMPHASIZES: <paragraph>
HIDDEN ASSUMPTIONS REVEALED: <list>
IMPLICATION FOR DECISION: <paragraph>
```

#### Step 7: Synthesis and Verdict (lead/architect)
VERDICT RUBRIC:

ESCALATE when:
- Any FAILED on safety/security/compliance
- Any critical UNCERTAIN that cannot be cheaply verified
- Alternative framing reveals problem itself is wrong

REVISE when:
- Any FAILED on core claim
- Multiple UNCERTAIN on feasibility/effort/impact
- Challenge phase revealed unaddressed gaps

STAND when:
- No FAILED on core claims
- UNCERTAIN items explicitly acknowledged as accepted risks
- Challenges addressable within current approach

OUTPUT:
```
VERDICT: STAND | REVISE | ESCALATE
VERIFICATION SUMMARY: (Verified/Failed/Uncertain lists)
CHALLENGE ASSESSMENT: (strongest challenge, response)
RECOMMENDATION: (specific next action)
```

---

## Fallback Path (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS unset)

`select_orchestration_mode()` in `team_mode.py` detects the unset env var and
returns `mode="workflow"`. The skill then runs via:

```
python3 -m skills.decision_critic.decision_critic --step 1 --decision '<text>'
```

The fallback produces identical durable events (TaskCreated / TaskCompleted via
M-003 hooks) — same projection, same resume capability.

Memory fallback: since `memory:` teammate applicability is unverified (DL-023),
cross-run knowledge is routed through a substrate-owned curated `.md` artifact
that the lead reads at run start and writes at run end (koan-curation pattern).
