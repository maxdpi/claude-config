Title: Advanced setup - Claude Code Docs

URL Source: https://docs.anthropic.com/en/docs/claude-code/setup

Markdown Content:
This page covers system requirements, platform-specific installation details, updates, and uninstallation. For a guided walkthrough of your first session, see the [quickstart](https://code.claude.com/docs/en/quickstart). If you’ve never used a terminal before, see the [terminal guide](https://code.claude.com/docs/en/terminal-guide).

## System requirements

Claude Code runs on the following platforms and configurations:

*   **Operating system**:
    *   macOS 13.0+
    *   Windows 10 1809+ or Windows Server 2019+
    *   Ubuntu 20.04+
    *   Debian 10+
    *   Alpine Linux 3.19+

*   **Hardware**: 4 GB+ RAM, x64 or ARM64 processor
*   **Network**: internet connection required. See [network configuration](https://code.claude.com/docs/en/network-config#network-access-requirements).
*   **Shell**: Bash, Zsh, PowerShell, or CMD.
*   **Location**: [Anthropic supported countries](https://www.anthropic.com/supported-countries)

### Additional dependencies

*   **ripgrep**: usually included with Claude Code. If search fails, see [search troubleshooting](https://code.claude.com/docs/en/troubleshooting#search-and-discovery-issues).

## Install Claude Code

To install Claude Code, use one of the following methods:

*   Native Install (Recommended)

*   Homebrew

*   WinGet

**macOS, Linux, WSL:**

```
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows PowerShell:**

```
irm https://claude.ai/install.ps1 | iex
```

**Windows CMD:**

```
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd
```

If you see `The token '&&' is not a valid statement separator`, you’re in PowerShell, not CMD. If you see `'irm' is not recognized as an internal or external command`, you’re in CMD, not PowerShell. Your prompt shows `PS C:\` when you’re in PowerShell and `C:\` without the `PS` when you’re in CMD.[Git for Windows](https://git-scm.com/downloads/win) is recommended on native Windows so Claude Code can use the Bash tool. If Git for Windows is not installed, Claude Code uses PowerShell as the shell tool instead. WSL setups do not need Git for Windows.

```
brew install --cask claude-code
```

Homebrew offers two casks. `claude-code` tracks the stable release channel, which is typically about a week behind and skips releases with major regressions. `claude-code@latest` tracks the latest channel and receives new versions as soon as they ship.

```
winget install Anthropic.ClaudeCode
```

You can also install with [apt, dnf, or apk](https://code.claude.com/docs/en/setup#install-with-linux-package-managers) on Debian, Fedora, RHEL, and Alpine.After installation completes, open a terminal in the project you want to work in and start Claude Code:

```
claude
```

If you encounter any issues during installation, see [Troubleshoot installation and login](https://code.claude.com/docs/en/troubleshoot-install).

### Set up on Windows

You can run Claude Code natively on Windows or inside WSL. Pick based on where your projects are located and which features you need:

| Option | Requires | [Sandboxing](https://code.claude.com/docs/en/sandboxing) | When to use |
| --- | --- | --- | --- |
| Native Windows | None; [Git for Windows](https://git-scm.com/downloads/win) is optional | Not supported | Windows-native projects and tools |
| WSL 2 | WSL 2 enabled | Supported | Linux toolchains or sandboxed command execution |
| WSL 1 | WSL 1 enabled | Not supported | If WSL 2 is unavailable |

**Option 1: Native Windows**Run the install command from PowerShell or CMD. You do not need to run as Administrator. Installing [Git for Windows](https://git-scm.com/downloads/win) is optional. It enables the [Bash tool](https://code.claude.com/docs/en/tools-reference#bash-tool-behavior) by providing Git Bash.Whether you install from PowerShell or CMD only affects which install command you run. Your prompt shows `PS C:\Users\YourName>` in PowerShell and `C:\Users\YourName>` without the `PS` in CMD. If you’re new to the terminal, the [terminal guide](https://code.claude.com/docs/en/terminal-guide#windows) walks through each step.After installation, launch `claude` from any terminal.

*   **Without Git for Windows**, Claude Code runs shell commands via the [PowerShell tool](https://code.claude.com/docs/en/tools-reference#powershell-tool).
*   **With Git for Windows**, Claude Code uses Git Bash for the [Bash tool](https://code.claude.com/docs/en/tools-reference#bash-tool-behavior). If Claude Code can’t find Git Bash, set the path in your [settings.json file](https://code.claude.com/docs/en/settings):```
{
  "env": {
    "CLAUDE_CODE_GIT_BASH_PATH": "C:\\Program Files\\Git\\bin\\bash.exe"
  }
}
``` 

When Git for Windows is installed, the PowerShell tool is rolling out progressively as an additional option alongside Bash. Set `CLAUDE_CODE_USE_POWERSHELL_TOOL=1` to opt in or `0` to opt out. See [PowerShell tool](https://code.claude.com/docs/en/tools-reference#powershell-tool) for setup and limitations.**Option 2: WSL**Open your WSL distribution and run the Linux installer from the [install instructions](https://docs.anthropic.com/en/docs/claude-code/setup#install-claude-code) above. You install and launch `claude` inside the WSL terminal, not from PowerShell or CMD.

### Alpine Linux and musl-based distributions

The native installer on Alpine and other musl/uClibc-based distributions requires `libgcc`, `libstdc++`, and `ripgrep`. Install these using your distribution’s package manager, then set `USE_BUILTIN_RIPGREP=0`.This example installs the required packages on Alpine:

```
apk add libgcc libstdc++ ripgrep
```

Then set `USE_BUILTIN_RIPGREP` to `0` in your [`settings.json`](https://code.claude.com/docs/en/settings#available-settings) file:

```
{
  "env": {
    "USE_BUILTIN_RIPGREP": "0"
  }
}
```

## Verify your installation

After installing, confirm Claude Code is working:

```
claude --version
```

If this fails with `command not found` or another error, see [Troubleshoot installation and login](https://code.claude.com/docs/en/troubleshoot-install).For a more detailed check of your installation and configuration, run [`claude doctor`](https://code.claude.com/docs/en/troubleshooting#get-more-help):

```
claude doctor
```

## Authenticate

Claude Code requires a Pro, Max, Team, Enterprise, or Console account. The free Claude.ai plan does not include Claude Code access. You can also use Claude Code with a third-party API provider like [Amazon Bedrock](https://code.claude.com/docs/en/amazon-bedrock), [Google Vertex AI](https://code.claude.com/docs/en/google-vertex-ai), or [Microsoft Foundry](https://code.claude.com/docs/en/microsoft-foundry).After installing, log in by running `claude` and following the browser prompts. See [Authentication](https://code.claude.com/docs/en/authentication) for all account types and team setup options.

## Update Claude Code

Native installations automatically update in the background. You can [configure the release channel](https://docs.anthropic.com/en/docs/claude-code/setup#configure-release-channel) to control whether you receive updates immediately or on a delayed stable schedule, or [disable auto-updates](https://docs.anthropic.com/en/docs/claude-code/setup#disable-auto-updates) entirely. Homebrew, WinGet, and [Linux package manager](https://docs.anthropic.com/en/docs/claude-code/setup#install-with-linux-package-managers) installations require manual updates by default.

### Auto-updates

Claude Code checks for updates on startup and periodically while running. Updates download and install in the background, then take effect the next time you start Claude Code.Run `claude doctor` to see the result of the most recent update attempt.If an npm global install can’t auto-update because the npm global directory isn’t writable, Claude Code shows a one-time notice at startup, and `claude doctor` lists the available fixes. See [permission errors during installation](https://code.claude.com/docs/en/troubleshoot-install#permission-errors-during-installation) for details.

### Configure release channel

Control which release channel Claude Code follows for auto-updates and `claude update` with the `autoUpdatesChannel` setting:

*   `"latest"`, the default: receive new features as soon as they’re released
*   `"stable"`: use a version that is typically about one week old, skipping releases with major regressions

Configure this via `/config` → **Auto-update channel**, or add it to your [settings.json file](https://code.claude.com/docs/en/settings):

```
{
  "autoUpdatesChannel": "stable"
}
```

For enterprise deployments, you can enforce a consistent release channel across your organization using [managed settings](https://code.claude.com/docs/en/permissions#managed-settings).Homebrew installations choose a channel by cask name instead of this setting: `claude-code` tracks stable and `claude-code@latest` tracks latest.

### Pin a minimum version

The `minimumVersion` setting establishes a floor. Background auto-updates and `claude update` refuse to install any version below this value, so moving to the `"stable"` channel does not downgrade you if you are already on a newer `"latest"` build.Switching from `"latest"` to `"stable"` via `/config` prompts you to either stay on the current version or allow the downgrade. Choosing to stay sets `minimumVersion` to that version. Switching back to `"latest"` clears it.Add it to your [settings.json file](https://code.claude.com/docs/en/settings) to pin a floor explicitly:

```
{
  "autoUpdatesChannel": "stable",
  "minimumVersion": "2.1.100"
}
```

In [managed settings](https://code.claude.com/docs/en/permissions#managed-settings), this enforces an organization-wide minimum that user and project settings cannot override.The `minimumVersion` pin only constrains updates. To make Claude Code refuse to start outside a version range, use the managed settings `requiredMinimumVersion` and `requiredMaximumVersion` instead. Updates also respect the `requiredMaximumVersion` ceiling. See [available settings](https://code.claude.com/docs/en/settings#available-settings).

### Disable auto-updates

Set `DISABLE_AUTOUPDATER` to `"1"` in the `env` key of your [`settings.json`](https://code.claude.com/docs/en/settings#available-settings) file:

```
{
  "env": {
    "DISABLE_AUTOUPDATER": "1"
  }
}
```

`DISABLE_AUTOUPDATER` only stops the background check; `claude update` and `claude install` still work. To block all update paths, including manual updates, set [`DISABLE_UPDATES`](https://code.claude.com/docs/en/env-vars) instead. Use this when you distribute Claude Code through your own channels and need users to stay on the version you provide.

### Update manually

To apply an update immediately without waiting for the next background check, run:

```
claude update
```

## Advanced installation options

These options are for version pinning, Linux package managers, npm, and verifying binary integrity.

### Install a specific version

The native installer accepts either a specific version number or a release channel (`latest` or `stable`). The channel you choose at install time becomes your default for auto-updates. See [configure release channel](https://docs.anthropic.com/en/docs/claude-code/setup#configure-release-channel) for more information.To install the latest version (default):

*   macOS, Linux, WSL

*   Windows PowerShell

*   Windows CMD

```
curl -fsSL https://claude.ai/install.sh | bash
```

```
irm https://claude.ai/install.ps1 | iex
```

```
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd
```

To install the stable version:

*   macOS, Linux, WSL

*   Windows PowerShell

*   Windows CMD

```
curl -fsSL https://claude.ai/install.sh | bash -s stable
```

```
& ([scriptblock]::Create((irm https://claude.ai/install.ps1))) stable
```

```
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd stable && del install.cmd
```

To install a specific version number:

*   macOS, Linux, WSL

*   Windows PowerShell

*   Windows CMD

```
curl -fsSL https://claude.ai/install.sh | bash -s 2.1.89
```

```
& ([scriptblock]::Create((irm https://claude.ai/install.ps1))) 2.1.89
```

```
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd 2.1.89 && del install.cmd
```

### Install with Linux package managers

Claude Code publishes signed apt, dnf, and apk repositories. Each repository offers two channels: `stable` serves a version that is typically about one week old, skipping releases with major regressions, and `latest` serves every release as soon as it ships. The commands below configure the `stable` channel, which fits most users; each tab also shows the `latest` repository URL. Package manager installations do not auto-update through Claude Code; updates arrive through your normal system upgrade workflow.All repositories are signed with the [Claude Code release signing key](https://docs.anthropic.com/en/docs/claude-code/setup#binary-integrity-and-code-signing). Before trusting the key, verify it as described in each tab.

*   apt

*   dnf

*   apk

For Debian and Ubuntu. The following commands configure the `stable` channel:

```
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://downloads.claude.ai/keys/claude-code.asc \
  -o /etc/apt/keyrings/claude-code.asc
echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
  | sudo tee /etc/apt/sources.list.d/claude-code.list
sudo apt update
sudo apt install claude-code
```

To use the `latest` channel instead, both the URL path and the suite name change. Use this `deb` line:

```
echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/latest latest main" \
  | sudo tee /etc/apt/sources.list.d/claude-code.list
```

Verify the GPG key fingerprint before trusting it: `gpg --show-keys /etc/apt/keyrings/claude-code.asc` should report `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE`.To upgrade later, run `sudo apt update && sudo apt upgrade claude-code`.

For Fedora and RHEL. The following commands configure the `stable` channel:

```
sudo tee /etc/yum.repos.d/claude-code.repo <<'EOF'
[claude-code]
name=Claude Code
baseurl=https://downloads.claude.ai/claude-code/rpm/stable
enabled=1
gpgcheck=1
gpgkey=https://downloads.claude.ai/keys/claude-code.asc
EOF
sudo dnf install claude-code
```

To use the `latest` channel instead, set `baseurl` to the `latest` repository:

```
baseurl=https://downloads.claude.ai/claude-code/rpm/latest
```

dnf downloads the key on first install and prompts you to confirm the fingerprint. Verify it matches `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE` before accepting.To upgrade later, run `sudo dnf upgrade claude-code`.

For Alpine Linux. The following commands configure the `stable` channel:

```
wget -O /etc/apk/keys/claude-code.rsa.pub \
  https://downloads.claude.ai/keys/claude-code.rsa.pub
echo "https://downloads.claude.ai/claude-code/apk/stable" >> /etc/apk/repositories
apk add claude-code
```

To switch to the `latest` channel, remove the `stable` repository line and add the `latest` repository:

```
sed -i '\|downloads.claude.ai/claude-code/apk/stable|d' /etc/apk/repositories
echo "https://downloads.claude.ai/claude-code/apk/latest" >> /etc/apk/repositories
```

Verify the downloaded key with `sha256sum /etc/apk/keys/claude-code.rsa.pub`, which should report `395759c1f7449ef4cdef305a42e820f3c766d6090d142634ebdb049f113168b6`.To upgrade later, run `apk update && apk upgrade claude-code`.

### Install with npm

You can also install Claude Code as a global npm package. The package requires [Node.js 18 or later](https://nodejs.org/en/download).

```
npm install -g @anthropic-ai/claude-code
```

The npm package installs the same native binary as the standalone installer. npm pulls the binary in through a per-platform optional dependency such as `@anthropic-ai/claude-code-darwin-arm64`, and a postinstall step links it into place. The installed `claude` binary does not itself invoke Node.Supported npm install platforms are `darwin-arm64`, `darwin-x64`, `linux-x64`, `linux-arm64`, `linux-x64-musl`, `linux-arm64-musl`, `win32-x64`, and `win32-arm64`. Your package manager must allow optional dependencies. See [troubleshooting](https://code.claude.com/docs/en/troubleshoot-install#native-binary-not-found-after-npm-install) if the binary is missing after install.To upgrade an npm installation, run `npm install -g @anthropic-ai/claude-code@latest`. Avoid `npm update -g`, which respects the semver range from the original install and may not move you to the newest release.

### Binary integrity and code signing

Each release publishes a `manifest.json` containing SHA256 checksums for every platform binary. The manifest is signed with an Anthropic GPG key, so verifying the signature on the manifest transitively verifies every binary it lists.

#### Verify the manifest signature

Steps 1-3 require a POSIX shell with `gpg` and `curl`. On Windows, run them in Git Bash or WSL. Step 4 includes a PowerShell option.

1

2

3

4

#### Platform code signatures

In addition to the signed manifest, individual binaries carry platform-native code signatures where supported.

*   **macOS**: signed by “Anthropic PBC” and notarized by Apple. Verify with `codesign --verify --verbose ./claude`.
*   **Windows**: signed by “Anthropic, PBC”. Verify with `Get-AuthenticodeSignature .\claude.exe`.
*   **Linux**: binaries are not individually code-signed. If you download directly from the `claude-code-releases` bucket or use the native installer, verify integrity with the manifest signature above. If you install with [apt, dnf, or apk](https://docs.anthropic.com/en/docs/claude-code/setup#install-with-linux-package-managers), your package manager verifies signatures automatically using the repository signing key.

## Uninstall Claude Code

To remove Claude Code, follow the instructions for your installation method. If `claude` still runs afterward, you likely have a second installation or a leftover shell alias from an older installer. See [Check for conflicting installations](https://code.claude.com/docs/en/troubleshoot-install#check-for-conflicting-installations) to find and remove it.

### Native installation

Remove the Claude Code binary and version files:

*   macOS, Linux, WSL

*   Windows PowerShell

```
rm -f ~/.local/bin/claude
rm -rf ~/.local/share/claude
```

```
Remove-Item -Path "$env:USERPROFILE\.local\bin\claude.exe" -Force
Remove-Item -Path "$env:USERPROFILE\.local\share\claude" -Recurse -Force
```

### Homebrew installation

Remove the Homebrew cask you installed. If you installed the stable cask:

```
brew uninstall --cask claude-code
```

If you installed the latest cask:

```
brew uninstall --cask claude-code@latest
```

### WinGet installation

Remove the WinGet package:

```
winget uninstall Anthropic.ClaudeCode
```

### apt / dnf / apk

Remove the package and the repository configuration:

*   apt

*   dnf

*   apk

```
sudo apt remove claude-code
sudo rm /etc/apt/sources.list.d/claude-code.list /etc/apt/keyrings/claude-code.asc
```

```
sudo dnf remove claude-code
sudo rm /etc/yum.repos.d/claude-code.repo
```

```
apk del claude-code
sed -i '\|downloads.claude.ai/claude-code/apk|d' /etc/apk/repositories
rm /etc/apk/keys/claude-code.rsa.pub
```

### npm

Remove the global npm package:

```
npm uninstall -g @anthropic-ai/claude-code
```

### Remove configuration files

The VS Code extension, the JetBrains plugin, and the Desktop app also write to `~/.claude/`. If any of them is still installed, the directory is recreated the next time it runs. To remove Claude Code completely, uninstall the [VS Code extension](https://code.claude.com/docs/en/vs-code#uninstall-the-extension), the JetBrains plugin, and the Desktop app before deleting these files.To remove Claude Code settings and cached data:

*   macOS, Linux, WSL

*   Windows PowerShell

```
# Remove user settings and state
rm -rf ~/.claude
rm ~/.claude.json

# Remove project-specific settings (run from your project directory)
rm -rf .claude
rm -f .mcp.json
```

```
# Remove user settings and state
Remove-Item -Path "$env:USERPROFILE\.claude" -Recurse -Force
Remove-Item -Path "$env:USERPROFILE\.claude.json" -Force

# Remove project-specific settings (run from your project directory)
Remove-Item -Path ".claude" -Recurse -Force
Remove-Item -Path ".mcp.json" -Force
```
