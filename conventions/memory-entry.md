# Memory Entry Schema and Self-Critique Gate

Authoritative spec for a durable memory entry: its structure, and the
all-PASS checklist every drafted entry must clear before it may be proposed
to a human. The `curation` skill (`skills/curation/SKILL.md`) is the primary
consumer; any agent that writes to a persistent memory store follows this.

Memory is **deliberate, not extracted**: entries are drafted, self-critiqued,
proposed, and only written after explicit human approval. This is the opposite
of conversational-memory systems that auto-summarize dialogue. The producer and
consumer are both LLMs across separate runs; optimize for LLM recall, not human
browsing.

## The two memory stores this repo writes to

Curation does NOT invent storage. It proposes entries into one of the two
stores that already exist:

| Store                | Location                                              | Index file  | When it is the target                                              |
| -------------------- | ---------------------------------------------------- | ----------- | ------------------------------------------------------------------ |
| User auto-memory     | `~/.claude/projects/<project-slug>/memory/`          | `MEMORY.md` | Cross-session facts about the user, the project, feedback, references |
| Agent project-memory | `.claude/agent-memory/<role>/MEMORY.md`              | (the file itself) | Durable per-role review knowledge (e.g. quality-reviewer conventions) |

Both stores share the same logical entry shape below. The user auto-memory
store splits each fact into its own file plus a one-line index pointer in
`MEMORY.md`; the agent project-memory store keeps entries as sections inside a
single `MEMORY.md`. The schema is identical; only the on-disk layout differs.
The curation skill reads the target store before drafting and writes only the
target store the invocation designates — it never creates a new store.

## Entry schema

Every entry carries four parts. One entry holds exactly one durable fact.

- **name / slug** — short kebab-case identifier, stable across the entry's life.
  In the user auto-memory store this is the filename (`planner-skill-ignores-args.md`)
  and the `name:` frontmatter field. In the agent store it is the section anchor.
- **description / hook** — one line, used at recall time to decide relevance.
  It must let a future agent judge "is this entry worth opening?" without the
  body. A vague hook ("notes about the planner") fails; a sharp claim
  ("planner args-threading bug is fixed in repo; installed copy needs sync")
  passes.
- **type / category** — what kind of knowledge this is. Use the user-store
  taxonomy when writing to the user auto-memory store:
  - **user** — who the user is: role, expertise, durable preferences.
  - **feedback** — guidance on how the agent should work (corrections and
    confirmed approaches). Include the WHY.
  - **project** — ongoing work, goals, constraints not derivable from code or
    git history. Convert relative dates to absolute (see `temporal.md`).
  - **reference** — pointer to an external resource (URL, dashboard, ticket).

  Agent project-memory entries are typically **convention** or **lesson**
  facts about reviewing this repo; classify by the same single-fact rule.
- **body** — the durable fact itself, stating WHY it matters and (for feedback
  and project facts) HOW to apply it. Self-contained: readable with no access
  to the conversation, run, plan, or milestone that produced it. Link related
  entries with `[[name]]`.

### Frontmatter shape (user auto-memory store)

```markdown
---
name: <kebab-case-slug>
description: <one-line hook used for recall relevance>
metadata:
  type: user | feedback | project | reference
---

<the durable fact. For feedback/project, follow with **Why:** and **How to apply:** lines.>
<Link related entries with [[their-name]].>
```

### Index discipline

One fact per entry; the index line points to it. After writing an entry to
the user auto-memory store, add (or update) exactly one pointer line in
`MEMORY.md`:

```markdown
- [Title](slug.md) — one-line hook
```

`MEMORY.md` is a pure index loaded each session: one line per entry, no
frontmatter, never any entry body. Never duplicate body content into the index.

## Self-critique checklist gate (ALL-PASS, hard gate)

Before any drafted entry is proposed to the user, run all nine checks. **Any
FAIL blocks the proposal** — the entry must be rewritten and re-checked until
every item PASSES. Emit the per-draft PASS/FAIL result as a committed,
visible artifact (the explicit checklist output is what prevents simulated
refinement; collapsing it collapses the gate).

1. **Durable, not transient.** Records knowledge that will still matter next
   week. Temporary implementation state, one-off task status, or anything that
   drifts with the next commit FAILS.

2. **Non-obvious / not already in the codebase.** The fact is NOT recoverable
   by reading the code, CLAUDE.md, git history, or an existing entry. File
   layout, API signatures, type definitions, import paths, function names FAIL
   — the agent gets these by opening the file. If an existing entry already
   covers it, classify NOOP, not a duplicate.

3. **Grounded in evidence.** The fact is anchored to something observed: a
   user statement, a code location, a dated event, a run outcome. Opinions
   without grounding in project experience FAIL.

4. **Timeless-present per `temporal.md`.** No change-narrative ("added", "now
   uses", "refactored to"), no relative time ("recently", "currently", "at
   the moment"). Dates are absolute. Forward-looking language ("will", "should",
   "TODO") FAILS unless embedded in a past-tense attribution of a decision.

5. **Single fact.** The entry captures exactly one durable fact. If it bundles
   two unrelated facts, split into two entries (decisions are the exception:
   choice + rationale + rejected alternatives stay bundled as one fact).

6. **Description enables recall.** The one-line hook names a specific subject
   and a specific claim, so a future agent can judge relevance without opening
   the body. A topic label without a claim ("memory system") FAILS.

7. **Self-contained, not a pointer.** The body contains the actual knowledge,
   not "X documents Y" or "see file Z". Readable standalone. Run-anchored
   identifiers (milestone numbers `M5`, step numbers, initiative names, "as of
   <date>" state snapshots, `per entry N` cross-references) FAIL — inline the
   knowledge and use project-stable identifiers (named subsystems, file paths,
   function names, dated external events).

8. **Concrete naming.** Names specific entities: file paths, function names,
   tool names, versions, env-var names. "The config" FAILS; "the
   `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var" passes.

9. **Right store and type.** The entry targets the correct store (user
   auto-memory vs agent project-memory) and carries a type from that store's
   taxonomy. A fact that belongs in a code comment (scoped to one function /
   one module's rationale) is NOT a memory entry — drop it.

A draft that PASSES all nine is eligible to be proposed. Proposal is not
approval: the human still decides ADD / UPDATE / DEPRECATE / reject (see the
skill's batch loop).
