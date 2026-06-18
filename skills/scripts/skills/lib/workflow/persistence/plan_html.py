#!/usr/bin/env python3
"""Render a plan dict into a self-contained HTML document compiled by marked.

The planner ``workflow.mjs`` returns a ``result.plan`` object that includes a
``diagrams`` list of ``{id, title, mermaid}`` entries.  This module turns that
dict into a single ``.html`` file openable directly in a browser, mirroring
koan's ``<Md>`` render path (markdown body + inline Mermaid) rather than
hand-building HTML.

Pipeline (DL-204):
  1. ``render_plan_markdown(plan)`` — serialize the plan dict into a Markdown
     document following ``skills/planner/resources/plan-format.md``.  Diagrams
     become fenced ```mermaid blocks.
  2. ``render_plan_html(plan)`` — wrap that Markdown in an HTML shell that loads
     ``marked@16`` + ``mermaid@11`` from a CDN and compiles the body in the
     browser.

Safety (DL-205, DL-210):
  - The Markdown *skeleton* (headings, tables) is authored here and trusted; all
    interpolated plan *values* pass through ``_esc`` / ``_cell`` so plan content
    cannot inject raw HTML once marked compiles it (marked does not sanitize).
  - The Markdown payload is embedded base64-encoded and ``atob``-decoded in JS,
    which removes every ``</script>`` / backtick escaping hazard.
  - Mermaid is initialized with ``securityLevel:'strict'`` to sandbox the
    LLM-generated diagram SVG, and each block renders inside a try/catch so one
    invalid diagram shows its raw source plus an inline error note without
    blanking the page.

Offline degradation: when the CDN scripts do not load, the ``#content`` div stays
empty (no try/catch wraps the boot script), but the base64 Markdown payload is
preserved in the page source and recoverable via View Source.

``render_plan_markdown`` / ``render_plan_html`` are pure (no I/O).
``write_plan_html`` is the atomic, non-fatal writer.

Design refs: DL-203, DL-204, DL-205, DL-208, DL-210.
"""
from __future__ import annotations

import base64
import html
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from ..constants import PLAN_HTML_FILE

log = logging.getLogger(__name__)

# CDN pins (DL-205): marked compiles the body, mermaid renders the fences.
MARKED_CDN = "https://cdn.jsdelivr.net/npm/marked@16/marked.min.js"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"


# ---------------------------------------------------------------------------
# Escape helpers (DL-210)
# ---------------------------------------------------------------------------


def _esc(text: Any) -> str:
    """HTML-escape a plan value (& < >) so it renders as text, not markup.

    marked passes raw HTML through verbatim; escaping the angle brackets here
    means a plan field containing ``<script>`` compiles to visible text.
    """
    return html.escape(str(text), quote=False)


def _cell(text: Any) -> str:
    """Escape a value for a Markdown TABLE cell.

    Adds pipe-escaping and newline-flattening on top of ``_esc`` so a multi-line
    or pipe-bearing value cannot break the surrounding table row.
    """
    return _esc(text).replace("|", "\\|").replace("\n", "<br>")


# ---------------------------------------------------------------------------
# Markdown section builders (pure)
# ---------------------------------------------------------------------------


def _overview_md(plan: dict) -> list[str]:
    ov = plan.get("overview") or {}
    out: list[str] = []
    problem = ov.get("problem") or ""
    approach = ov.get("approach") or ""
    if problem:
        out += ["## Overview", "", f"**Problem:** {_esc(problem)}", ""]
    if approach:
        out += [f"**Approach:** {_esc(approach)}", ""]
    return out


