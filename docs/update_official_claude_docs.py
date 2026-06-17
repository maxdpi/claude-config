#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "requests>=2.31.0",
#   "rich>=13.0.0",
# ]
# ///
"""
Mirror the complete Claude Code documentation from the official docs site.

The docs live at https://code.claude.com/docs/en/ and publish a machine-readable
index at https://code.claude.com/docs/llms.txt listing every page. Each page is
also served as clean raw markdown at the same path with a ``.md`` suffix
(``text/markdown``).

This script reads llms.txt, downloads every ``.md`` page it lists (no API key
required), and sorts each page into a section folder that mirrors the official
docs sidebar (``getting-started/``, ``core-concepts/``, ``agent-sdk/``, etc.)
rather than dumping ~150 files into one directory.

New pages are still picked up automatically: anything in the index that isn't in
the section map below lands in ``misc/`` and is reported at the end so the map
can be updated.
"""

import re
import sys
import time
import argparse
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table

console = Console()

# The docs index and the prefix every page URL shares.
DOCS_INDEX = "https://code.claude.com/docs/llms.txt"
DOCS_BASE = "https://code.claude.com/docs/en"

# Matches a llms.txt entry: "- [Title](https://.../slug.md): optional description"
LINK_RE = re.compile(
    r"^\s*-\s*\[(?P<title>.+?)\]\((?P<url>"
    + re.escape(DOCS_BASE)
    + r"/[^)]+\.md)\)(?::\s*(?P<desc>.*))?\s*$"
)

# Pages whose URL path already starts with one of these prefixes are routed to a
# folder of the same name (e.g. agent-sdk/overview.md -> agent-sdk/overview.md).
PREFIX_SECTIONS = ("agent-sdk", "whats-new")

# Section -> the page slugs that belong in it, mirroring the docs sidebar.
# Order here is the display/section order used for the generated index.
SECTIONS = {
    "getting-started": [
        "overview", "quickstart", "changelog",
    ],
    "core-concepts": [
        "how-claude-code-works", "features-overview", "claude-directory",
        "context-window", "prompt-caching", "memory", "glossary",
    ],
    "use-claude-code": [
        "permission-modes", "permissions", "sessions", "common-workflows",
        "prompt-library", "best-practices", "interactive-mode", "checkpointing",
        "goal", "fast-mode", "voice-dictation",
    ],
    "agents-and-parallel-work": [
        "agents", "sub-agents", "agent-view", "agent-teams", "workflows",
        "worktrees",
    ],
    "mcp": [
        "mcp", "mcp-quickstart", "managed-mcp",
    ],
    "skills": [
        "skills",
    ],
    "plugins": [
        "plugins", "discover-plugins", "plugins-reference", "plugin-marketplaces",
        "plugin-dependencies", "plugin-hints",
    ],
    "automation": [
        "hooks-guide", "hooks", "channels", "channels-reference",
        "scheduled-tasks", "routines", "desktop-scheduled-tasks", "deep-links",
        "headless",
    ],
    "platforms-and-integrations": [
        "platforms", "remote-control", "claude-code-on-the-web", "web-quickstart",
        "desktop", "desktop-quickstart", "chrome", "computer-use", "vs-code",
        "jetbrains", "code-review", "github-actions", "gitlab-ci-cd", "slack",
        "ultrareview", "ultraplan", "security-guidance",
    ],
    "configuration": [
        "settings", "model-config", "terminal-config", "statusline", "keybindings",
        "env-vars", "output-styles", "fullscreen", "auto-mode-config", "sandboxing",
        "sandbox-environments", "advisor",
    ],
    "reference": [
        "cli-reference", "commands", "tools-reference",
    ],
    "guides": [
        "large-codebases",
    ],
    "administration": [
        "admin-setup", "setup", "authentication", "security", "data-usage",
        "monitoring-usage", "costs", "analytics", "server-managed-settings",
        "network-config", "legal-and-compliance", "zero-data-retention",
        "champion-kit", "communications-kit",
    ],
    "deployment": [
        "third-party-integrations", "amazon-bedrock", "google-vertex-ai",
        "microsoft-foundry", "llm-gateway", "devcontainer",
        "github-enterprise-server", "claude-platform-on-aws",
    ],
    "troubleshooting": [
        "troubleshoot-install", "troubleshooting", "debug-your-config", "errors",
    ],
    # agent-sdk and whats-new are appended dynamically via PREFIX_SECTIONS.
}

