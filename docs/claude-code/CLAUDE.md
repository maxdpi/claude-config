# Claude Code documentation (vendored mirror)

A complete, offline snapshot of the official Claude Code docs (https://code.claude.com/docs/llms.txt), organized into the folders below to mirror the docs sidebar. Each `.md` file is the raw markdown of one docs page. Regenerate with `update_official_claude_docs.py`.

Pages: 148 · Last updated: 2026-06-17

## How to navigate

1. Skim the **Sections** table to pick the right folder for the topic.
2. Open that folder's files, or use `README.md` for a flat, linked index of every page.
3. Grep the tree for a keyword when you're not sure where something lives.

## Start here

- [`getting-started/overview.md`](getting-started/overview.md) — What Claude Code is and how to install it on each surface
- [`core-concepts/how-claude-code-works.md`](core-concepts/how-claude-code-works.md) — The agentic loop and built-in tools
- [`use-claude-code/common-workflows.md`](use-claude-code/common-workflows.md) — Step-by-step recipes for everyday tasks
- [`reference/cli-reference.md`](reference/cli-reference.md) — Every CLI flag and command
- [`configuration/settings.md`](configuration/settings.md) — The full settings.json reference
- [`agent-sdk/overview.md`](agent-sdk/overview.md) — Building custom agents with the Agent SDK

## Sections

| Folder | When to read | Pages |
| ------ | ------------ | ----: |
| `getting-started/` | Install, first run, and the changelog — what Claude Code is and how to start it. | 3 |
| `core-concepts/` | The mental model: the agent loop, the .claude directory, context window, prompt caching, memory, glossary. | 7 |
| `use-claude-code/` | Day-to-day usage: permission modes, sessions, common workflows, the prompt library, best practices, goals. | 11 |
| `agents-and-parallel-work/` | Running many agents at once: subagents, agent view, agent teams, dynamic workflows, git worktrees. | 6 |
| `mcp/` | Model Context Protocol — connect Claude Code to external tools and data sources. | 3 |
| `skills/` | Authoring and using skills (reusable, shareable workflows). | 1 |
| `plugins/` | Discover, create, and distribute plugins and plugin marketplaces. | 6 |
| `automation/` | Hooks, channels (push events in), scheduled tasks/routines, headless/programmatic runs, deep links. | 9 |
| `platforms-and-integrations/` | Surfaces and integrations: web, desktop, VS Code, JetBrains, Chrome, Slack, GitHub/GitLab CI, code review. | 17 |
| `configuration/` | Settings and tunables: settings.json, model/terminal/statusline config, keybindings, env vars, sandboxing. | 12 |
| `reference/` | Exhaustive references: CLI flags, commands, and the tool list. | 3 |
| `guides/` | Task-specific setup guides (e.g. monorepos and large codebases). | 1 |
| `administration/` | Org/enterprise admin: setup, auth, security, data usage, monitoring, costs, analytics, compliance. | 14 |
| `deployment/` | Deploy via cloud providers and gateways: Bedrock, Vertex AI, Foundry, LLM gateway, devcontainer, GitHub Enterprise. | 8 |
| `troubleshooting/` | Fix install/login, performance and stability, broken config, plus the error reference. | 4 |
| `agent-sdk/` | Claude Agent SDK — build your own agents on Claude Code: Python/TypeScript references, sessions, tools, hooks, hosting. | 30 |
| `whats-new/` | Weekly release notes (newest features and changes). | 13 |

> Note: these files are a point-in-time copy and may lag the live docs. When a detail is critical, confirm against the linked original.
