# agents/

Subagent definitions (system prompts + frontmatter) for the six registered agent
types. All are leaf workers — `disallowedTools: Agent` (or a `tools` allowlist that
omits `Agent`) prevents them from spawning subagents. `architect` and `researcher`
are read-only (`tools: Read, Grep, Glob, Bash`); the rest retain Write/Edit.

## Files

| File                   | What                                                              | When to read                                                             |
| ---------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `architect.md`         | Architect agent: design-only, plan-before-code, escalation rules | Modifying architect behavior, understanding design boundaries            |
| `debugger.md`          | Debugger agent: evidence-first investigation, cleanup protocol   | Modifying debugger behavior, debugging investigation workflow            |
| `developer.md`         | Developer agent: spec-faithful implementation, scope rules       | Modifying developer behavior, understanding spec-adherence rules         |
| `quality-reviewer.md`  | Quality reviewer: RULE 0/1/2 hierarchy, findings format          | Modifying QR behavior, understanding review rules, adding finding categories |
| `researcher.md`        | Researcher agent: read-only adversarial critique, divergent reasoning, investigation | Modifying researcher behavior, understanding the read-only worker role for adversarial skills |
| `technical-writer.md`  | Technical writer: LLM-optimized docs, forbidden patterns         | Modifying TW behavior, understanding documentation output format         |
