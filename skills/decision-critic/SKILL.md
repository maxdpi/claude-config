---
name: decision-critic
description: Invoke IMMEDIATELY to stress-test a decision or piece of reasoning via an adversarial critique. You (the lead) orchestrate it — spawn adversarial workers, then synthesize a verdict. Do NOT critique first; run the workflow.
argument-hint: [decision or claim]
allowed-tools: Read Glob Grep Bash(printenv *)
---

# Decision Critic

When this skill activates, **you are the lead.** You run the 7-step adversarial
critique below: do the structural steps yourself, dispatch the verification and
challenge work to two adversarial workers in parallel, then synthesize a verdict.

## How to run it

The two adversarial workers (`verifier`, `challenger`) run in parallel. Pick the
dispatch mechanism by environment:

!`printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS | grep -q 1 && echo "AGENT_TEAMS=ON — spawn workers as teammates" || echo "AGENT_TEAMS=OFF — spawn workers as Agent-tool subagents"`

The line above is resolved **once at skill load** from the live process env, which
is authoritative — not `settings.json`'s committed value — so it reports the real
active mode without the model having to evaluate an env var it cannot observe. If it
instead reads `[shell command execution disabled by policy]`, default to OFF
(Agent-tool subagents). Scope note: this injection and the `allowed-tools` frontmatter
apply to the lead / Agent-tool path; both are **inert on the Agent Teams teammate
path**, where only `tools`/`model`/body apply.

- **Agent Teams enabled** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`): spawn them as
  **teammates** — "Spawn a teammate using the `quality-reviewer` agent type as
  *verifier* …" and "Spawn a teammate using the `researcher` agent type as
  *challenger* …". They share the task list; the durable hooks (TaskCreated /
  TaskCompleted / TeammateIdle / SubagentStop) mirror progress into the substrate.
  On resume, re-spawn a fresh team for the remaining work (teammates are ephemeral).
- **Agent Teams disabled** (default): spawn them as **Agent-tool subagents** in one
  parallel batch — `Agent(subagent_type='quality-reviewer', …)` for the verifier and
  `Agent(subagent_type='researcher', …)` for the challenger. Same prompts, same
  durable events (via the SubagentStart/Stop hooks). This is the normal path.

Either way: the worker roles are the registered subagent types `quality-reviewer`
(verifier) and `researcher` (challenger); you (the lead / `architect` perspective)
own steps 1–2 and 7. Put the step instructions below into each worker's spawn prompt.

> Do NOT pre-author anything under `~/.claude/teams` or `~/.claude/tasks` — those are
> runtime-owned and reaped/overwritten by Claude Code.

## Decision Critic — 7-Step Methodology

**Research grounding:** Chain-of-Verification (Dhuliawala et al., 2023);
Self-Consistency (Wang et al., 2023).

**Stable IDs:** every extracted ID (C1, A1, K1, J1, Q1 …) MUST persist unchanged
through all 7 steps. Never renumber mid-workflow.

### Step 1 — Extract Structure  *(lead)*
Assign stable IDs:
- CLAIMS [C1…] — factual assertions (3–7): assumed facts / cause-effect.
- ASSUMPTIONS [A1…] — unstated beliefs (2–5): implied but not stated.
- CONSTRAINTS [K1…] — hard boundaries (1–4): technical/organizational limits.
- JUDGMENTS [J1…] — subjective tradeoffs (1–3): where values are weighed.

Format: `C1: <claim> | A1: <assumption> | K1: <constraint>`

### Step 2 — Classify Verifiability  *(lead)*
Classify each item: `[V]` verifiable (checkable vs evidence), `[J]` judgment
(subjective), `[C]` constraint (given/fixed). Prefer `[V]` > `[J]` > `[C]`.
State how many `[V]` items need verification.

### Step 3 — Generate Verification Questions  *(verifier worker — quality-reviewer)*
For each `[V]` item, generate 1–3 questions that are specific, independently
answerable, and designed to FALSIFY (not confirm). Format:
```
C1 [V]: <claim>
  Q1: <question>
  Q2: <question>
```

### Step 4 — Factored Verification  *(verifier worker)*
Answer each question INDEPENDENTLY (the most important step). Epistemic boundary:
use ONLY established knowledge, stated constraints, logical inference; do NOT assume
the decision is right/wrong and work backward. Separate **Answer** (evidence-based)
from **Implication** (what it means for the claim). Mark each `[V]` item:
VERIFIED / FAILED / UNCERTAIN.

### Step 5 — Contrarian Perspective  *(challenger worker — researcher)*
Generate the STRONGEST steel-manned argument AGAINST the decision. Start from
verification results (FAILED = ammunition, UNCERTAIN = attack vectors). Output:
```
CONTRARIAN POSITION: <one sentence>
ARGUMENT: <2–3 paragraphs>
KEY RISKS: <bullets>
```

### Step 6 — Alternative Framing  *(challenger worker)*
Challenge the PROBLEM STATEMENT (not the solution): right problem or symptom? what
would a different stakeholder prioritize? what if constraints were negotiable? Output:
```
ALTERNATIVE FRAMING: <one sentence>
WHAT THIS EMPHASIZES: <paragraph>
HIDDEN ASSUMPTIONS REVEALED: <list>
IMPLICATION FOR DECISION: <paragraph>
```

### Step 7 — Synthesis & Verdict  *(lead)*
Verdict rubric:
- **ESCALATE** — any FAILED on safety/security/compliance; a critical UNCERTAIN that
  can't be cheaply verified; alternative framing shows the problem itself is wrong.
- **REVISE** — any FAILED on a core claim; multiple UNCERTAIN on feasibility/impact;
  the challenge revealed unaddressed gaps.
- **STAND** — no FAILED on core claims; UNCERTAIN items accepted as explicit risks;
  challenges addressable within the current approach.

Output:
```
VERDICT: STAND | REVISE | ESCALATE
VERIFICATION SUMMARY: <Verified / Failed / Uncertain lists>
CHALLENGE ASSESSMENT: <strongest challenge + your response>
RECOMMENDATION: <specific next action>
```

## Cross-run knowledge

`memory:` frontmatter is NOT applied to teammates (Claude Code limitation), so
cross-run knowledge is NOT carried via teammate memory. If accumulated critique
patterns are useful across runs, the lead reads/writes a curated `.md` note in the
run dir at start/end (substrate-owned), not teammate `memory:`.
