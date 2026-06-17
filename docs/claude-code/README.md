# Claude Code Documentation

Complete mirror of the official Claude Code documentation, organized
into folders that mirror the docs sidebar.

Source index: https://code.claude.com/docs/llms.txt

Pages: 148

Last updated: 2026-06-17 12:48:18

## Getting Started

- [Claude Code changelog](getting-started/changelog.md) ([original](https://code.claude.com/docs/en/changelog)) — Release notes for Claude Code, including new features, improvements, and bug fixes by version.
- [Overview](getting-started/overview.md) ([original](https://code.claude.com/docs/en/overview)) — Claude Code is an agentic coding tool that reads your codebase, edits files, runs commands, and integrates with your development tools. Available in your terminal, IDE, desktop app, and browser.
- [Quickstart](getting-started/quickstart.md) ([original](https://code.claude.com/docs/en/quickstart)) — Welcome to Claude Code!

## Core Concepts

- [Explore the .claude directory](core-concepts/claude-directory.md) ([original](https://code.claude.com/docs/en/claude-directory)) — Where Claude Code reads CLAUDE.md, settings.json, hooks, skills, commands, subagents, workflows, rules, and auto memory. Explore the .claude directory in your project and ~/.claude in your home directory.
- [Explore the context window](core-concepts/context-window.md) ([original](https://code.claude.com/docs/en/context-window)) — An interactive simulation of how Claude Code's context window fills during a session. See what loads automatically, what each file read costs, and when rules and hooks fire.
- [Extend Claude Code](core-concepts/features-overview.md) ([original](https://code.claude.com/docs/en/features-overview)) — Understand when to use CLAUDE.md, Skills, subagents, hooks, MCP, and plugins.
- [Glossary](core-concepts/glossary.md) ([original](https://code.claude.com/docs/en/glossary)) — Definitions for Claude Code terminology. Learn what agentic loop, compaction, CLAUDE.md, hooks, subagents, MCP, and other core concepts mean.
- [How Claude Code works](core-concepts/how-claude-code-works.md) ([original](https://code.claude.com/docs/en/how-claude-code-works)) — Understand the agentic loop, built-in tools, and how Claude Code interacts with your project.
- [How Claude remembers your project](core-concepts/memory.md) ([original](https://code.claude.com/docs/en/memory)) — Give Claude persistent instructions with CLAUDE.md files, and let Claude accumulate learnings automatically with auto memory.
- [How Claude Code uses prompt caching](core-concepts/prompt-caching.md) ([original](https://code.claude.com/docs/en/prompt-caching)) — Claude Code manages prompt caching automatically. See why a model switch triggers a slow uncached turn, what `/compact` costs, why CLAUDE.md edits don't apply mid-session, and how to check your cache hit rate.

## Use Claude Code

- [Best practices for Claude Code](use-claude-code/best-practices.md) ([original](https://code.claude.com/docs/en/best-practices)) — Tips and patterns for getting the most out of Claude Code, from configuring your environment to scaling across parallel sessions.
- [Checkpointing](use-claude-code/checkpointing.md) ([original](https://code.claude.com/docs/en/checkpointing)) — Track, rewind, and summarize Claude's edits and conversation to manage session state.
- [Common workflows](use-claude-code/common-workflows.md) ([original](https://code.claude.com/docs/en/common-workflows)) — Step-by-step guides for exploring codebases, fixing bugs, refactoring, testing, and other everyday tasks with Claude Code.
- [Speed up responses with fast mode](use-claude-code/fast-mode.md) ([original](https://code.claude.com/docs/en/fast-mode)) — Get faster Opus responses in Claude Code by toggling fast mode.
- [Keep Claude working toward a goal](use-claude-code/goal.md) ([original](https://code.claude.com/docs/en/goal)) — Set a completion condition with /goal and Claude keeps working across turns until the condition is met.
- [Interactive mode](use-claude-code/interactive-mode.md) ([original](https://code.claude.com/docs/en/interactive-mode)) — Complete reference for keyboard shortcuts, input modes, and interactive features in Claude Code sessions.
- [Choose a permission mode](use-claude-code/permission-modes.md) ([original](https://code.claude.com/docs/en/permission-modes)) — Control whether Claude asks before editing files or running commands. Cycle modes with Shift+Tab in the CLI or use the mode selector in VS Code, Desktop, and claude.ai.
- [Configure permissions](use-claude-code/permissions.md) ([original](https://code.claude.com/docs/en/permissions)) — Control what Claude Code can access and do with fine-grained permission rules, modes, and managed policies.
- [Prompt library](use-claude-code/prompt-library.md) ([original](https://code.claude.com/docs/en/prompt-library)) — Copy-paste prompts for Claude Code, tagged by task and role.
- [Manage sessions](use-claude-code/sessions.md) ([original](https://code.claude.com/docs/en/sessions)) — Name, resume, branch, and switch between Claude Code conversations. Covers `--continue`, `--resume`, `--from-pr`, the `/resume` picker, session naming, and where transcripts are stored.
- [Voice dictation](use-claude-code/voice-dictation.md) ([original](https://code.claude.com/docs/en/voice-dictation)) — Speak your prompts in the Claude Code CLI with hold-to-record or tap-to-record voice dictation.

## Agents And Parallel Work

- [Orchestrate teams of Claude Code sessions](agents-and-parallel-work/agent-teams.md) ([original](https://code.claude.com/docs/en/agent-teams)) — Coordinate multiple Claude Code instances working together as a team, with shared tasks, inter-agent messaging, and centralized management.
- [Manage multiple agents with agent view](agents-and-parallel-work/agent-view.md) ([original](https://code.claude.com/docs/en/agent-view)) — Dispatch and manage many Claude Code sessions from one screen. Agent view shows what every session is doing and which ones need your input.
- [Run agents in parallel](agents-and-parallel-work/agents.md) ([original](https://code.claude.com/docs/en/agents)) — Compare the ways Claude Code can take on multiple tasks at once: subagents, agent view, agent teams, and dynamic workflows.
- [Create custom subagents](agents-and-parallel-work/sub-agents.md) ([original](https://code.claude.com/docs/en/sub-agents)) — Create and use specialized AI subagents in Claude Code for task-specific workflows and improved context management.
- [Orchestrate subagents at scale with dynamic workflows](agents-and-parallel-work/workflows.md) ([original](https://code.claude.com/docs/en/workflows)) — Dynamic workflows orchestrate many subagents from a script Claude writes and you can rerun. Use them for codebase audits, large migrations, and cross-checked research.
- [Run parallel sessions with worktrees](agents-and-parallel-work/worktrees.md) ([original](https://code.claude.com/docs/en/worktrees)) — Isolate parallel Claude Code sessions in separate git worktrees so changes don't collide. Covers the `--worktree` flag, subagent isolation, `.worktreeinclude`, cleanup, and non-git VCS hooks.

## Mcp

- [Control MCP server access for your organization](mcp/managed-mcp.md) ([original](https://code.claude.com/docs/en/managed-mcp)) — Restrict which MCP servers users can add or connect to with managed configuration files, allowlists, and denylists.
- [Connect Claude Code to tools via MCP](mcp/mcp.md) ([original](https://code.claude.com/docs/en/mcp)) — Learn how to connect Claude Code to your tools with the Model Context Protocol.
- [Connect to MCP servers](mcp/mcp-quickstart.md) ([original](https://code.claude.com/docs/en/mcp-quickstart)) — Add an MCP server to Claude Code, verify the connection, and find the configuration on disk.

## Skills

- [Extend Claude with skills](skills/skills.md) ([original](https://code.claude.com/docs/en/skills)) — Create, manage, and share skills to extend Claude's capabilities in Claude Code. Includes custom commands and bundled skills.

## Plugins

- [Discover and install prebuilt plugins through marketplaces](plugins/discover-plugins.md) ([original](https://code.claude.com/docs/en/discover-plugins)) — Find and install plugins from marketplaces to extend Claude Code with new skills, agents, and capabilities.
- [Constrain plugin dependency versions](plugins/plugin-dependencies.md) ([original](https://code.claude.com/docs/en/plugin-dependencies)) — Declare version constraints on plugin dependencies so your plugin keeps working when an upstream plugin ships a breaking change.
- [Recommend your plugin from your CLI](plugins/plugin-hints.md) ([original](https://code.claude.com/docs/en/plugin-hints)) — Emit a one-line marker from your CLI so Claude Code prompts users to install your official plugin.
- [Create and distribute a plugin marketplace](plugins/plugin-marketplaces.md) ([original](https://code.claude.com/docs/en/plugin-marketplaces)) — Build and host plugin marketplaces to distribute Claude Code extensions across teams and communities.
- [Create plugins](plugins/plugins.md) ([original](https://code.claude.com/docs/en/plugins)) — Create custom plugins to extend Claude Code with skills, agents, hooks, and MCP servers.
- [Plugins reference](plugins/plugins-reference.md) ([original](https://code.claude.com/docs/en/plugins-reference)) — Complete technical reference for Claude Code plugin system, including schemas, CLI commands, and component specifications.

## Automation

- [Push events into a running session with channels](automation/channels.md) ([original](https://code.claude.com/docs/en/channels)) — Use channels to push messages, alerts, and webhooks into your Claude Code session from an MCP server. Forward CI results, chat messages, and monitoring events so Claude can react while you're away.
- [Channels reference](automation/channels-reference.md) ([original](https://code.claude.com/docs/en/channels-reference)) — Build an MCP server that pushes webhooks, alerts, and chat messages into a Claude Code session. Reference for the channel contract: capability declaration, notification events, reply tools, sender gating, and permission relay.
- [Launch sessions from links](automation/deep-links.md) ([original](https://code.claude.com/docs/en/deep-links)) — Open a Claude Code terminal session from a URL. Embed `claude-cli://` links in runbooks, alerts, and dashboards so a click opens Claude Code in the right repo with the right prompt.
- [Schedule recurring tasks in Claude Code Desktop](automation/desktop-scheduled-tasks.md) ([original](https://code.claude.com/docs/en/desktop-scheduled-tasks)) — Set up scheduled tasks in Claude Code Desktop to run Claude automatically on a recurring basis for daily code reviews, dependency audits, or morning briefings.
- [Run Claude Code programmatically](automation/headless.md) ([original](https://code.claude.com/docs/en/headless)) — Use the Agent SDK to run Claude Code programmatically from the CLI, Python, or TypeScript.
- [Hooks reference](automation/hooks.md) ([original](https://code.claude.com/docs/en/hooks)) — Reference for Claude Code hook events, configuration schema, JSON input/output formats, exit codes, async hooks, HTTP hooks, prompt hooks, and MCP tool hooks.
- [Automate actions with hooks](automation/hooks-guide.md) ([original](https://code.claude.com/docs/en/hooks-guide)) — Run shell commands automatically when Claude Code edits files, finishes tasks, or needs input. Format code, send notifications, validate commands, and enforce project rules.
- [Automate work with routines](automation/routines.md) ([original](https://code.claude.com/docs/en/routines)) — Put Claude Code on autopilot. Define routines that run on a schedule, trigger on API calls, or react to GitHub events from Anthropic-managed cloud infrastructure.
- [Run prompts on a schedule](automation/scheduled-tasks.md) ([original](https://code.claude.com/docs/en/scheduled-tasks)) — Use /loop and the cron scheduling tools to run prompts repeatedly, poll for status, or set one-time reminders within a Claude Code session.

## Platforms And Integrations

- [Use Claude Code with Chrome (beta)](platforms-and-integrations/chrome.md) ([original](https://code.claude.com/docs/en/chrome)) — Connect Claude Code to your Chrome browser to test web apps, debug with console logs, automate form filling, and extract data from web pages.
- [Use Claude Code on the web](platforms-and-integrations/claude-code-on-the-web.md) ([original](https://code.claude.com/docs/en/claude-code-on-the-web)) — Configure cloud environments, setup scripts, network access, and Docker in Anthropic's sandbox. Move sessions between web and terminal with `--remote` and `--teleport`.
- [Code Review](platforms-and-integrations/code-review.md) ([original](https://code.claude.com/docs/en/code-review)) — Set up automated PR reviews that catch logic errors, security vulnerabilities, and regressions using multi-agent analysis of your full codebase
- [Let Claude use your computer from the CLI](platforms-and-integrations/computer-use.md) ([original](https://code.claude.com/docs/en/computer-use)) — Enable computer use in the Claude Code CLI so Claude can open apps, click, type, and see your screen on macOS. Test native apps, debug visual issues, and automate GUI-only tools without leaving your terminal.
- [Desktop application](platforms-and-integrations/desktop.md) ([original](https://code.claude.com/docs/en/desktop)) — Get more out of Claude Code Desktop: parallel sessions with Git isolation, drag-and-drop pane layout, integrated terminal and file editor, side chats, computer use, Dispatch sessions from your phone, visual diff review, app previews, PR monitoring, connectors, and enterprise configuration.
- [Get started with the desktop app](platforms-and-integrations/desktop-quickstart.md) ([original](https://code.claude.com/docs/en/desktop-quickstart)) — Install Claude Code on desktop and start your first coding session
- [Claude Code GitHub Actions](platforms-and-integrations/github-actions.md) ([original](https://code.claude.com/docs/en/github-actions)) — Learn about integrating Claude Code into your development workflow with Claude Code GitHub Actions
- [Claude Code GitLab CI/CD](platforms-and-integrations/gitlab-ci-cd.md) ([original](https://code.claude.com/docs/en/gitlab-ci-cd)) — Learn about integrating Claude Code into your development workflow with GitLab CI/CD
- [JetBrains IDEs](platforms-and-integrations/jetbrains.md) ([original](https://code.claude.com/docs/en/jetbrains)) — Use Claude Code with JetBrains IDEs including IntelliJ, PyCharm, WebStorm, and more
- [Platforms and integrations](platforms-and-integrations/platforms.md) ([original](https://code.claude.com/docs/en/platforms)) — Choose where to run Claude Code and what to connect it to. Compare the CLI, Desktop, VS Code, JetBrains, web, mobile, and integrations like Chrome, Slack, and CI/CD.
- [Continue local sessions from any device with Remote Control](platforms-and-integrations/remote-control.md) ([original](https://code.claude.com/docs/en/remote-control)) — Continue a local Claude Code session from your phone, tablet, or any browser using Remote Control. Works with claude.ai/code and the Claude mobile app.
- [Catch security issues as Claude writes code](platforms-and-integrations/security-guidance.md) ([original](https://code.claude.com/docs/en/security-guidance)) — Install the security-guidance plugin to have Claude review its own code changes for vulnerabilities and fix them in the same session.
- [Claude Code in Slack](platforms-and-integrations/slack.md) ([original](https://code.claude.com/docs/en/slack)) — Delegate coding tasks directly from your Slack workspace
- [Plan in the cloud with ultraplan](platforms-and-integrations/ultraplan.md) ([original](https://code.claude.com/docs/en/ultraplan)) — Start a plan from your CLI, draft it on Claude Code on the web, then execute it remotely or back in your terminal
- [Find bugs with ultrareview](platforms-and-integrations/ultrareview.md) ([original](https://code.claude.com/docs/en/ultrareview)) — Run a deep, multi-agent code review in the cloud with /code-review ultra to find and verify bugs before you merge.
- [Use Claude Code in VS Code](platforms-and-integrations/vs-code.md) ([original](https://code.claude.com/docs/en/vs-code)) — Install and configure the Claude Code extension for VS Code. Get AI coding assistance with inline diffs, @-mentions, plan review, and keyboard shortcuts.
- [Get started with Claude Code on the web](platforms-and-integrations/web-quickstart.md) ([original](https://code.claude.com/docs/en/web-quickstart)) — Run Claude Code in the cloud from your browser or phone. Connect a GitHub repository, submit a task, and review the PR without local setup.

## Configuration

- [Escalate hard decisions with the advisor tool](configuration/advisor.md) ([original](https://code.claude.com/docs/en/advisor)) — Pair your main model with a stronger advisor model that Claude consults at key moments during a task.
- [Configure auto mode](configuration/auto-mode-config.md) ([original](https://code.claude.com/docs/en/auto-mode-config)) — Tell the auto mode classifier which repos, buckets, and domains your organization trusts. Set environment context, override the default block and allow rules, and inspect your effective config with the auto-mode CLI subcommands.
- [Environment variables](configuration/env-vars.md) ([original](https://code.claude.com/docs/en/env-vars)) — Reference for environment variables that control Claude Code behavior.
- [Fullscreen rendering](configuration/fullscreen.md) ([original](https://code.claude.com/docs/en/fullscreen)) — Enable a smoother, flicker-free rendering mode with mouse support and stable memory usage in long conversations.
- [Customize keyboard shortcuts](configuration/keybindings.md) ([original](https://code.claude.com/docs/en/keybindings)) — Customize keyboard shortcuts in Claude Code with a keybindings configuration file.
- [Model configuration](configuration/model-config.md) ([original](https://code.claude.com/docs/en/model-config)) — Learn about the Claude Code model configuration, including model aliases like `opusplan`
- [Output styles](configuration/output-styles.md) ([original](https://code.claude.com/docs/en/output-styles)) — Adapt Claude Code for uses beyond software engineering
- [Choose a sandbox environment](configuration/sandbox-environments.md) ([original](https://code.claude.com/docs/en/sandbox-environments)) — Compare Claude Code sandbox options: the built-in sandboxed Bash tool, sandbox runtime, dev containers, Docker, and VMs. Choose the right isolation for your threat model.
- [Configure the sandboxed Bash tool](configuration/sandboxing.md) ([original](https://code.claude.com/docs/en/sandboxing)) — Learn how Claude Code's sandboxed Bash tool provides filesystem and network isolation for safer, more autonomous agent execution.
- [Claude Code settings](configuration/settings.md) ([original](https://code.claude.com/docs/en/settings)) — Configure Claude Code with global and project-level settings, and environment variables.
- [Customize your status line](configuration/statusline.md) ([original](https://code.claude.com/docs/en/statusline)) — Configure a custom status bar to monitor context window usage, costs, and git status in Claude Code
- [Configure your terminal for Claude Code](configuration/terminal-config.md) ([original](https://code.claude.com/docs/en/terminal-config)) — Fix Shift+Enter for newlines, get a terminal bell when Claude finishes, configure tmux, match the color theme, and enable Vim mode in the Claude Code CLI.

## Reference

- [CLI reference](reference/cli-reference.md) ([original](https://code.claude.com/docs/en/cli-reference)) — Complete reference for Claude Code command-line interface, including commands and flags.
- [Commands](reference/commands.md) ([original](https://code.claude.com/docs/en/commands)) — Complete reference for commands available in Claude Code, including built-in commands and bundled skills.
- [Tools reference](reference/tools-reference.md) ([original](https://code.claude.com/docs/en/tools-reference)) — Complete reference for the tools Claude Code can use, including permission requirements and per-tool behavior.

## Guides

- [Set up Claude Code in a monorepo or large codebase](guides/large-codebases.md) ([original](https://code.claude.com/docs/en/large-codebases)) — Configure Claude Code for monorepos and large single-tree codebases with nested CLAUDE.md files, sparse worktrees, code intelligence, and per-package skills so Claude stays focused on the code you're working in.

## Administration

- [Set up Claude Code for your organization](administration/admin-setup.md) ([original](https://code.claude.com/docs/en/admin-setup)) — A decision map for administrators deploying Claude Code, covering API providers, managed settings, policy enforcement, usage monitoring, and data handling.
- [Track team usage with analytics](administration/analytics.md) ([original](https://code.claude.com/docs/en/analytics)) — View Claude Code usage metrics, track adoption, and measure engineering velocity in the analytics dashboard.
- [Authentication](administration/authentication.md) ([original](https://code.claude.com/docs/en/authentication)) — Log in to Claude Code and configure authentication for individuals, teams, and organizations.
- [Champion kit](administration/champion-kit.md) ([original](https://code.claude.com/docs/en/champion-kit)) — A playbook for engineers advocating Claude Code internally: what to share, how to answer questions, and how to grow adoption on your team.
- [Communications kit](administration/communications-kit.md) ([original](https://code.claude.com/docs/en/communications-kit)) — Launch announcements, drip-campaign messages, and FAQ responses for rolling Claude Code out to your engineering organization.
- [Manage costs effectively](administration/costs.md) ([original](https://code.claude.com/docs/en/costs)) — Track token usage, set team spend limits, and reduce Claude Code costs with context management, model selection, extended thinking settings, and preprocessing hooks.
- [Data usage](administration/data-usage.md) ([original](https://code.claude.com/docs/en/data-usage)) — Learn about Anthropic's data usage policies for Claude
- [Legal and compliance](administration/legal-and-compliance.md) ([original](https://code.claude.com/docs/en/legal-and-compliance)) — Legal agreements, compliance certifications, and security information for Claude Code.
- [Monitoring](administration/monitoring-usage.md) ([original](https://code.claude.com/docs/en/monitoring-usage)) — Learn how to enable and configure OpenTelemetry for Claude Code.
- [Enterprise network configuration](administration/network-config.md) ([original](https://code.claude.com/docs/en/network-config)) — Configure Claude Code for enterprise environments with proxy servers, custom Certificate Authorities (CA), and mutual Transport Layer Security (mTLS) authentication.
- [Security](administration/security.md) ([original](https://code.claude.com/docs/en/security)) — Learn about Claude Code's security safeguards and best practices for safe usage.
- [Configure server-managed settings](administration/server-managed-settings.md) ([original](https://code.claude.com/docs/en/server-managed-settings)) — Centrally configure Claude Code for your organization through server-delivered settings, without requiring device management infrastructure.
- [Advanced setup](administration/setup.md) ([original](https://code.claude.com/docs/en/setup)) — System requirements, platform-specific installation, version management, and uninstallation for Claude Code.
- [Zero data retention](administration/zero-data-retention.md) ([original](https://code.claude.com/docs/en/zero-data-retention)) — Learn about Zero Data Retention (ZDR) for Claude Code, available to qualified accounts on Claude for Enterprise, including scope, disabled features, and how to request enablement.

## Deployment

- [Claude Code on Amazon Bedrock](deployment/amazon-bedrock.md) ([original](https://code.claude.com/docs/en/amazon-bedrock)) — Learn about configuring Claude Code through Amazon Bedrock, including setup, IAM configuration, and troubleshooting.
- [Claude Code on Claude Platform on AWS](deployment/claude-platform-on-aws.md) ([original](https://code.claude.com/docs/en/claude-platform-on-aws)) — Configure Claude Code to use the Anthropic-operated Claude API with AWS authentication, IAM access control, and AWS Marketplace billing.
- [Development containers](deployment/devcontainer.md) ([original](https://code.claude.com/docs/en/devcontainer)) — Run Claude Code inside a dev container for consistent, isolated environments across your team.
- [Claude Code with GitHub Enterprise Server](deployment/github-enterprise-server.md) ([original](https://code.claude.com/docs/en/github-enterprise-server)) — Connect Claude Code to your self-hosted GitHub Enterprise Server instance for web sessions, code review, and plugin marketplaces.
- [Claude Code on Google Vertex AI](deployment/google-vertex-ai.md) ([original](https://code.claude.com/docs/en/google-vertex-ai)) — Learn about configuring Claude Code through Google Vertex AI, including setup, IAM configuration, and troubleshooting.
- [LLM gateway configuration](deployment/llm-gateway.md) ([original](https://code.claude.com/docs/en/llm-gateway)) — Learn how to configure Claude Code to work with LLM gateway solutions. Covers gateway requirements, authentication configuration, model selection, and provider-specific endpoint setup.
- [Claude Code on Microsoft Foundry](deployment/microsoft-foundry.md) ([original](https://code.claude.com/docs/en/microsoft-foundry)) — Learn about configuring Claude Code through Microsoft Foundry, including setup, configuration, and troubleshooting.
- [Enterprise deployment overview](deployment/third-party-integrations.md) ([original](https://code.claude.com/docs/en/third-party-integrations)) — Learn how Claude Code can integrate with various third-party services and infrastructure to meet enterprise deployment requirements.

## Troubleshooting

- [Debug your configuration](troubleshooting/debug-your-config.md) ([original](https://code.claude.com/docs/en/debug-your-config)) — Diagnose why CLAUDE.md, settings, hooks, MCP servers, or skills aren't taking effect. Use /context, /doctor, /hooks, and /mcp to see what actually loaded.
- [Error reference](troubleshooting/errors.md) ([original](https://code.claude.com/docs/en/errors)) — Look up Claude Code runtime error messages with what each one means and how to fix it.
- [Troubleshoot installation and login](troubleshooting/troubleshoot-install.md) ([original](https://code.claude.com/docs/en/troubleshoot-install)) — Fix command not found, PATH, permission, network, and authentication errors when installing or signing in to Claude Code.
- [Troubleshooting](troubleshooting/troubleshooting.md) ([original](https://code.claude.com/docs/en/troubleshooting)) — Fix high CPU or memory usage, hangs, auto-compact thrashing, and search problems in Claude Code, and find the right page for other issues.

## Agent Sdk

- [How the agent loop works](agent-sdk/agent-loop.md) ([original](https://code.claude.com/docs/en/agent-sdk/agent-loop)) — Understand the message lifecycle, tool execution, context window, and architecture that power your SDK agents.
- [Use Claude Code features in the SDK](agent-sdk/claude-code-features.md) ([original](https://code.claude.com/docs/en/agent-sdk/claude-code-features)) — Load project instructions, skills, hooks, and other Claude Code features into your SDK agents.
- [Track cost and usage](agent-sdk/cost-tracking.md) ([original](https://code.claude.com/docs/en/agent-sdk/cost-tracking)) — Learn how to track token usage, estimate costs, and configure prompt caching with the Claude Agent SDK.
- [Give Claude custom tools](agent-sdk/custom-tools.md) ([original](https://code.claude.com/docs/en/agent-sdk/custom-tools)) — Define custom tools with the Claude Agent SDK's in-process MCP server so Claude can call your functions, hit your APIs, and perform domain-specific operations.
- [Rewind file changes with checkpointing](agent-sdk/file-checkpointing.md) ([original](https://code.claude.com/docs/en/agent-sdk/file-checkpointing)) — Track file changes during agent sessions and restore files to any previous state
- [Intercept and control agent behavior with hooks](agent-sdk/hooks.md) ([original](https://code.claude.com/docs/en/agent-sdk/hooks)) — Intercept and customize agent behavior at key execution points with hooks
- [Hosting the Agent SDK](agent-sdk/hosting.md) ([original](https://code.claude.com/docs/en/agent-sdk/hosting)) — Deploy the Agent SDK in production: subprocess architecture, session persistence, scaling, observability, and multi-tenant isolation for Docker, Kubernetes, and sandbox providers.
- [Connect to external tools with MCP](agent-sdk/mcp.md) ([original](https://code.claude.com/docs/en/agent-sdk/mcp)) — Configure MCP servers to extend your agent with external tools. Covers transport types, tool search for large tool sets, authentication, and error handling.
- [Migrate to Claude Agent SDK](agent-sdk/migration-guide.md) ([original](https://code.claude.com/docs/en/agent-sdk/migration-guide)) — Guide for migrating the Claude Code TypeScript and Python SDKs to the Claude Agent SDK
- [Modifying system prompts](agent-sdk/modifying-system-prompts.md) ([original](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts)) — Choose between the `claude_code` preset and a custom system prompt, and customize behavior with CLAUDE.md, output styles, append, or a fully custom prompt.
- [Observability with OpenTelemetry](agent-sdk/observability.md) ([original](https://code.claude.com/docs/en/agent-sdk/observability)) — Export traces, metrics, and events from the Agent SDK to your observability backend using OpenTelemetry.
- [Agent SDK overview](agent-sdk/overview.md) ([original](https://code.claude.com/docs/en/agent-sdk/overview)) — Build production AI agents with Claude Code as a library
- [Configure permissions](agent-sdk/permissions.md) ([original](https://code.claude.com/docs/en/agent-sdk/permissions)) — Control how your agent uses tools with permission modes, hooks, and declarative allow/deny rules.
- [Plugins in the SDK](agent-sdk/plugins.md) ([original](https://code.claude.com/docs/en/agent-sdk/plugins)) — Load custom plugins to extend Claude Code with skills, agents, hooks, and MCP servers through the Agent SDK
- [Agent SDK reference - Python](agent-sdk/python.md) ([original](https://code.claude.com/docs/en/agent-sdk/python)) — Complete API reference for the Python Agent SDK, including all functions, types, and classes.
- [Quickstart](agent-sdk/quickstart.md) ([original](https://code.claude.com/docs/en/agent-sdk/quickstart)) — Get started with the Python or TypeScript Agent SDK to build AI agents that work autonomously
- [Securely deploying AI agents](agent-sdk/secure-deployment.md) ([original](https://code.claude.com/docs/en/agent-sdk/secure-deployment)) — A guide to securing Claude Code and Agent SDK deployments with isolation, credential management, and network controls
- [Persist sessions to external storage](agent-sdk/session-storage.md) ([original](https://code.claude.com/docs/en/agent-sdk/session-storage)) — Mirror session transcripts to S3, Redis, or your own backend so any host can resume them.
- [Work with sessions](agent-sdk/sessions.md) ([original](https://code.claude.com/docs/en/agent-sdk/sessions)) — How sessions persist agent conversation history, and when to use continue, resume, and fork to return to a prior run.
- [Agent Skills in the SDK](agent-sdk/skills.md) ([original](https://code.claude.com/docs/en/agent-sdk/skills)) — Extend Claude with specialized capabilities using Agent Skills in the Claude Agent SDK
- [Slash Commands in the SDK](agent-sdk/slash-commands.md) ([original](https://code.claude.com/docs/en/agent-sdk/slash-commands)) — Learn how to use slash commands to control Claude Code sessions through the SDK
- [Stream responses in real-time](agent-sdk/streaming-output.md) ([original](https://code.claude.com/docs/en/agent-sdk/streaming-output)) — Get real-time responses from the Agent SDK as text and tool calls stream in
- [Streaming Input](agent-sdk/streaming-vs-single-mode.md) ([original](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)) — Understanding the two input modes for Claude Agent SDK and when to use each
- [Get structured output from agents](agent-sdk/structured-outputs.md) ([original](https://code.claude.com/docs/en/agent-sdk/structured-outputs)) — Return validated JSON from agent workflows using JSON Schema, Zod, or Pydantic. Get type-safe, structured data after multi-turn tool use.
- [Subagents in the SDK](agent-sdk/subagents.md) ([original](https://code.claude.com/docs/en/agent-sdk/subagents)) — Define and invoke subagents to isolate context, run tasks in parallel, and apply specialized instructions in your Claude Agent SDK applications.
- [Todo Lists](agent-sdk/todo-tracking.md) ([original](https://code.claude.com/docs/en/agent-sdk/todo-tracking)) — Track and display todos using the Claude Agent SDK for organized task management
- [Scale to many tools with tool search](agent-sdk/tool-search.md) ([original](https://code.claude.com/docs/en/agent-sdk/tool-search)) — Scale your agent to thousands of tools by discovering and loading only what's needed, on demand.
- [Agent SDK reference - TypeScript](agent-sdk/typescript.md) ([original](https://code.claude.com/docs/en/agent-sdk/typescript)) — Complete API reference for the TypeScript Agent SDK, including all functions, types, and interfaces.
- [TypeScript SDK V2 session API (removed)](agent-sdk/typescript-v2-preview.md) ([original](https://code.claude.com/docs/en/agent-sdk/typescript-v2-preview)) — Reference for the removed V2 TypeScript Agent SDK session API, with session-based send/stream patterns for multi-turn conversations.
- [Handle approvals and user input](agent-sdk/user-input.md) ([original](https://code.claude.com/docs/en/agent-sdk/user-input)) — Surface Claude's approval requests and clarifying questions to users, then return their decisions to the SDK.

## Whats New

- [Week 13 · March 23–27, 2026](whats-new/2026-w13.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w13)) — Auto mode for hands-off permissions, computer use built in, PR auto-fix in the cloud, transcript search, and a PowerShell tool for Windows.
- [Week 14 · March 30 – April 3, 2026](whats-new/2026-w14.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w14)) — Computer use in the CLI, interactive in-product lessons, flicker-free rendering, per-tool MCP result-size overrides, and plugin executables on PATH.
- [Week 15 · April 6–10, 2026](whats-new/2026-w15.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w15)) — Ultraplan cloud planning, the Monitor tool with self-pacing /loop, /team-onboarding for packaging your setup, and /autofix-pr from your terminal.
- [Week 16 · April 13–17, 2026](whats-new/2026-w16.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w16)) — Claude Opus 4.7 with the new xhigh effort level, Routines on Claude Code on the web, mobile push notifications that ping your phone when Claude needs you, a /usage breakdown that shows what's driving your limits, and native binaries replacing the bundled JavaScript.
- [Week 17 · April 20–24, 2026](whats-new/2026-w17.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w17)) — /ultrareview opens as a research preview, automatic session recaps when you return to a terminal, custom color themes you can build and ship in plugins, and a redesigned Claude Code on the web.
- [Week 18 · April 27 – May 1, 2026](whats-new/2026-w18.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w18)) — Claude Code on Windows runs without Git Bash, claude auth login accepts a pasted OAuth code when the browser callback can't reach localhost, claude project purge cleans up local state per project, and pasting a PR URL into /resume finds the session that created it.
- [Week 19 · May 4–8, 2026](whats-new/2026-w19.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w19)) — Load plugins from .zip archives and URLs, search command history across every project with Ctrl+R, branch new worktrees from local HEAD or the remote default, and block actions unconditionally with auto mode hard deny rules.
- [Week 20 · May 11–15, 2026](whats-new/2026-w20.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w20)) — Manage every Claude Code session from one screen with agent view, keep Claude working toward a goal until a condition holds, and run fast mode on Opus 4.7 by default.
- [Week 21 · May 18–22, 2026](whats-new/2026-w21.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w21)) — Use auto mode on the Pro plan and with Sonnet 4.6, see which skills, subagents, and MCP servers drive your plan limits in /usage, and review diffs with the new /code-review command.
- [Week 22 · May 25–29, 2026](whats-new/2026-w22.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w22)) — Run Claude Code on Claude Opus 4.8, orchestrate large tasks with dynamic workflows, catch security issues with the security-guidance plugin, and use fast mode on Opus 4.8 at a lower price.
- [Week 23 · June 1–5, 2026](whats-new/2026-w23.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w23)) — Run auto mode on Bedrock, Vertex, and Foundry, prompt before writing files that can run code in acceptEdits mode, list installed plugins with /plugin list, and require an approved version range for managed deployments.
- [Week 24 · June 8–12, 2026](whats-new/2026-w24.md) ([original](https://code.claude.com/docs/en/whats-new/2026-w24)) — Move a session to a new directory with /cd, let sub-agents spawn their own sub-agents, and troubleshoot a broken configuration with safe mode.
- [What's new](whats-new/index.md) ([original](https://code.claude.com/docs/en/whats-new/index)) — A weekly digest of notable Claude Code features, with code snippets, demos, and context on why they matter.