# Reverse lookup: slug -> section, built once at import time.
_SLUG_TO_SECTION = {slug: section for section, slugs in SECTIONS.items() for slug in slugs}

# Fallback bucket for pages not present in SECTIONS or PREFIX_SECTIONS.
MISC_SECTION = "misc"

# One-line "when to read" guidance per section, used to build the navigation
# CLAUDE.md so agents can jump to the right folder without scanning every file.
SECTION_GUIDE = {
    "getting-started": "Install, first run, and the changelog — what Claude Code is and how to start it.",
    "core-concepts": "The mental model: the agent loop, the .claude directory, context window, prompt caching, memory, glossary.",
    "use-claude-code": "Day-to-day usage: permission modes, sessions, common workflows, the prompt library, best practices, goals.",
    "agents-and-parallel-work": "Running many agents at once: subagents, agent view, agent teams, dynamic workflows, git worktrees.",
    "mcp": "Model Context Protocol — connect Claude Code to external tools and data sources.",
    "skills": "Authoring and using skills (reusable, shareable workflows).",
    "plugins": "Discover, create, and distribute plugins and plugin marketplaces.",
    "automation": "Hooks, channels (push events in), scheduled tasks/routines, headless/programmatic runs, deep links.",
    "platforms-and-integrations": "Surfaces and integrations: web, desktop, VS Code, JetBrains, Chrome, Slack, GitHub/GitLab CI, code review.",
    "configuration": "Settings and tunables: settings.json, model/terminal/statusline config, keybindings, env vars, sandboxing.",
    "reference": "Exhaustive references: CLI flags, commands, and the tool list.",
    "guides": "Task-specific setup guides (e.g. monorepos and large codebases).",
    "administration": "Org/enterprise admin: setup, auth, security, data usage, monitoring, costs, analytics, compliance.",
    "deployment": "Deploy via cloud providers and gateways: Bedrock, Vertex AI, Foundry, LLM gateway, devcontainer, GitHub Enterprise.",
    "troubleshooting": "Fix install/login, performance and stability, broken config, plus the error reference.",
    "agent-sdk": "Claude Agent SDK — build your own agents on Claude Code: Python/TypeScript references, sessions, tools, hooks, hosting.",
    "whats-new": "Weekly release notes (newest features and changes).",
    MISC_SECTION: "Pages not yet mapped to a section (update SECTIONS in the fetch script).",
}

# A few high-value entry points to surface at the top of the navigation guide.
# Keys are page slugs (URL path after DOCS_BASE, without ".md").
KEY_ENTRY_POINTS = [
    ("overview", "What Claude Code is and how to install it on each surface"),
    ("how-claude-code-works", "The agentic loop and built-in tools"),
    ("common-workflows", "Step-by-step recipes for everyday tasks"),
    ("cli-reference", "Every CLI flag and command"),
    ("settings", "The full settings.json reference"),
    ("agent-sdk/overview", "Building custom agents with the Agent SDK"),
]


def categorize(relpath):
    """Return (section, filename) for a page's path relative to DOCS_BASE."""
    if "/" in relpath:
        prefix, _, rest = relpath.partition("/")
        if prefix in PREFIX_SECTIONS:
            return prefix, rest
        # Unexpected nesting: keep its own folder so nothing collides.
        return prefix, rest
    return _SLUG_TO_SECTION.get(relpath, MISC_SECTION), relpath


def discover_pages(session, filter_substr=None):
    """Read llms.txt and return a de-duplicated list of page dicts."""
    resp = session.get(DOCS_INDEX, timeout=30)
    resp.raise_for_status()

    pages = []
    seen = set()
    for line in resp.text.splitlines():
        m = LINK_RE.match(line)
        if not m:
            continue
        url = m.group("url")
        if url in seen:
            continue
        seen.add(url)
        relpath = url[len(DOCS_BASE) + 1:]  # e.g. "overview.md" or "agent-sdk/overview.md"
        slug = relpath[:-3] if relpath.endswith(".md") else relpath
        if filter_substr and filter_substr not in slug:
            continue
        section, filename = categorize(slug)
        pages.append({
            "title": m.group("title"),
            "url": url,
            "slug": slug,
            "desc": m.group("desc") or "",
            "section": section,
            "relpath": f"{section}/{filename}.md",
        })
    return pages


