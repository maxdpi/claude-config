#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "requests>=2.31.0",
#   "rich>=13.0.0",
# ]
# ///
"""
Fetch complete Claude Code documentation from Anthropic docs site
"""

import os
import sys
import time
import json
import argparse
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

console = Console()

# Claude Code documentation structure
CLAUDE_DOCS_URLS = {
    "getting-started": [
        ("overview", "https://docs.anthropic.com/en/docs/claude-code/overview"),
        ("quickstart", "https://docs.anthropic.com/en/docs/claude-code/quickstart"),
        ("common-workflows", "https://docs.anthropic.com/en/docs/claude-code/common-workflows"),
    ],
    "build": [
        ("sub-agents", "https://docs.anthropic.com/en/docs/claude-code/sub-agents"),
        ("output-styles", "https://docs.anthropic.com/en/docs/claude-code/output-styles"),
        ("hooks-guide", "https://docs.anthropic.com/en/docs/claude-code/hooks-guide"),
        ("github-actions", "https://docs.anthropic.com/en/docs/claude-code/github-actions"),
        ("mcp", "https://docs.anthropic.com/en/docs/claude-code/mcp"),
        ("troubleshooting", "https://docs.anthropic.com/en/docs/claude-code/troubleshooting"),
    ],
    "sdk": [
        ("sdk-overview", "https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-overview"),
        ("sdk-headless", "https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-headless"),
        ("sdk-python", "https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-python"),
        ("sdk-typescript", "https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-typescript"),
    ],
    "deployment": [
        ("overview", "https://docs.anthropic.com/en/docs/claude-code/third-party-integrations"),  # This is the deployment overview
        ("amazon-bedrock", "https://docs.anthropic.com/en/docs/claude-code/amazon-bedrock"),
        ("google-vertex-ai", "https://docs.anthropic.com/en/docs/claude-code/google-vertex-ai"),
        ("corporate-proxy", "https://docs.anthropic.com/en/docs/claude-code/corporate-proxy"),
        ("llm-gateway", "https://docs.anthropic.com/en/docs/claude-code/llm-gateway"),
        ("devcontainer", "https://docs.anthropic.com/en/docs/claude-code/devcontainer"),
    ],
    "administration": [
        ("setup", "https://docs.anthropic.com/en/docs/claude-code/setup"),
        ("iam", "https://docs.anthropic.com/en/docs/claude-code/iam"),
        ("security", "https://docs.anthropic.com/en/docs/claude-code/security"),
        ("data-usage", "https://docs.anthropic.com/en/docs/claude-code/data-usage"),
        ("monitoring-usage", "https://docs.anthropic.com/en/docs/claude-code/monitoring-usage"),
        ("costs", "https://docs.anthropic.com/en/docs/claude-code/costs"),
        ("analytics", "https://docs.anthropic.com/en/docs/claude-code/analytics"),
        ("output-styles-admin", "https://docs.anthropic.com/en/docs/claude-code/output-styles-admin"),
    ],
    "configuration": [
        ("settings", "https://docs.anthropic.com/en/docs/claude-code/settings"),
        ("ide-integrations", "https://docs.anthropic.com/en/docs/claude-code/ide-integrations"),
        ("terminal-config", "https://docs.anthropic.com/en/docs/claude-code/terminal-config"),
        ("model-config", "https://docs.anthropic.com/en/docs/claude-code/model-config"),
        ("memory", "https://docs.anthropic.com/en/docs/claude-code/memory"),
        ("statusline", "https://docs.anthropic.com/en/docs/claude-code/statusline"),
    ],
    "reference": [
        ("cli-reference", "https://docs.anthropic.com/en/docs/claude-code/cli-reference"),
        ("interactive-mode", "https://docs.anthropic.com/en/docs/claude-code/interactive-mode"),
        ("slash-commands", "https://docs.anthropic.com/en/docs/claude-code/slash-commands"),
        ("hooks", "https://docs.anthropic.com/en/docs/claude-code/hooks"),
    ],
}

def fetch_page(session, url, output_path, jina_key, rate_limit_delay=1.0):
    """Fetch a single documentation page"""
    headers = {
        "Authorization": f"Bearer {jina_key}",
        "DNT": "1",
        "X-Engine": "browser"
    }

    jina_url = f"https://r.jina.ai/{url}"

    try:
        response = session.get(jina_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Create directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response.text)

        # Rate limiting
        time.sleep(rate_limit_delay)

        return (str(output_path), True, f"{len(response.text):,} chars")

    except Exception as e:
        return (str(output_path), False, str(e))