def _planning_context_md(plan: dict) -> list[str]:
    pc = plan.get("planning_context") or {}
    out: list[str] = []

    decisions = pc.get("decisions") or pc.get("decision_log") or []
    if decisions:
        out += ["## Planning Context", "", "### Decision Log", "",
                "| ID | Decision | Reasoning |", "| --- | --- | --- |"]
        for d in decisions:
            out.append(
                f"| {_cell(d.get('id', ''))} | {_cell(d.get('decision', ''))} "
                f"| {_cell(d.get('reasoning') or d.get('reasoning_chain', ''))} |"
            )
        out.append("")

    rejected = pc.get("rejected_alternatives") or []
    if rejected:
        out += ["### Rejected Alternatives", "",
                "| Alternative | Why Rejected |", "| --- | --- |"]
        for r in rejected:
            out.append(
                f"| {_cell(r.get('alternative', ''))} "
                f"| {_cell(r.get('reason') or r.get('rejection_reason', ''))} |"
            )
        out.append("")

    constraints = pc.get("constraints") or []
    if constraints:
        out += ["### Constraints", ""]
        for c in constraints:
            val = c if isinstance(c, str) else c.get("description", str(c))
            out.append(f"- {_esc(val)}")
        out.append("")

    risks = pc.get("risks") or pc.get("known_risks") or []
    if risks:
        out += ["### Known Risks", "",
                "| Risk | Mitigation |", "| --- | --- |"]
        for r in risks:
            out.append(
                f"| {_cell(r.get('risk', ''))} | {_cell(r.get('mitigation', ''))} |"
            )
        out.append("")

    return out


def _invisible_knowledge_md(plan: dict) -> list[str]:
    ik = plan.get("invisible_knowledge") or {}
    out: list[str] = []
    system = ik.get("system") or ""
    if system:
        out += ["## Invisible Knowledge", "", _esc(system), ""]
    for label, key in (("Invariants", "invariants"), ("Tradeoffs", "tradeoffs")):
        items = ik.get(key) or []
        if items:
            out += [f"### {label}", ""]
            out += [f"- {_esc(i)}" for i in items]
            out.append("")
    return out


def _milestones_md(plan: dict) -> list[str]:
    milestones = plan.get("milestones") or []
    if not milestones:
        return []
    out: list[str] = ["## Milestones", ""]
    for m in milestones:
        out += [f"### {_esc(m.get('id', ''))}: {_esc(m.get('name', ''))}", ""]
        files = m.get("files") or []
        if files:
            out.append("**Files:**")
            out += [f"- `{_esc(f)}`" for f in files]
            out.append("")
        for label, key in (("Requirements", "requirements"),
                           ("Acceptance Criteria", "acceptance_criteria")):
            items = m.get(key) or []
            if items:
                out.append(f"**{label}:**")
                out += [f"- {_esc(i)}" for i in items]
                out.append("")
        ci_list = m.get("code_intents") or []
        if ci_list:
            out += ["**Code Intents:**", "",
                    "| ID | File | Function | Behavior |", "| --- | --- | --- | --- |"]
            for ci in ci_list:
                out.append(
                    f"| {_cell(ci.get('id', ''))} | `{_cell(ci.get('file', ''))}` "
                    f"| {_cell(ci.get('function') or '')} | {_cell(ci.get('behavior', ''))} |"
                )
            out.append("")
    return out


def _waves_md(plan: dict) -> list[str]:
    waves = plan.get("waves") or []
    if not waves:
        return []
    out: list[str] = ["## Waves", ""]
    for w in waves:
        ms = ", ".join(_esc(m) for m in (w.get("milestones") or []))
        out.append(
            f"- **{_esc(w.get('id', ''))} (Wave {_esc(w.get('wave', ''))}):** "
            f"{ms} — _{_esc(w.get('rationale') or '')}_"
        )
    out.append("")
    return out


def _diagrams_md(plan: dict) -> list[str]:
    diagrams = plan.get("diagrams") or []
    if not diagrams:
        return []
    out: list[str] = ["## Diagrams", ""]
    for d in diagrams:
        title = d.get("title") or d.get("id") or "Diagram"
        out += [f"### {_esc(title)}", ""]
        # Mermaid source goes verbatim into the fence. marked HTML-escapes code
        # content during compile; the boot script reads textContent (decoded),
        # so arrow syntax (-->, ->>) round-trips intact to Mermaid.
        out += ["```mermaid", str(d.get("mermaid") or ""), "```", ""]
    return out


# ---------------------------------------------------------------------------
# Public render functions (pure, no I/O)
# ---------------------------------------------------------------------------


def render_plan_markdown(plan: dict) -> str:
    """Serialize a plan dict into a Markdown document.

    Diagrams are emitted as fenced ```mermaid blocks; every interpolated plan
    value is escaped so plan content cannot inject markup once marked compiles
    the document.
    """
    title = (plan.get("overview") or {}).get("title") or "Plan"
    lines: list[str] = [f"# {_esc(title)}", ""]
    for builder in (
        _overview_md,
        _planning_context_md,
        _invisible_knowledge_md,
        _milestones_md,
        _waves_md,
        _diagrams_md,
    ):
        lines += builder(plan)
    return "\n".join(lines).rstrip() + "\n"


