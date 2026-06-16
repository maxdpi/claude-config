#!/usr/bin/env python3
"""Assert: real SubagentStart/Stop payloads carry the fields hook_adapter assumes.

PURPOSE (R-008 verdict):
    After running S1 (dump_payload_hook installed, subagent spawned), this
    script reads the captured JSONL files and cross-checks every field constant
    defined in hook_adapter._PAYLOAD_* against the actual payload keys.

    For each assumed field it reports:
        CONFIRMED  — the exact assumed name is present with a non-None value
        ABSENT     — the assumed name is not present; shows fuzzy-match candidates
        NULL       — the assumed name is present but the value is None/empty

    Also specifically checks whether SubagentStop carries `transcript_path`
    (the copy-on-stop primary path, DL-016).

USAGE:
    python3 tests/live/assert/assert_payload_fields.py

    Run from the repo root, or any directory — the script uses absolute paths.
    The script finds the debug dir at ~/.claude/skill-runs-debug/.

PREREQUISITES:
    - Scenario S1 must have been run (dump_payload_hook installed + subagent spawned)
    - ~/.claude/skill-runs-debug/payloads-SubagentStart.jsonl must exist

OUTPUTS:
    Prints PASS/FAIL lines to stdout. Exits 0 even on FAIL so you can pipe
    the output. Check for FAIL lines manually.

WHAT IT READS:
    ~/.claude/skill-runs-debug/payloads-SubagentStart.jsonl
    ~/.claude/skill-runs-debug/payloads-SubagentStop.jsonl  (optional)

WHAT IT NEVER TOUCHES:
    ~/.claude/teams, ~/.claude/tasks, ~/.claude/skill-runs
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the substrate module to read the _PAYLOAD_* constants.
# The repo may be synced to ~/.claude as per PLATFORM-ASSUMPTIONS.md note.
# Try both the worktree location and the installed location.
# ---------------------------------------------------------------------------

_REPO_CANDIDATES: list[Path] = [
    # When running from the worktree / repo checkout
    Path(__file__).parent.parent.parent.parent / "skills" / "scripts",
    # When the repo is synced to ~/.claude/skills/scripts
    Path.home() / ".claude" / "skills" / "scripts",
]

_substrate_loaded = False
for _candidate in _REPO_CANDIDATES:
    if _candidate.exists() and (_candidate / "skills").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        try:
            import skills.lib.workflow.persistence.hook_adapter as _ha  # type: ignore[import]
            _substrate_loaded = True
            break
        except ImportError:
            continue

if not _substrate_loaded:
    print("ERROR: cannot import hook_adapter from any candidate path:")
    for c in _REPO_CANDIDATES:
        print(f"  {c}")
    print("Ensure the repo is checked out at one of these locations.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Debug capture directory
# ---------------------------------------------------------------------------

_DEBUG_DIR: Path = Path.home() / ".claude" / "skill-runs-debug"

# ---------------------------------------------------------------------------
# The assumed field names from hook_adapter (R-008 constants)
# ---------------------------------------------------------------------------

ASSUMED_FIELDS_START: dict[str, str] = {
    "agentId": _ha._PAYLOAD_AGENT_ID,
    "sessionId": _ha._PAYLOAD_SESSION_ID,
    "parentAgentId": _ha._PAYLOAD_PARENT_AGENT_ID,
    "depth": _ha._PAYLOAD_DEPTH,
}

ASSUMED_FIELDS_STOP: dict[str, str] = {
    "agentId": _ha._PAYLOAD_AGENT_ID,
    "sessionId": _ha._PAYLOAD_SESSION_ID,
    "transcript_path": _ha._PAYLOAD_TRANSCRIPT_PATH,
}

# ---------------------------------------------------------------------------
# Fuzzy-match helpers
# ---------------------------------------------------------------------------

_FUZZY_ALIASES: dict[str, list[str]] = {
    "agentId": ["agent_id", "agent-id", "agentid", "AgentId", "AGENT_ID"],
    "sessionId": ["session_id", "session-id", "sessionid", "SessionId", "SESSION_ID"],
    "parentAgentId": ["parent_agent_id", "parentagentid", "ParentAgentId", "parent_id"],
    "depth": ["nesting_depth", "nestingDepth", "level"],
    "transcript_path": ["transcriptPath", "transcript-path", "TranscriptPath"],
}


def _fuzzy_find(key: str, payload: dict) -> str | None:
    """Return an alternative key that carries the same data, or None."""
    aliases = _FUZZY_ALIASES.get(key, [])
    for alias in aliases:
        if alias in payload:
            return alias
    # Substring match: look for any key containing a recognizable fragment
    key_lower = key.lower().replace("_", "").replace("-", "")
    for pk in payload:
        if pk.lower().replace("_", "").replace("-", "") == key_lower:
            return pk
    return None


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------

def _load_payloads(event_name: str) -> list[dict]:
    """Load all captured payloads for an event type."""
    path = _DEBUG_DIR / f"payloads-{event_name}.jsonl"
    if not path.exists():
        return []
    payloads: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            payloads.append(record.get("payload") or {})
        except json.JSONDecodeError:
            pass
    return payloads


def _check_fields(
    event_name: str,
    payloads: list[dict],
    assumed: dict[str, str],
) -> list[str]:
    """Check assumed field names against real payloads. Returns verdict lines."""
    results: list[str] = []

    if not payloads:
        results.append(f"  SKIP  {event_name}: no captured payloads in {_DEBUG_DIR}/payloads-{event_name}.jsonl")
        return results

    # Merge all unique keys seen across all payloads for a richer report
    all_keys: set[str] = set()
    for p in payloads:
        all_keys.update(p.keys())

    results.append(f"  INFO  {event_name}: {len(payloads)} captured payload(s); keys seen: {sorted(all_keys)}")

    for label, assumed_name in assumed.items():
        # Check against ALL payloads — report the worst-case (absent/null) if any
        found_values: list = []
        for p in payloads:
            if assumed_name in p:
                found_values.append(p[assumed_name])

        if not found_values:
            # Not found under assumed name — try fuzzy
            alt = _fuzzy_find(assumed_name, payloads[0])
            if alt:
                alt_values = [p.get(alt) for p in payloads if alt in p]
                results.append(
                    f"  FAIL  {event_name}.{assumed_name} (assumed _PAYLOAD_{label.upper()}={assumed_name!r}):"
                    f" NOT FOUND under assumed name."
                    f" Found under '{alt}' with values {alt_values[:3]}."
                    f" => UPDATE hook_adapter._PAYLOAD_{label.upper()} = {alt!r}"
                )
            else:
                results.append(
                    f"  FAIL  {event_name}.{assumed_name} (assumed _PAYLOAD_{label.upper()}={assumed_name!r}):"
                    f" NOT FOUND under any recognizable name."
                    f" All keys in payload: {sorted(all_keys)}"
                )
        else:
            non_null = [v for v in found_values if v is not None and v != ""]
            if non_null:
                results.append(
                    f"  PASS  {event_name}.{assumed_name} (constant={assumed_name!r}):"
                    f" present, non-null in {len(non_null)}/{len(payloads)} payloads."
                    f" Sample value: {non_null[0]!r}"
                )
            else:
                # Present but always null/empty — may be optional (parentAgentId, depth)
                results.append(
                    f"  WARN  {event_name}.{assumed_name} (constant={assumed_name!r}):"
                    f" present but always None/empty."
                    f" (For parentAgentId/depth this is expected for top-level agents.)"
                )

    return results


def _check_transcript_path_on_stop(payloads_stop: list[dict]) -> list[str]:
    """Specifically assert whether SubagentStop carries transcript_path (DL-016)."""
    results: list[str] = []
    if not payloads_stop:
        results.append(
            "  SKIP  SubagentStop.transcript_path: no Stop payloads captured."
            " (DL-016 copy-on-stop primary path — unverified)"
        )
        return results

    tp_name = _ha._PAYLOAD_TRANSCRIPT_PATH  # "transcript_path"
    payloads_with_tp = [p for p in payloads_stop if tp_name in p and p[tp_name]]
    payloads_null_tp = [p for p in payloads_stop if tp_name in p and not p[tp_name]]
    payloads_absent_tp = [p for p in payloads_stop if tp_name not in p]

    if payloads_with_tp:
        results.append(
            f"  PASS  SubagentStop.transcript_path: PRESENT AND NON-NULL in"
            f" {len(payloads_with_tp)}/{len(payloads_stop)} payloads."
            f" Sample: {payloads_with_tp[0][tp_name]!r}"
            f" => DL-016 PRIMARY PATH IS DELIVERED BY RUNTIME. No derive-path fallback needed."
        )
    elif payloads_null_tp:
        results.append(
            f"  WARN  SubagentStop.transcript_path: field present but value is"
            f" None/empty in {len(payloads_null_tp)}/{len(payloads_stop)} payloads."
            f" => copy-on-stop will fall back to derive-path (DL-016 fallback)."
        )
    else:
        # Check camelCase alias
        alt = "transcriptPath"
        if any(alt in p for p in payloads_stop):
            alt_vals = [p[alt] for p in payloads_stop if alt in p]
            results.append(
                f"  FAIL  SubagentStop.transcript_path: field ABSENT under 'transcript_path'."
                f" Found under '{alt}' with values {alt_vals[:2]}."
                f" => UPDATE hook_adapter._PAYLOAD_TRANSCRIPT_PATH = {alt!r}"
            )
        else:
            results.append(
                f"  WARN  SubagentStop.transcript_path: field ABSENT from all"
                f" {len(payloads_absent_tp)} captured Stop payloads."
                f" => Runtime does NOT deliver transcript_path in SubagentStop."
                f" copy-on-stop will always derive the path from sessionId+agentId (DL-016 fallback)."
            )

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("R-008 VERDICT: hook_adapter._PAYLOAD_* field name validation")
    print(f"Debug dir: {_DEBUG_DIR}")
    print("=" * 72)

    payloads_start = _load_payloads("SubagentStart")
    payloads_stop = _load_payloads("SubagentStop")

    # Check SubagentStart fields
    print("\n--- SubagentStart ---")
    for line in _check_fields("SubagentStart", payloads_start, ASSUMED_FIELDS_START):
        print(line)

    # Check SubagentStop fields
    print("\n--- SubagentStop ---")
    for line in _check_fields("SubagentStop", payloads_stop, ASSUMED_FIELDS_STOP):
        print(line)

    # Specific transcript_path check
    print("\n--- transcript_path (DL-016 copy-on-stop primary) ---")
    for line in _check_transcript_path_on_stop(payloads_stop):
        print(line)

    # Summary: count FAIL lines
    all_lines: list[str] = []
    all_lines.extend(_check_fields("SubagentStart", payloads_start, ASSUMED_FIELDS_START))
    all_lines.extend(_check_fields("SubagentStop", payloads_stop, ASSUMED_FIELDS_STOP))
    all_lines.extend(_check_transcript_path_on_stop(payloads_stop))

    fails = [l for l in all_lines if l.strip().startswith("FAIL")]
    warns = [l for l in all_lines if l.strip().startswith("WARN")]

    print("\n" + "=" * 72)
    if not payloads_start and not payloads_stop:
        print("RESULT: NO DATA — run Scenario S1 first (install debug hooks + spawn a subagent)")
    elif fails:
        print(f"RESULT: FAIL — {len(fails)} field name mismatch(es) found.")
        print("Hook constants to update in hook_adapter.py are listed above (=> UPDATE lines).")
    elif warns:
        print(f"RESULT: PASS with {len(warns)} warning(s) — review WARN lines above.")
        print("Core field names are confirmed. Optional fields (parentAgentId, transcript_path) may be absent.")
    else:
        print("RESULT: PASS — all assumed field names confirmed against live payloads.")
    print("=" * 72)


if __name__ == "__main__":
    main()
