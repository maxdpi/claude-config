Title: Development containers - Claude Code Docs

URL Source: https://docs.anthropic.com/en/docs/claude-code/devcontainer

Markdown Content:
A [development container](https://containers.dev/), or dev container, lets you define an identical, isolated environment that every engineer on your team can run. With Claude Code installed in that container, commands Claude runs execute inside it rather than on the host machine, while edits to your project files appear in your local repository as you work.This page covers [installing Claude Code in a dev container](https://docs.anthropic.com/en/docs/claude-code/devcontainer#add-claude-code-to-your-dev-container) and the configuration topics that follow. Each topic is self-contained, so jump to the ones that match what you need to set up:

*   [Persist authentication and settings across rebuilds](https://docs.anthropic.com/en/docs/claude-code/devcontainer#persist-authentication-and-settings-across-rebuilds)
*   [Enforce organization policy](https://docs.anthropic.com/en/docs/claude-code/devcontainer#enforce-organization-policy)
*   [Restrict network egress](https://docs.anthropic.com/en/docs/claude-code/devcontainer#restrict-network-egress)
*   [Run without permission prompts](https://docs.anthropic.com/en/docs/claude-code/devcontainer#run-without-permission-prompts)

How dev containers work with your editor

![Image 1: Diagram showing an editor on the host connecting to a Docker dev container. Claude Code, the terminal, and build tools run inside the container. The host repository is bind-mounted into the container as the workspace.](https://mintcdn.com/claude-code/YvJyjZfd9yMihr0i/images/devcontainer-architecture.svg?fit=max&auto=format&n=YvJyjZfd9yMihr0i&q=85&s=9017b1d16a446c6cc37ba562f35b9aae)![Image 2: Diagram showing an editor on the host connecting to a Docker dev container. Claude Code, the terminal, and build tools run inside the container. The host repository is bind-mounted into the container as the workspace.](https://mintcdn.com/claude-code/YvJyjZfd9yMihr0i/images/devcontainer-architecture-dark.svg?fit=max&auto=format&n=YvJyjZfd9yMihr0i&q=85&s=ef00c8e25b1ea7a3a152895f1488831b)A dev container runs as a Docker container, either on your machine or on a cloud host such as GitHub Codespaces. An editor that supports the Dev Containers spec, such as VS Code, GitHub Codespaces, a JetBrains IDE, or Cursor, connects to that container: you browse and edit files in the editor as usual, but the integrated terminal, language servers, and build tools all run inside the container rather than on your host. Editors without dev container support, such as plain Vim, are not part of this workflow.Claude Code runs inside the container, so it sees the same files, dependencies, and tools as the rest of your project’s toolchain. In VS Code you can use either the [Claude Code extension panel](https://code.claude.com/docs/en/vs-code) or run `claude` in the integrated terminal; both run inside the container and share the same `~/.claude` configuration.

## Add Claude Code to your dev container

Claude Code installs into any dev container through the [Claude Code Dev Container Feature](https://github.com/anthropics/devcontainer-features/tree/main/src/claude-code).The settings work with any tool that supports the Dev Containers spec, such as VS Code, GitHub Codespaces, or JetBrains IDEs. The steps below use VS Code as an example.When you open the container in VS Code or Codespaces, the feature also adds the Claude Code VS Code extension; other editors ignore that part.

1

2

3

What you see at the authentication prompt depends on your provider:

*   **Anthropic**: sign in through a browser with your Claude or Anthropic Console account
*   **[Amazon Bedrock, Google Vertex AI, or Microsoft Foundry](https://code.claude.com/docs/en/third-party-integrations)**: Claude Code uses your cloud provider credentials, with no browser prompt

For cloud providers, pass credentials into the container as environment variables through `containerEnv`, a Codespaces secret, or your cloud’s workload identity rather than mounting credential files from the host. See [Amazon Bedrock](https://code.claude.com/docs/en/amazon-bedrock), [Google Vertex AI](https://code.claude.com/docs/en/google-vertex-ai), or [Microsoft Foundry](https://code.claude.com/docs/en/microsoft-foundry) for the credential chain Claude Code reads.See [Choose your API provider](https://code.claude.com/docs/en/admin-setup#choose-your-api-provider) to decide which path fits your organization.

## Persist authentication and settings across rebuilds

By default, the container’s home directory is discarded on rebuild, so engineers must sign in again each time. Claude Code stores its authentication token, user settings, and session history under [`~/.claude`](https://code.claude.com/docs/en/claude-directory). Mount a named volume at that path to keep this state across rebuilds.The following example mounts a volume at the home directory of the `node` user:

devcontainer.json

```
"mounts": [
  "source=claude-code-config,target=/home/node/.claude,type=volume"
]
```

Replace `/home/node` with the home directory of your container’s `remoteUser`. If you mount the volume somewhere other than `~/.claude`, set [`CLAUDE_CONFIG_DIR`](https://code.claude.com/docs/en/env-vars) to the mount path so Claude Code reads and writes there.To isolate state per project rather than sharing one volume across all repositories, include the `${devcontainerId}` variable in the source name. The [reference configuration](https://github.com/anthropics/claude-code/blob/main/.devcontainer/devcontainer.json) uses `source=claude-code-config-${devcontainerId}` for this purpose.In GitHub Codespaces, `~/.claude` persists across stopping and starting a codespace, but is still cleared when you rebuild the container, so the volume mount above applies there too. To carry authentication across codespaces, store `ANTHROPIC_API_KEY` or a `CLAUDE_CODE_OAUTH_TOKEN` from [`claude setup-token`](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token) as a [Codespaces secret](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces); Codespaces makes secrets available as environment variables inside the container automatically.

## Enforce organization policy

A dev container is a convenient place to apply organization policy, because the same image and configuration run on every engineer’s machine.Claude Code reads `/etc/claude-code/managed-settings.json` on Linux and applies it at the highest precedence in the [settings hierarchy](https://code.claude.com/docs/en/settings#how-scopes-interact), so values there override anything an engineer sets in `~/.claude` or the project’s `.claude/` directory. Copy the file into place from your Dockerfile:

Dockerfile

```
RUN mkdir -p /etc/claude-code
COPY managed-settings.json /etc/claude-code/managed-settings.json
```

Because the Dockerfile lives in the repository, anyone with write access can change or remove this step. For policy that engineers cannot bypass by editing repository files, deliver managed settings through [server-managed settings](https://code.claude.com/docs/en/server-managed-settings) or your MDM instead. See [managed settings files](https://code.claude.com/docs/en/settings#settings-files) for the available keys and the other delivery paths.To set [environment variables](https://code.claude.com/docs/en/env-vars) that apply to every Claude Code session in the container, add them to `containerEnv` in your `devcontainer.json`. The following example opts out of telemetry and error reporting and prevents Claude Code from auto-updating after install:

devcontainer.json

```
"containerEnv": {
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
  "DISABLE_AUTOUPDATER": "1"
}
```

The Dev Container Feature always installs the latest Claude Code release. To pin a specific Claude Code version for reproducible builds, install it from your Dockerfile with `npm install -g @anthropic-ai/claude-code@X.Y.Z` instead of using the feature, and set `DISABLE_AUTOUPDATER` as shown above.For the full list of policy controls including permission rules, tool restrictions, and MCP server allowlists, see [Set up Claude Code for your organization](https://code.claude.com/docs/en/admin-setup).To make [MCP servers](https://code.claude.com/docs/en/mcp) available inside the container, define them at [project scope](https://code.claude.com/docs/en/mcp#mcp-installation-scopes) in a `.mcp.json` file at the repository root so they are checked in alongside your dev container configuration. Install any binaries that local stdio servers depend on in your Dockerfile, and add remote server domains to your network allowlist.

## Restrict network egress

You can limit the container’s outbound traffic to only the domains Claude Code needs. See [Network access requirements](https://code.claude.com/docs/en/network-config#network-access-requirements) for the inference and authentication domains, and [Telemetry services](https://code.claude.com/docs/en/data-usage#telemetry-services) for the optional telemetry and error reporting connections and how to disable them.The reference container includes an [`init-firewall.sh`](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh) script that blocks all outbound traffic except the domains Claude Code and your development tools need. Running a firewall inside a container requires extra permissions, so the reference adds the `NET_ADMIN` and `NET_RAW` capabilities through `runArgs`. The firewall script and these capabilities are not required for Claude Code itself: you can leave them out and rely on your own network controls instead.

## Run without permission prompts

Because the container runs Claude Code as a non-root user and confines command execution to the container, you can pass `--dangerously-skip-permissions` for unattended operation. The CLI rejects this flag when launched as root, so confirm `remoteUser` is set to a non-root account.Skipping permission prompts removes your opportunity to review tool calls before they run. Claude can still modify any file in the bind-mounted workspace, which appears directly on your host, and reach anything the container’s network policy allows. Pair this flag with the [network egress restrictions](https://docs.anthropic.com/en/docs/claude-code/devcontainer#restrict-network-egress) above to limit what a bypassed session can reach.If you want fewer prompts without disabling safety checks, consider [auto mode](https://code.claude.com/docs/en/permission-modes#eliminate-prompts-with-auto-mode) instead, which has a classifier review actions before they run. To prevent engineers from using `--dangerously-skip-permissions` at all, set `permissions.disableBypassPermissionsMode` to `"disable"` in [managed settings](https://code.claude.com/docs/en/settings#permission-settings).

## Try the reference container

The [`anthropics/claude-code`](https://github.com/anthropics/claude-code/tree/main/.devcontainer) repository includes an example dev container that combines the CLI, the egress firewall, persistent volumes, and a Zsh-based shell. It is provided as a working example rather than a maintained base image; use it to see how the pieces fit together before applying them to your own configuration.

1

2

3

4

To use this configuration with your own project, copy the `.devcontainer/` directory into your repository and adjust the Dockerfile for your toolchain, or return to [Add Claude Code to your dev container](https://docs.anthropic.com/en/docs/claude-code/devcontainer#add-claude-code-to-your-dev-container) to add only the feature to a setup you already have.The reference configuration consists of three files. None of them are required when you add Claude Code to your own dev container through the feature, but they show one way to combine the pieces.

| File | Purpose |
| --- | --- |
| [`devcontainer.json`](https://github.com/anthropics/claude-code/blob/main/.devcontainer/devcontainer.json) | Volume mounts, `runArgs` capabilities, VS Code extensions, and `containerEnv` |
| [`Dockerfile`](https://github.com/anthropics/claude-code/blob/main/.devcontainer/Dockerfile) | Base image, development tools, and the Claude Code install |
| [`init-firewall.sh`](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh) | Blocks all outbound network traffic except the allowed domains |

## Next steps

Once Claude Code is running in your dev container, the pages below cover the rest of an organization rollout: choosing an authentication path, delivering managed policy outside the repository, monitoring usage, and understanding what Claude Code stores and sends.

*   [Set up Claude Code for your organization](https://code.claude.com/docs/en/admin-setup): choose an authentication provider, decide how policy reaches devices, and plan the rollout
*   [Server-managed settings](https://code.claude.com/docs/en/server-managed-settings): deliver managed policy from the Claude.ai admin console so engineers cannot bypass it by editing repository files
*   [Monitor usage and audit activity](https://code.claude.com/docs/en/monitoring-usage): export OpenTelemetry metrics and review what your team is running
*   [Network access requirements](https://code.claude.com/docs/en/network-config#network-access-requirements): the full domain allowlist for proxies and firewalls
*   [Telemetry services and opt-out](https://code.claude.com/docs/en/data-usage#telemetry-services): what Claude Code sends by default and the environment variables that disable it
*   [Explore the `.claude` directory](https://code.claude.com/docs/en/claude-directory): what the volume mount holds, including credentials, settings, and session history
*   [Sandbox environments](https://code.claude.com/docs/en/sandbox-environments): compare dev containers with the built-in Bash sandbox, custom containers, and VMs
*   [Security model](https://code.claude.com/docs/en/security): how Claude Code’s permission system, sandboxing, and prompt-injection protections fit together
*   [Permission modes](https://code.claude.com/docs/en/permission-modes): the full range from plan mode to auto mode to bypass, and when to use each
