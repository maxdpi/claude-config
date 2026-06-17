Title: Common workflows - Claude Code Docs

URL Source: https://docs.anthropic.com/en/docs/claude-code/common-workflows

Markdown Content:
This page collects short recipes for everyday development. For higher-level guidance on prompting and context management, see [Best practices](https://code.claude.com/docs/en/best-practices).This page covers:

*   [Prompt recipes](https://docs.anthropic.com/en/docs/claude-code/common-workflows#prompt-recipes) for exploring code, fixing bugs, refactoring, testing, PRs, and documentation
*   [Resume previous conversations](https://docs.anthropic.com/en/docs/claude-code/common-workflows#resume-previous-conversations) so a task can span multiple sittings
*   [Run parallel sessions with worktrees](https://docs.anthropic.com/en/docs/claude-code/common-workflows#run-parallel-sessions-with-worktrees) so concurrent edits don’t collide
*   [Plan before editing](https://docs.anthropic.com/en/docs/claude-code/common-workflows#plan-before-editing) to review changes before they touch disk
*   [Delegate research to subagents](https://docs.anthropic.com/en/docs/claude-code/common-workflows#delegate-research-to-subagents) to keep your main context clean
*   [Pipe Claude into scripts](https://docs.anthropic.com/en/docs/claude-code/common-workflows#pipe-claude-into-scripts) for CI and batch processing

## Prompt recipes

These are prompt patterns for everyday tasks like exploring unfamiliar code, debugging, refactoring, writing tests, and creating PRs. Each works in any Claude Code surface; adapt the wording to your project.

### Understand new codebases

For configuring Claude Code in a monorepo or large codebase, see [Monorepos and large repos](https://code.claude.com/docs/en/large-codebases).

#### Get a quick codebase overview

Suppose you’ve just joined a new project and need to understand its structure quickly.

1

2

3

4

#### Find relevant code

Suppose you need to locate code related to a specific feature or functionality.

1

2

3

* * *

### Fix bugs efficiently

Suppose you’ve encountered an error message and need to find and fix its source.

1

2

3

* * *

### Refactor code

Suppose you need to update old code to use modern patterns and practices.

1

2

3

4

* * *

### Work with tests

Suppose you need to add tests for uncovered code.

1

2

3

4

Claude can generate tests that follow your project’s existing patterns and conventions. When asking for tests, be specific about what behavior you want to verify. Claude examines your existing test files to match the style, frameworks, and assertion patterns already in use.For comprehensive coverage, ask Claude to identify edge cases you might have missed. Claude can analyze your code paths and suggest tests for error conditions, boundary values, and unexpected inputs that are easy to overlook.

* * *

### Create pull requests

You can create pull requests by asking Claude directly (“create a pr for my changes”), or guide Claude through it step-by-step:

1

2

3

When you create a PR using `gh pr create`, the session is automatically linked to that PR. To return to it later, run `claude --from-pr <number>` or paste the PR URL into the [`/resume` picker](https://code.claude.com/docs/en/sessions#use-the-session-picker) search.

### Handle documentation

Suppose you need to add or update documentation for your code.

1

2

3

4

* * *

### Work in notes and non-code folders

Claude Code works in any directory. Run it inside a notes vault, a documentation folder, or any collection of markdown files to search, edit, and reorganize content the same way you would code.The `.claude/` directory and `CLAUDE.md` sit alongside other tools’ config directories without conflict. Claude reads files fresh on each tool call, so it sees edits you make in another application the next time it reads that file.

* * *

### Work with images

Suppose you need to work with images in your codebase, and you want Claude’s help analyzing image content.

1

2

3

4

* * *

### Reference files and directories

Use @ to quickly include files or directories without waiting for Claude to read them.

1

2

3

* * *

### Run Claude on a schedule

Suppose you want Claude to handle a task automatically on a recurring basis, like reviewing open PRs every morning, auditing dependencies weekly, or checking for CI failures overnight.Pick a scheduling option based on where you want the task to run:

| Option | Where it runs | Best for |
| --- | --- | --- |
| [Routines](https://code.claude.com/docs/en/routines) | Anthropic-managed infrastructure | Tasks that should run even when your computer is off. Can also trigger on API calls or GitHub events in addition to a schedule. Configure at [claude.ai/code/routines](https://claude.ai/code/routines). |
| [Desktop scheduled tasks](https://code.claude.com/docs/en/desktop-scheduled-tasks) | Your machine, via the desktop app | Tasks that need direct access to local files, tools, or uncommitted changes. |
| [GitHub Actions](https://code.claude.com/docs/en/github-actions) | Your CI pipeline | Tasks tied to repo events like opened PRs, or cron schedules that should live alongside your workflow config. |
| [`/loop`](https://code.claude.com/docs/en/scheduled-tasks) | The current CLI session | Quick polling while a session is open. Tasks stop when you start a new conversation; `--resume` and `--continue` restore unexpired ones. |

* * *

### Ask Claude about its capabilities

Claude has built-in access to its documentation and can answer questions about its own features and limitations.

#### Example questions

```
can Claude Code create pull requests?
```

```
how does Claude Code handle permissions?
```

```
what skills are available?
```

```
how do I use MCP with Claude Code?
```

```
how do I configure Claude Code for Amazon Bedrock?
```

```
what are the limitations of Claude Code?
```

* * *

## Resume previous conversations

When a task spans multiple sittings, pick up where you left off instead of re-explaining context. Claude Code saves every conversation locally.

```
claude --continue
```

This resumes the most recent session in the current directory; if there isn’t one yet, it prints `No conversation found to continue` and exits. Use `claude --resume` to choose from a list, or `/resume` from inside a running session. See [Manage sessions](https://code.claude.com/docs/en/sessions) for naming, branching, and the full picker reference.

## Run parallel sessions with worktrees

Work on a feature in one terminal while Claude fixes a bug in another, without the edits colliding. Each worktree is a separate checkout on its own branch.

```
claude --worktree feature-auth
```

Run the same command with a different name in a second terminal to start an isolated parallel session. See [Worktrees](https://code.claude.com/docs/en/worktrees) for cleanup, `.worktreeinclude`, and non-git VCS support. To monitor parallel sessions from one screen instead of separate terminals, see [background agents](https://code.claude.com/docs/en/agent-view).

## Plan before editing

For changes you want to review before they touch disk, switch to plan mode. Claude reads files and proposes a plan but makes no edits until you approve.

```
claude --permission-mode plan
```

You can also press `Shift+Tab` mid-session to toggle into plan mode. See [Plan mode](https://code.claude.com/docs/en/permission-modes#analyze-before-you-edit-with-plan-mode) for the approval flow and editing the plan in your text editor.

## Delegate research to subagents

Exploring a large codebase fills your context with file reads. Delegate the exploration so only the findings come back.

```
use a subagent to investigate how our auth system handles token refresh
```

The subagent reads files in its own context window and reports a summary. See [Subagents](https://code.claude.com/docs/en/sub-agents) for defining custom agents with their own tools and prompts.

## Pipe Claude into scripts

Run Claude non-interactively for CI, pre-commit hooks, or batch processing. Stdin and stdout work like any Unix tool.

```
git log --oneline -20 | claude -p "summarize these recent commits"
```

See [Non-interactive mode](https://code.claude.com/docs/en/headless) for output formats, permission flags, and fan-out patterns.

## Next steps
