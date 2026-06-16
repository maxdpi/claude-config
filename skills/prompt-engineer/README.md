# Prompt Engineer

Prompts are code. They have bugs, edge cases, and failure modes. This skill
treats prompt optimization as a systematic discipline -- analyzing issues,
applying documented patterns, and proposing changes with explicit rationale.

The skill was optimized using itself.

## When to Use

- A sub-agent definition that misbehaves (`agents/developer.md`)
- A Python script with embedded prompts that underperform
- A multi-prompt workflow that produces inconsistent results
- Any prompt that does not do what you intended

## How It Runs

The skill runs as a native Workflow-tool script (`workflow.mjs`). No Python
orchestrator, no `--step` re-invocation. The Workflow tool executes all phases
in a single linear pass.

Activation: the `Workflow` tool is invoked with
`skills/prompt-engineer/workflow.mjs`. The workflow determines scope in its
first phase and proceeds through all subsequent phases natively. Do not analyze
or explore before invoking -- the workflow IS the entry point.

## Scope Detection and Phase Flow

### Triage (phase 1)

The workflow examines the input, attached files, and prior conversation context
to classify the request into one of four scopes:

| Scope           | Trigger condition                                      |
| --------------- | ------------------------------------------------------ |
| `single-prompt` | One prompt file + general optimization request         |
| `ecosystem`     | Multiple related prompts with shared data flow         |
| `greenfield`    | No existing prompt + design/create request             |
| `problem`       | Existing prompt(s) + specific described failure        |

Scope classification is extracted from triage output and used to branch the
assess phase.

### Assess (phase 2)

Scope-specific analysis:

- **single-prompt**: Diagnoses issues by category (reasoning, consistency,
  accuracy, context, format).
- **ecosystem**: Maps each prompt's role, data flow, and cross-prompt coupling
  issues.
- **greenfield**: Derives requirements, execution context, and structural
  decisions (single-turn vs multi-turn vs multi-step).
- **problem**: Classifies the specific failure type and establishes expected
  vs actual behavior.

### Plan (phase 3)

Reads technique references from `references/` (organized by issue category:
reasoning, consistency, accuracy, context, efficiency). Maps diagnosed issues
to applicable techniques, citing trigger conditions per technique.

### Draft (phase 4)

Applies planned techniques to produce the optimized prompt(s).

Meta-constraint enforced here: changes may only ADD output instructions
(chain-of-thought triggers, format specs, verification steps). Compressing,
removing, or restructuring existing prompt text is a violation.

Each applied change is annotated with `[TECHNIQUE: name]` at the point of
application.

### Refine (phase 5)

Factored verification (CoVe, Dhuliawala 2023): for each claimed applicable
technique, the refine step closes the draft, checks the technique's exact
trigger condition from the reference, then checks the target prompt text, then
compares. Inconsistent claims are revised or removed.

For `greenfield` and `problem` scopes, an additional context-correctness check
verifies whether `<system>` wrapper / identity setup is appropriate for the
detected execution context.

### Approve (phase 6)

Presents the verified proposal to the user as a structured table (location,
opportunity, technique, risk) with per-change detail and a verification
summary. **Stops and waits for explicit user approval before proceeding.**

### Execute (phase 7)

Applies only the approved changes to the target file(s). Reads the updated
file to verify. Returns the final optimized prompt text and a summary of
applied changes as the `optimized_prompt` artifact.

## Phase Trust

Phases carry a trust manifest consumed by the workflow bridge:

| Phase   | Trust level |
| ------- | ----------- |
| triage  | read_only   |
| assess  | read_only   |
| plan    | read_only   |
| draft   | write       |
| refine  | write       |
| approve | write       |
| execute | execute     |

## Example Usage

Optimize a sub-agent:

```
Use your prompt engineer skill to optimize the system prompt for
the following claude code sub-agent: agents/developer.md
```

Optimize a multi-prompt workflow:

```
Consider @skills/planner/workflow.mjs. Identify all prompts,
understand how they interact, then use your prompt engineer skill
to optimize each.
```

## Caveat

When you tell an LLM "find problems and opportunities for optimization", it
will find problems. That is what you asked it to do. Some may not be real
issues.

Invoke the skill multiple times on challenging prompts, but recognize when the
prompt is good enough and stop. Diminishing returns are real.