def main():
    parser = argparse.ArgumentParser(
        description="Fetch complete Claude Code documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This tool fetches all Claude Code documentation pages from Anthropic's docs site.
Examples:
  # Fetch all docs with default settings
  ./tools/fetch_claude_docs.py
  # Fetch only specific sections
  ./tools/fetch_claude_docs.py --sections getting-started build
  # Use custom output directory
  ./tools/fetch_claude_docs.py -d context/references/claude_docs
  # Sequential processing (slower but gentler)
  ./tools/fetch_claude_docs.py --sequential
Environment:
  JINA_API_KEY - Required. Set this to your Jina.ai API key
        """
    )

    parser.add_argument('-d', '--directory', type=Path,
                       default=Path('context/third_party_docs/claude_code'),
                       help='Output directory (default: context/third_party_docs/claude_code)')
    parser.add_argument('--sections', nargs='+',
                       choices=list(CLAUDE_DOCS_URLS.keys()),
                       help='Specific sections to fetch (default: all)')
    parser.add_argument('--sequential', action='store_true',
                       help='Fetch pages sequentially instead of in parallel')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--max-workers', type=int, default=3,
                       help='Maximum parallel workers (default: 3)')

    args = parser.parse_args()

    # Get API key
    jina_key = os.environ.get('JINA_API_KEY')
    if not jina_key:
        print("Error: JINA_API_KEY environment variable not set", file=sys.stderr)
        print("Get your API key from https://jina.ai", file=sys.stderr)
        sys.exit(1)

    # Determine which sections to fetch
    sections_to_fetch = args.sections or list(CLAUDE_DOCS_URLS.keys())

    # Build list of all pages to fetch
    pages_to_fetch = []
    for section in sections_to_fetch:
        for filename, url in CLAUDE_DOCS_URLS[section]:
            output_path = args.directory / section / f"{filename}.md"
            pages_to_fetch.append((url, output_path))

    console.print(f"[cyan]Fetching {len(pages_to_fetch)} documentation pages...[/cyan]")
    console.print(f"Output directory: [green]{args.directory}[/green]")
    console.print()

    # Create session for connection pooling
    session = requests.Session()

    results = []

    if args.sequential:
        # Sequential processing
        with Progress(
            TextColumn("[bold blue]{task.fields[current]}/{task.fields[total]}", justify="right"),
            TextColumn("{task.fields[filename]}"),
            BarColumn(),
            TextColumn("{task.fields[status]}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching", total=len(pages_to_fetch), current=0, filename="", status="")
            for i, (url, output_path) in enumerate(pages_to_fetch, 1):
                progress.update(task, current=i, total=len(pages_to_fetch), filename=output_path.name, status="downloading...")
                path, success, info = fetch_page(session, url, output_path, jina_key, args.delay)
                results.append((path, success, info))
                status = f"[green]✓[/green] {info}" if success else f"[red]✗[/red] {info}"
                progress.update(task, status=status)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(fetch_page, session, url, output_path, jina_key, args.delay): (url, output_path)
                for url, output_path in pages_to_fetch
            }

            for i, future in enumerate(as_completed(futures), 1):
                url, output_path = futures[future]
                path, success, info = future.result()
                results.append((path, success, info))
                console.print(f"[{i}/{len(pages_to_fetch)}] {output_path.name}: {'[green]✓[/green]' if success else '[red]✗[/red]'} {info}")

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

    # Create an index file
    index_path = args.directory / "README.md"
    with open(index_path, 'w') as f:
        f.write("# Claude Code Documentation\n\n")
        f.write("This directory contains a complete snapshot of Claude Code documentation.\n\n")
        f.write(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        for section in sections_to_fetch:
            f.write(f"\n## {section.replace('-', ' ').title()}\n\n")
            for filename, url in CLAUDE_DOCS_URLS[section]:
                f.write(f"- [{filename.replace('-', ' ').title()}]({section}/{filename}.md) - [Original]({url})\n")

    console.print(f"\n[green]Created index at {index_path}[/green]")

if __name__ == "__main__":
    main()