def render_plan_html(plan: dict) -> str:
    """Render a plan dict into a self-contained HTML string.

    The returned string starts with ``<!DOCTYPE html>`` and embeds the plan's
    Markdown (base64-encoded) for client-side compilation by ``marked@16``.
    Fenced ```mermaid blocks are rendered by ``mermaid@11`` initialized with
    ``startOnLoad:false`` + ``securityLevel:'strict'``.
    """
    title = _esc((plan.get("overview") or {}).get("title") or "Plan")
    markdown = render_plan_markdown(plan)
    payload = base64.b64encode(markdown.encode("utf-8")).decode("ascii")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
  h1, h2 {{ border-bottom: 1px solid #ddd; padding-bottom: .25rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
  th, td {{ border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; vertical-align: top; }}
  th {{ background: #f5f5f5; }}
  code {{ background: #f0f0f0; padding: .1em .3em; border-radius: 3px; }}
  pre.mermaid {{ background: #fafafa; padding: 1rem; border-radius: 4px; overflow-x: auto; }}
  .mermaid-error {{ color: #c00; font-size: .85em; margin-top: .5rem; }}
</style>
</head>
<body>
<div id="content"></div>
<script id="plan-md" type="application/octet-stream">{payload}</script>
<script src="{MARKED_CDN}"></script>
<script src="{MERMAID_CDN}"></script>
<script>
  mermaid.initialize({{ startOnLoad: false, securityLevel: 'strict' }});
  document.addEventListener('DOMContentLoaded', function () {{
    // Decode the base64 Markdown payload as UTF-8.
    var b64 = document.getElementById('plan-md').textContent;
    var bytes = Uint8Array.from(atob(b64), function (c) {{ return c.charCodeAt(0); }});
    var md = new TextDecoder('utf-8').decode(bytes);
    document.getElementById('content').innerHTML = marked.parse(md);
    // marked compiles ```mermaid fences to <code class="language-mermaid">;
    // convert each to a <pre class="mermaid"> block for mermaid to render.
    document.querySelectorAll('code.language-mermaid').forEach(function (code) {{
      var pre = document.createElement('pre');
      pre.className = 'mermaid';
      pre.textContent = code.textContent;
      var host = code.closest('pre') || code;
      host.replaceWith(pre);
    }});
    // Render each block in isolation so one bad diagram never blanks the page.
    document.querySelectorAll('pre.mermaid').forEach(function (el) {{
      var src = el.textContent;
      mermaid.render('m-' + Math.random().toString(36).slice(2), src).then(function (res) {{
        el.innerHTML = res.svg;
      }}).catch(function (err) {{
        var note = document.createElement('div');
        note.className = 'mermaid-error';
        note.textContent = 'Diagram render error: ' + String(err);
        el.parentNode.insertBefore(note, el.nextSibling);
        el.textContent = src;
      }});
    }});
  }});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Atomic writer (DL-202, DL-208)
# ---------------------------------------------------------------------------


def write_plan_html(run_dir: Path, plan: dict) -> None:
    """Write ``plan.html`` atomically to *run_dir*.

    Mirrors the tmp-file + fsync + ``os.rename`` pattern of ``atomic.py`` (omits
    the parent-dir fsync — acceptable under the DL-208 best-effort contract for a
    derived, regenerable view). Non-fatal: any exception is logged at WARNING and
    swallowed so the caller (``bridge_workflow_run``) continues bridging phase
    events regardless.
    """
    tmp_path: str | None = None
    try:
        html_bytes = render_plan_html(plan).encode("utf-8")
        fd, tmp_path = tempfile.mkstemp(dir=run_dir, prefix=".tmp-plan-html-")
        try:
            os.write(fd, html_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(tmp_path, Path(run_dir) / PLAN_HTML_FILE)
        tmp_path = None  # Renamed successfully; nothing to clean up.
    except Exception as exc:
        log.warning("plan_html: failed to write plan.html: %s", exc)
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                # Temp file may already be gone (e.g. dir removed); safe to ignore.
                pass
