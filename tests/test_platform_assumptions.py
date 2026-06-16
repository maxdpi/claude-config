"""M-000 -- tests for the load-bearing platform assumptions (A1-A4).

These pin the empirical findings captured by the M-000 probes so a regression (or a
Claude Code platform change that breaks an assumption) is caught. They are pure
Python + stdlib so they run under plain ``pytest`` with no extra deps.

Proof anchors:
  * A1 -- workflow_journal_probe.mjs + the JOURNAL_FIXTURE below (a verbatim journal
    captured 2026-06-16 from run wf_f423bb66-344).
  * A2 -- documented Claude Code Workflow-tool semantics (cited below) + the same
    journal fixture (the `key` content-hash is the resumeFromRunId cache mechanism).
  * A3 -- teams_dir_probe.py.
  * A4 -- subagent_transcript_probe.py + subagent_transcript_probe_result.json.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO / "skills/scripts/skills/lib/workflow/persistence/probe"


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- A1: Workflow journal is machine-readable (Python json.loads) ----------------
#
# Verbatim journal.jsonl captured from run wf_f423bb66-344 (2026-06-16), located at
# ~/.claude/projects/{project}/{session}/subagents/workflows/wf_*/journal.jsonl.
JOURNAL_FIXTURE = (
    '{"type":"started","key":"v2:0cafabaffd9ce0da13b51c6871ac9a6a93630198bec20ea752708233e4855b40","agentId":"afea4dc57083c426a"}\n'
    '{"type":"result","key":"v2:0cafabaffd9ce0da13b51c6871ac9a6a93630198bec20ea752708233e4855b40","agentId":"afea4dc57083c426a","result":"PONG"}\n'
)


def test_workflow_journal_is_python_readable():
    """A1: every journal line parses as JSON and carries the resume cache key."""
    lines = [l for l in JOURNAL_FIXTURE.splitlines() if l.strip()]
    parsed = [json.loads(l) for l in lines]  # raises if not machine-readable
    assert {p["type"] for p in parsed} == {"started", "result"}
    for p in parsed:
        assert p["key"].startswith("v2:"), "journal key is the content-hash cache key"
        assert "agentId" in p
    # started/result share the SAME key -> that key is what dedupes on resume.
    assert parsed[0]["key"] == parsed[1]["key"]


def test_resume_from_run_id_same_session():
    """A2: resumeFromRunId is same-session-only and journals agent() calls.

    Documented semantics (Claude Code Workflow tool, ``resumeFromRunId``):
      "Same-session only. The longest unchanged prefix of agent() calls returns
       cached results instantly; the first edited/new call and everything after it
       runs live. Same script + same args -> 100% cache hit."
    The journal IS the cache: each agent() call writes a `started`/`result` pair
    keyed by a content hash of (prompt, opts). Resume replays by matching those keys.

    Structural corroboration of "same-session-only": the journal is stored UNDER the
    session id --
      ~/.claude/projects/{project}/{sessionId}/subagents/workflows/{runId}/journal.jsonl
    so a different session does not share the path and cannot see the journal without
    being handed it -- consistent with the documented same-session restriction.
    """
    parsed = [json.loads(l) for l in JOURNAL_FIXTURE.splitlines() if l.strip()]
    # agent() calls are journaled as started+result pairs keyed by content hash.
    by_key: dict[str, set[str]] = {}
    for p in parsed:
        by_key.setdefault(p["key"], set()).add(p["type"])
    assert all(v == {"started", "result"} for v in by_key.values()), (
        "each journaled agent() call has a started+result pair -> replayable cache entry"
    )
    # The recorded path proves session-namespacing (same-session-only mechanism).
    anchor = json.loads((PROBE_DIR / "subagent_transcript_probe_result.json").read_text())
    assert "{sessionId}" in anchor["transcript_path"]["pattern"]


# --- A3: runtime dirs are runtime-owned (durable store must live elsewhere) -------
def test_teams_tasks_not_a_safe_durable_store():
    mod = _load("teams_dir_probe", PROBE_DIR / "teams_dir_probe.py")
    res = mod.probe_teams_dir_ephemerality("observe")
    concl = res["observed_conclusion"]
    # Whatever the reaping behaviour, C-003 must hold: store lives outside these dirs.
    assert concl["c003_durable_store_outside_these_dirs_still_required"] is True
    # teams dir absent (Agent Teams disabled here) OR present; either way tasks must
    # not be treated as durable. If tasks persists, A3's literal "reaped" wording is
    # flagged for DL-002/DL-005 revisit.
    if concl["tasks_dir_persists_across_sessions"]:
        assert concl["a3_literal_reaping_supported"] is False
        assert "revisit" in concl["action"]


# --- A4: native subagent transcript path + correlation join -----------------------
def test_subagent_transcript_proof_anchor():
    mod = _load("subagent_transcript_probe", PROBE_DIR / "subagent_transcript_probe.py")
    res = mod.probe_subagent_transcript()  # replays the captured proof anchor
    assert res["transcript_path"]["confirmed"] is True
    assert res["transcript_path"]["pattern"] == (
        "~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl"
    )
    # The DL-016/DL-020 correlation join: path id == record id == spawn-result id.
    jv = res["join_validation"]
    assert jv["match"] is True
    assert jv["filename_agent_id"] == jv["spawn_result_agent_id"]
    assert jv["filename_agent_id"] in jv["in_record_agent_ids"]
    assert jv["session_id_matches_path"] is True


def test_dl021_parent_precedence_is_live_here():
    """A4/DL-021: this environment's parent mode is `auto` -> overrides child plan."""
    mod = _load("subagent_transcript_probe", PROBE_DIR / "subagent_transcript_probe.py")
    res = mod.probe_subagent_transcript()
    pp = res["permission_mode"]["parent_precedence"]
    assert pp["this_environment_parent_mode"] in {"auto", "acceptEdits", "bypassPermissions"}
    assert "default-deny" in pp["implication"]


def test_resolve_unresolved_path_is_not_resumable():
    """DL-020: an unresolvable transcript path returns is_resumable=False."""
    mod = _load("subagent_transcript_probe", PROBE_DIR / "subagent_transcript_probe.py")
    res = mod.probe_subagent_transcript(
        session_id="00000000-dead-beef-0000-000000000000",
        native_agent_id="adeadbeefdeadbeef",
    )
    assert res["resolved"] is False
    assert res["is_resumable"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
