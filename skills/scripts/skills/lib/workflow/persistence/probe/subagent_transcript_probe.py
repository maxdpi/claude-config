#!/usr/bin/env python3
"""M-000 / CI-M-000-005 -- native subagent-transcript probe (assumption A4).

NATIVE-FIRST validation. The substrate must correlate a durable run to the native
subagent transcript that captures per-subagent history (DL-016), age-guard resume
off that transcript's mtime (DL-020), and map phase-trust onto permissionMode
(DL-017/DL-021). All of that rests on A4:

  A4: native subagent transcripts live at
      ~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl
      and the agentId in the path == the agentId carried in the transcript records
      == the agentId surfaced when the subagent is spawned.

SELF-BOOTSTRAP
--------------
A4 cannot be validated without a live subagent, so the orchestrator runs the
bootstrap, then this probe resolves and validates the transcript:

  1. ORCHESTRATOR spawns a minimal subagent (Agent tool) and captures its agentId
     from the spawn result.   (M-000 captured: ab73a631269d58310)
  2. THIS probe, given (session_id, native_agent_id), resolves the transcript path
     and confirms the path<->record agentId join, the format, and retention.

The captured M-000 evidence is persisted alongside this file in
``subagent_transcript_probe_result.json`` (the proof anchor referenced by
docs/PLATFORM-ASSUMPTIONS.md). Re-running ``--agent-id <id> --session <sid>``
re-validates against any live subagent.

KEY FINDINGS (2026-06-16, session 6bc18a41..., agent ab73a631269d58310)
  * Path pattern CONFIRMED exactly.
  * JOIN CONFIRMED: filename agentId == in-record agentId == spawn-result agentId.
  * Format: JSONL; every record carries agentId + sessionId (records: user /
    assistant / attachment; isSidechain=true).
  * cleanupPeriodDays: unset -> default 30 (medium confidence it governs subagent
    transcripts specifically).
  * SendMessage: available for subagent continuation even with Agent Teams disabled.
  * permissionMode: native values plan/default/acceptEdits/bypassPermissions/auto;
    a direct plan-mode spawn was NOT exercisable (permissionMode lives on subagent
    .md frontmatter, not on Agent/agent() opts) -> medium confidence. PARENT
    PRECEDENCE (DL-021) is LIVE here: settings.json sets defaultMode="auto", an
    overriding mode -> classify_phases must default-deny.
  * Native subagent resume is SESSION-SCOPED -> cross-session workflow-level resume
    still requires the substrate (DL-001).
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

CLAUDE = Path.home() / ".claude"
PROJECTS = CLAUDE / "projects"
RESULT_SIDECAR = Path(__file__).with_name("subagent_transcript_probe_result.json")

# DL-020: when the transcript path cannot be resolved, assume cleaned -> not resumable.
NOT_RESOLVED_IS_NOT_RESUMABLE = True


def _project_key_for_cwd(cwd: str) -> str:
    """Claude Code derives the project dir key by replacing path separators with '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd.rstrip("/"))


def resolve_transcript_path(session_id: str, native_agent_id: str, cwd: str | None = None):
    """Resolve ~/.claude/projects/{project}/{session}/subagents/agent-{id}.jsonl.

    Tries the cwd-derived project key first, then falls back to scanning every
    project dir for the {session}/subagents/agent-{id}.jsonl file.
    """
    candidates = []
    if cwd:
        candidates.append(PROJECTS / _project_key_for_cwd(cwd) / session_id)
    if PROJECTS.exists():
        for proj in PROJECTS.iterdir():
            candidates.append(proj / session_id)
    seen = set()
    for sess_dir in candidates:
        key = str(sess_dir)
        if key in seen:
            continue
        seen.add(key)
        f = sess_dir / "subagents" / f"agent-{native_agent_id}.jsonl"
        if f.exists():
            return f
    return None


def read_cleanup_period_days() -> dict:
    for name in ("settings.json", "settings.local.json"):
        p = CLAUDE / name
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if "cleanupPeriodDays" in data:
                return {"value": data["cleanupPeriodDays"], "source": name, "confidence": "high"}
    return {
        "value": 30,
        "source": "default (cleanupPeriodDays unset in settings.json/settings.local.json)",
        "confidence": "medium",
        "note": "Default presumed to govern subagent transcripts (they live under ~/.claude/projects); tag medium until cited.",
    }


def probe_subagent_transcript(
    session_id: str | None = None,
    native_agent_id: str | None = None,
    cwd: str | None = None,
) -> dict:
    """Validate assumption A4 for a (session_id, native_agent_id) pair.

    With no ids, returns the persisted M-000 proof-anchor result (the self-bootstrap
    capture) so the probe is reproducible without re-spawning a subagent.
    """
    if not (session_id and native_agent_id):
        if RESULT_SIDECAR.exists():
            anchor = json.loads(RESULT_SIDECAR.read_text(encoding="utf-8"))
            anchor["_mode"] = "replayed_proof_anchor"
            return anchor
        return {
            "probe": "subagent_transcript", "assumption": "A4",
            "error": "no (session_id, native_agent_id) given and no proof-anchor sidecar present",
        }

    transcript = resolve_transcript_path(session_id, native_agent_id, cwd)
    if transcript is None:
        return {
            "probe": "subagent_transcript", "assumption": "A4",
            "session_id": session_id, "native_agent_id": native_agent_id,
            "resolved": False,
            "is_resumable": False if NOT_RESOLVED_IS_NOT_RESUMABLE else None,
            "verdict": "PATH_NOT_RESOLVED",
            "dl020": "transcript path unresolved -> assume cleaned -> is_resumable()=False (no started_at proxy).",
        }

    record_agent_ids: set[str] = set()
    record_session_ids: set[str] = set()
    record_keys: list[str] | None = None
    record_types: dict[str, int] = {}
    for line in transcript.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record_keys is None:
            record_keys = list(d.keys())
        if "agentId" in d:
            record_agent_ids.add(d["agentId"])
        if "sessionId" in d:
            record_session_ids.add(d["sessionId"])
        t = d.get("type", "?")
        record_types[t] = record_types.get(t, 0) + 1

    stat = transcript.stat()
    join_ok = native_agent_id in record_agent_ids
    return {
        "probe": "subagent_transcript", "assumption": "A4",
        "session_id": session_id, "native_agent_id": native_agent_id,
        "resolved": True,
        "transcript_path": str(transcript).replace(str(Path.home()), "~"),
        "transcript_mtime_epoch": stat.st_mtime,
        "format": "JSONL",
        "record_keys": record_keys,
        "record_types": record_types,
        "in_record_agent_ids": sorted(record_agent_ids),
        "in_record_session_ids": sorted(record_session_ids),
        "join_match_path_vs_records": join_ok,  # DL-016/DL-020 correlation join
        "session_id_matches": session_id in record_session_ids,
        "cleanup_period_days": read_cleanup_period_days(),
        "age_guard_note": "DL-020: is_resumable() must judge age from THIS transcript's mtime, not run started_at.",
        "session_scoped_resume": "Native subagent resume is session-scoped; cross-session workflow resume needs the substrate (DL-001).",
        "verdict": "A4_CONFIRMED" if join_ok else "A4_JOIN_MISMATCH",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="A4 native subagent-transcript probe")
    ap.add_argument("--session", dest="session_id", default=None)
    ap.add_argument("--agent-id", dest="native_agent_id", default=None)
    ap.add_argument("--cwd", dest="cwd", default=os.getcwd())
    args = ap.parse_args()
    result = probe_subagent_transcript(args.session_id, args.native_agent_id, args.cwd)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
