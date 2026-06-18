#!/usr/bin/env python3
"""Unit tests for plan_html: render_plan_markdown, render_plan_html, write_plan_html.

The escaping boundary is the critical correctness surface (DL-210):
  - plan body VALUES pass through ``_esc`` (HTML-escapes & < >) so a field
    containing ``<script>`` compiles to visible text, not live markup;
  - Mermaid source goes verbatim inside a ```mermaid fence — marked escapes the
    code content during compile and the boot script reads textContent (decoded),
    so arrow syntax (-->, ->>) round-trips intact.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).parent.parent
_SCRIPTS = _WORKTREE / "skills" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from skills.lib.workflow.constants import PLAN_HTML_FILE
from skills.lib.workflow.persistence.plan_html import (
    render_plan_html,
    render_plan_markdown,
    write_plan_html,
)


# ---------------------------------------------------------------------------
# Fixture plan
# ---------------------------------------------------------------------------

DIAGRAM_SRC = "flowchart TD\n  A-->B"


def _minimal_plan(**overrides) -> dict:
    base = {
        "overview": {"title": "Test Plan", "problem": "P", "approach": "A"},
        "planning_context": {
            "decisions": [{"id": "DL-001", "decision": "Use X", "reasoning": "Y -> Z"}],
            "rejected_alternatives": [{"alternative": "Use Q", "reason": "slow"}],
            "constraints": ["Must be fast"],
            "risks": [{"risk": "CDN down", "mitigation": "raw source readable"}],
        },
        "invisible_knowledge": {"system": "IK body", "invariants": ["inv1"], "tradeoffs": ["t1"]},
        "milestones": [
            {
                "id": "M-001",
                "name": "First milestone",
                "files": ["src/foo.py"],
                "requirements": ["do the thing"],
                "acceptance_criteria": ["Passes tests"],
                "code_intents": [
                    {"id": "CI-1", "file": "src/foo.py", "function": "bar", "behavior": "Does bar"}
                ],
            }
        ],
        "waves": [{"id": "W-001", "wave": 1, "milestones": ["M-001"], "rationale": "First"}],
        "diagrams": [{"id": "CON", "title": "Architecture", "mermaid": DIAGRAM_SRC}],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# render_plan_markdown
# ---------------------------------------------------------------------------


class TestRenderPlanMarkdown:
    def test_has_mermaid_fence_per_diagram(self):
        md = render_plan_markdown(_minimal_plan())
        assert md.count("```mermaid") == 1

    def test_two_diagrams_two_fences(self):
        md = render_plan_markdown(_minimal_plan(diagrams=[
            {"id": "CON", "title": "Arch", "mermaid": "flowchart TD\n  A-->B"},
            {"id": "SEQ", "title": "Seq", "mermaid": "sequenceDiagram\n  A->>B: hi"},
        ]))
        assert md.count("```mermaid") == 2

    def test_mermaid_source_verbatim(self):
        md = render_plan_markdown(_minimal_plan())
        # Arrow syntax is NOT escaped in the markdown (marked escapes at compile).
        assert "flowchart TD" in md
        assert "A-->B" in md

    def test_value_html_escaped(self):
        md = render_plan_markdown(_minimal_plan(
            overview={"title": "T", "problem": "<script>alert(1)</script>", "approach": "A"}
        ))
        assert "<script>alert(1)</script>" not in md
        assert "&lt;script&gt;" in md

    def test_table_pipe_escaped_in_cell(self):
        md = render_plan_markdown(_minimal_plan(
            planning_context={"decisions": [
                {"id": "DL-1", "decision": "a | b", "reasoning": "r"}], "constraints": []}
        ))
        assert "a \\| b" in md

    def test_empty_diagrams_no_fence(self):
        md = render_plan_markdown(_minimal_plan(diagrams=[]))
        assert "```mermaid" not in md

    def test_sections_present(self):
        md = render_plan_markdown(_minimal_plan())
        for token in ("# Test Plan", "## Overview", "## Milestones", "First milestone", "DL-001"):
            assert token in md


# ---------------------------------------------------------------------------
# render_plan_html
# ---------------------------------------------------------------------------


class TestRenderPlanHtml:
    def test_starts_with_doctype(self):
        assert render_plan_html(_minimal_plan()).startswith("<!DOCTYPE html>")

    def test_marked_cdn_present(self):
        assert "marked@16" in render_plan_html(_minimal_plan())

    def test_mermaid_11_cdn_present(self):
        assert "mermaid@11" in render_plan_html(_minimal_plan())

    def test_security_level_strict(self):
        assert "securityLevel: 'strict'" in render_plan_html(_minimal_plan())

    def test_start_on_load_false(self):
        assert "startOnLoad: false" in render_plan_html(_minimal_plan())

    def test_base64_payload_roundtrips_to_markdown(self):
        import base64, re
        html = render_plan_html(_minimal_plan())
        m = re.search(r'<script id="plan-md"[^>]*>([^<]+)</script>', html)
        assert m is not None
        decoded = base64.b64decode(m.group(1)).decode("utf-8")
        assert decoded == render_plan_markdown(_minimal_plan())

    def test_script_injection_not_live_in_payload(self):
        # The <script> in a plan field is escaped inside the markdown, so once
        # base64-decoded+compiled it cannot execute.
        import base64, re
        html = render_plan_html(_minimal_plan(
            overview={"title": "T", "problem": "<script>alert(1)</script>", "approach": "A"}
        ))
        decoded = base64.b64decode(
            re.search(r'<script id="plan-md"[^>]*>([^<]+)</script>', html).group(1)
        ).decode("utf-8")
        assert "<script>alert(1)</script>" not in decoded
        assert "&lt;script&gt;" in decoded

    def test_empty_plan_renders_valid_html(self):
        html = render_plan_html({})
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html


# ---------------------------------------------------------------------------
# write_plan_html
# ---------------------------------------------------------------------------


class TestWritePlanHtml:
    def test_creates_plan_html(self, tmp_path):
        write_plan_html(tmp_path, _minimal_plan())
        dest = tmp_path / PLAN_HTML_FILE
        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "marked@16" in content

    def test_no_tmp_files_after_success(self, tmp_path):
        write_plan_html(tmp_path, _minimal_plan())
        assert list(tmp_path.glob(".tmp-plan-html-*")) == []

    def test_rename_failure_leaves_no_tmp_and_does_not_raise(self, tmp_path, monkeypatch):
        def bad_rename(src, dst):
            raise OSError("disk full")

        # Patch os.rename directly so write_plan_html's finally-block cleanup runs.
        monkeypatch.setattr(os, "rename", bad_rename)
        write_plan_html(tmp_path, _minimal_plan())  # must not raise
        assert not (tmp_path / PLAN_HTML_FILE).exists()
        assert list(tmp_path.glob(".tmp-plan-html-*")) == []

    def test_idempotent_overwrite(self, tmp_path):
        write_plan_html(tmp_path, _minimal_plan())
        write_plan_html(tmp_path, _minimal_plan())
        assert (tmp_path / PLAN_HTML_FILE).exists()

    def test_accepts_str_run_dir(self, tmp_path):
        # run_dir.path is a Path, but the writer must tolerate a str too.
        write_plan_html(str(tmp_path), _minimal_plan())
        assert (tmp_path / PLAN_HTML_FILE).exists()