def _strip_index_banner(text):
    """Drop the leading "Documentation Index" blockquote the docs site prepends."""
    lines = text.splitlines(keepends=True)
    i = 0
    # Skip an initial run of blockquote lines (the injected banner) plus blanks.
    while i < len(lines) and (lines[i].lstrip().startswith(">") or not lines[i].strip()):
        i += 1
    return "".join(lines[i:]).lstrip("\n") if i else text


def fetch_page(session, url, output_path, rate_limit_delay=0.5):
    """Fetch a single documentation page (raw markdown) and write it to disk."""
    headers = {
        "Accept": "text/markdown, text/plain, */*",
        "User-Agent": "claude-config-docs-fetcher",
    }

    try:
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        content = _strip_index_banner(response.text)

        # Create directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Be polite between requests
        time.sleep(rate_limit_delay)

        return (str(output_path), True, f"{len(content):,} chars")

    except Exception as e:
        return (str(output_path), False, str(e))


def section_order():
    """Section display order: explicit map, then prefix sections, then misc."""
    return list(SECTIONS.keys()) + list(PREFIX_SECTIONS) + [MISC_SECTION]


def write_index(directory, pages):
    """Write a README.md grouping pages by section."""
    by_section = {}
    for p in pages:
        by_section.setdefault(p["section"], []).append(p)

    ordered = [s for s in section_order() if s in by_section]
    ordered += [s for s in sorted(by_section) if s not in ordered]

    index_path = directory / "README.md"
    with open(index_path, "w") as f:
        f.write("# Claude Code Documentation\n\n")
        f.write("Complete mirror of the official Claude Code documentation, organized\n")
        f.write("into folders that mirror the docs sidebar.\n\n")
        f.write(f"Source index: {DOCS_INDEX}\n\n")
        f.write(f"Pages: {len(pages)}\n\n")
        f.write(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        for section in ordered:
            items = sorted(by_section[section], key=lambda x: x["slug"])
            pretty = section.replace("-", " ").title()
            f.write(f"\n## {pretty}\n\n")
            for p in items:
                page_url = p["url"][:-3]  # drop ".md" for the canonical link
                suffix = f" — {p['desc']}" if p["desc"] else ""
                f.write(f"- [{p['title']}]({p['relpath']}) ([original]({page_url})){suffix}\n")
    return index_path


def write_claude_md(directory, pages):
    """Write a CLAUDE.md navigation guide at the root of the docs mirror."""
    by_section = {}
    for p in pages:
        by_section.setdefault(p["section"], []).append(p)

    ordered = [s for s in section_order() if s in by_section]
    ordered += [s for s in sorted(by_section) if s not in ordered]

    # Only surface entry points that actually exist in this run.
    by_slug = {p["slug"]: p for p in pages}

    path = directory / "CLAUDE.md"
    with open(path, "w") as f:
        f.write("# Claude Code documentation (vendored mirror)\n\n")
        f.write(
            "A complete, offline snapshot of the official Claude Code docs "
            f"({DOCS_INDEX}), organized into the folders below to mirror the docs "
            "sidebar. Each `.md` file is the raw markdown of one docs page. "
            "Regenerate with `update_official_claude_docs.py`.\n\n"
        )
        f.write(f"Pages: {len(pages)} · Last updated: {time.strftime('%Y-%m-%d')}\n\n")

        f.write("## How to navigate\n\n")
        f.write(
            "1. Skim the **Sections** table to pick the right folder for the topic.\n"
            "2. Open that folder's files, or use `README.md` for a flat, linked index of every page.\n"
            "3. Grep the tree for a keyword when you're not sure where something lives.\n\n"
        )

        f.write("## Start here\n\n")
        for slug, why in KEY_ENTRY_POINTS:
            p = by_slug.get(slug)
            if p:
                f.write(f"- [`{p['relpath']}`]({p['relpath']}) — {why}\n")
        f.write("\n")

        f.write("## Sections\n\n")
        f.write("| Folder | When to read | Pages |\n")
        f.write("| ------ | ------------ | ----: |\n")
        for section in ordered:
            guide = SECTION_GUIDE.get(section, "")
            f.write(f"| `{section}/` | {guide} | {len(by_section[section])} |\n")
        f.write("\n")

        f.write(
            "> Note: these files are a point-in-time copy and may lag the live docs. "
            "When a detail is critical, confirm against the linked original.\n"
        )
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Mirror the complete Claude Code documentation, organized by section",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This tool reads the official docs index (llms.txt) and downloads every page it
lists from https://code.claude.com/docs/en/ as raw markdown, sorting each page
into a section folder that mirrors the docs sidebar.

Examples:
  # Mirror all docs into a 'claude-code' folder in the current directory
  ./update_official_claude_docs.py
  # Write to a specific directory instead
  ./update_official_claude_docs.py -d 'docs/claude_code docs'
  # Only pages whose slug contains a substring (e.g. just the SDK pages)
  ./update_official_claude_docs.py --filter agent-sdk
  # Sequential processing (slower but gentler)
  ./update_official_claude_docs.py --sequential

No API key is required.
        """,
    )

    parser.add_argument(
        "-d", "--directory", type=Path,
        default=Path.cwd() / "claude-code",
        help="Output directory (default: a 'claude-code' folder in the current working directory)",
    )
    parser.add_argument(
        "--filter", dest="filter_substr", default=None,
        help="Only fetch pages whose slug contains this substring",
    )
    parser.add_argument(
        "--sequential", action="store_true",
        help="Fetch pages sequentially instead of in parallel",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--max-workers", type=int, default=4,
        help="Maximum parallel workers (default: 4)",
    )

    args = parser.parse_args()

    # Create session for connection pooling
    session = requests.Session()

    # Discover every page from the index
    console.print(f"[cyan]Reading index:[/cyan] {DOCS_INDEX}")
    try:
        pages = discover_pages(session, args.filter_substr)
    except Exception as e:
        console.print(f"[red]Failed to read index: {e}[/red]")
        sys.exit(1)

    if not pages:
        console.print("[red]No pages found in the index (check --filter).[/red]")
        sys.exit(1)

    # Warn about pages that fell through to the misc bucket
    uncategorized = [p["slug"] for p in pages if p["section"] == MISC_SECTION]
    if uncategorized:
        console.print(
            f"[yellow]Note: {len(uncategorized)} page(s) not in the section map "
            f"(placed in '{MISC_SECTION}/'):[/yellow] " + ", ".join(sorted(uncategorized))
        )

    console.print(f"[cyan]Fetching {len(pages)} documentation pages...[/cyan]")
    console.print(f"Output directory: [green]{args.directory}[/green]")
    console.print()

    results = []

    if args.sequential:
        # Sequential processing
        with Progress(
            TextColumn("[bold blue]{task.fields[current]}/{task.fields[total]}", justify="right"),
            TextColumn("{task.fields[filename]}"),
            BarColumn(),
            TextColumn("{task.fields[status]}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching", total=len(pages), current=0, filename="", status="")
            for i, p in enumerate(pages, 1):
                output_path = args.directory / p["relpath"]
                progress.update(task, current=i, total=len(pages), filename=p["relpath"], status="downloading...")
                path, success, info = fetch_page(session, p["url"], output_path, args.delay)
                results.append((path, success, info))
                status = f"[green]✓[/green] {info}" if success else f"[red]✗[/red] {info}"
                progress.update(task, status=status)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(fetch_page, session, p["url"], args.directory / p["relpath"], args.delay): p
                for p in pages
            }

            for i, future in enumerate(as_completed(futures), 1):
                p = futures[future]
                path, success, info = future.result()
                results.append((path, success, info))
                console.print(f"[{i}/{len(pages)}] {p['relpath']}: {'[green]✓[/green]' if success else '[red]✗[/red]'} {info}")

    # Summary
    successful = sum(1 for _, success, _ in results if success)
    failed = len(results) - successful

    console.print()

    # Display summary table
    table = Table(title="Download Summary")
    table.add_column("Status", justify="center")
    table.add_column("Count", justify="right")
    table.add_row("[green]Successful[/green]", str(successful))
    table.add_row("[red]Failed[/red]", str(failed))
    console.print(table)

    if failed > 0:
        console.print("\n[red]Failed pages:[/red]")
        for path, success, info in results:
            if not success:
                console.print(f"  - {path}: {info}")
        sys.exit(1)

    index_path = write_index(args.directory, pages)
    console.print(f"\n[green]Created index at {index_path}[/green]")

    claude_md_path = write_claude_md(args.directory, pages)
    console.print(f"[green]Created navigation guide at {claude_md_path}[/green]")


if __name__ == "__main__":
    main()
