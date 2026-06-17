---
name: deepthink
description: Invoke IMMEDIATELY to run structured divergent reasoning on an open-ended analytical question. You (the lead) orchestrate it — clarify context, design sub-questions, dispatch divergent-reasoner workers, then synthesize a confidence-rated answer. Do NOT explore first; run the workflow.
argument-hint: [question]
allowed-tools: Read Glob Grep Bash(printenv *)
---

# DeepThink

When this skill activates, **you are the lead.** You run the 14-step structured
reasoning workflow below: perform context clarification, abstraction, and planning
yourself, then dispatch divergent-reasoner workers in parallel for the fan-out
phase, aggregate their outputs, and synthesize a confidence-rated answer.

## How to run it

The divergent-reasoner workers (step 9 fan-out, Full mode only) run in parallel.
Pick the dispatch mechanism by environment:

!`printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS | grep -q 1 && echo "AGENT_TEAMS=ON — spawn workers as teammates" || echo "AGENT_TEAMS=OFF — spawn workers as Agent-tool subagents"`

The line above is resolved **once at skill load** from the live process env, which
is authoritative — not `settings.json`'s committed value — so it reports the real
active mode without the model having to evaluate an env var it cannot observe. If it
instead reads `[shell command execution disabled by policy]`, default to OFF
(Agent-tool subagents). Scope note: this injection and the `allowed-tools` frontmatter
apply to the lead / Agent-tool path; both are **inert on the Agent Teams teammate
path**, where only `tools`/`model`/body apply.

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

At Step 1, the lead loads `skills/deepthink/methodology.md` and follows the 14-step
methodology defined there. It is kept in a separate file (loaded just-in-time)
rather than inline so this entry point stays small in always-on context; the lead
reads the full file once, and dispatch prompts to divergent-reasoner workers carry
only the relevant per-step task text (workers do not need the whole methodology
block). Mode selection (Full/Quick), dispatch topology, and the roster above remain
in this file.

## Cross-run knowledge

`memory:` frontmatter is NOT applied to teammates (Claude Code limitation), so
cross-run knowledge is NOT carried via teammate memory. If accumulated reasoning
patterns are useful across runs, the lead reads/writes a curated `.md` note in the
run dir at start/end (substrate-owned), not teammate `memory:`.
