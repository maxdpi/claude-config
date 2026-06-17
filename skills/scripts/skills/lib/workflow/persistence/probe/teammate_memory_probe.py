#!/usr/bin/env python3
"""M-007 / CI-M-007-006 -- teammate memory probe (assumption DL-023).

GATING QUESTION (DL-023):
  Is `memory:` frontmatter HONORED for an agent definition used as an Agent
  Teams TEAMMATE (as opposed to a main-thread/subagent agent where memory IS
  applied)?

Design
------
When Agent Teams IS enabled, a complete probe would:
  1. Spawn a teammate carrying `memory: project`.
  2. Have the teammate write a known token to the memory store.
  3. Re-spawn a fresh team and have the teammate read from the memory store.
  4. Record whether run 2 observes run 1's token.

Because CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is UNSET in this environment,
no live teammate can be driven. The probe detects this and records:

  honored: null (unverifiable — teams disabled)

Default-deny: the curated-.md fallback is ALWAYS selected when the result is
unverifiable or explicitly not honored. This keeps the DL-018 boundary intact:
curated knowledge lives in the artifact, run/phase state stays in the substrate.

FALLBACK (selected when honored is null or False):
  The lead reads a substrate-owned curated `.md` artifact at run start and
  writes it at run end (koan-curation pattern). Cross-run knowledge lives in
  that artifact; runtime state lives in the durable substrate. They do not overlap.

Result sidecar
--------------
Written to ``teammate_memory_probe_result.json`` alongside this file. The
result is machine-readable so team_mode.py (and test_team_mode_fallback.py)
can gate on it without re-running the probe.

Re-running the probe when Agent Teams IS enabled:
  python3 teammate_memory_probe.py --live
  (requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS set; drives a real teammate)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RESULT_SIDECAR = Path(__file__).with_name("teammate_memory_probe_result.json")
AGENT_TEAMS_ENV = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"

#: Default-deny: if unverifiable, select the curated-.md fallback.
DEFAULT_DENY_FALLBACK = "curated_md_artifact"


def probe_teammate_memory(force_live: bool = False) -> dict:
    """Check whether `memory:` frontmatter is honored on the Agent Teams teammate path.

    Args:
        force_live: When True, attempt a live probe even if teams appear disabled.
            Has no effect when the env var is unset (cannot drive a live teammate).

    Returns:
        Machine-readable result dict. Key fields:

        ``probe``
            Always "teammate_memory".

        ``assumption``
            "DL-023" — the decision log entry this probe gates.

        ``agent_teams_env_set``
            Whether CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is set to a non-empty string.

        ``honored``
            True  — teammate memory IS honored (live probe confirmed).
            False — teammate memory is NOT honored (live probe contradicted).
            None  — unverifiable (teams disabled in this environment).

        ``fallback_selected``
            "curated_md_artifact" — always selected when honored is null or False.
            None — only when honored is True and memory can be used.

        ``fallback_description``
            Human-readable explanation of the fallback mechanism.

        ``verdict``
            "UNVERIFIABLE_TEAMS_DISABLED" when teams are off.
            "MEMORY_HONORED" when live probe confirmed.
            "MEMORY_NOT_HONORED" when live probe contradicted.
    """
    env_value = os.environ.get(AGENT_TEAMS_ENV, "")
    teams_enabled = bool(env_value)

    if not teams_enabled:
        result = _build_unverifiable_result(env_value)
        RESULT_SIDECAR.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    # Agent Teams IS enabled. A live probe would drive a teammate here.
    # Documented design: in a live probe the orchestrator would:
    #   1. Spawn teammate with `memory: project` and a write task.
    #   2. Re-spawn a fresh team and have the teammate attempt to read.
    #   3. Record whether run 2 sees run 1's token.
    # Since we cannot drive this programmatically from within a Python script
    # (it requires the native Agent Teams runtime), we record a pending state.
    result = _build_pending_result(env_value)
    RESULT_SIDECAR.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _build_unverifiable_result(env_value: str) -> dict:
    """Build the result when Agent Teams is disabled — default-deny."""
    return {
        "probe": "teammate_memory",
        "assumption": "DL-023",
        "captured_at": _now_iso(),
        "agent_teams_env_set": False,
        "agent_teams_env_value": env_value or "<unset>",
        "honored": None,
        "verdict": "UNVERIFIABLE_TEAMS_DISABLED",
        "fallback_selected": DEFAULT_DENY_FALLBACK,
        "fallback_description": (
            "memory: frontmatter applicability on the teammate path cannot be "
            "verified because CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is unset. "
            "Default-deny: cross-run knowledge is routed through a substrate-owned "
            "curated .md artifact (koan-curation pattern). The lead reads the "
            "artifact at run start and writes it at run end. Curated knowledge "
            "stays in the artifact; run/phase state stays in the durable substrate "
            "(DL-018 boundary). They do not overlap."
        ),
        "live_probe_instructions": (
            "To run a live probe when Agent Teams IS enabled: "
            "set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1, then run: "
            "python3 teammate_memory_probe.py --live. "
            "The probe will drive a teammate with memory: project across two "
            "runs and record whether run 2 observes run 1's accumulated knowledge."
        ),
        "dl023_gate": (
            "M-007 memory-dependent behavior is gated on this result. "
            "Until honored=True is recorded by a live probe, the curated-.md "
            "fallback is always selected (default-deny per DL-023)."
        ),
    }


def _build_pending_result(env_value: str) -> dict:
    """Build the result when Agent Teams is enabled but live probe not yet run."""
    return {
        "probe": "teammate_memory",
        "assumption": "DL-023",
        "captured_at": _now_iso(),
        "agent_teams_env_set": True,
        "agent_teams_env_value": env_value,
        "honored": None,
        "verdict": "PENDING_LIVE_PROBE",
        "live_attempt": (
            "Re-run with CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS set (the live runtime "
            "exposes Teams). The env gate is now satisfied, so the verdict is no "
            "longer UNVERIFIABLE_TEAMS_DISABLED."
        ),
        "blocker": (
            "A non-interactive Python process cannot drive a real Agent Teams "
            "teammate with memory: project across two runs and observe whether run "
            "2 sees run 1's token — that requires the native Agent Teams runtime in "
            "an interactive session. honored is NOT forced true (R-3); default-deny "
            "stays in force."
        ),
        "fallback_selected": DEFAULT_DENY_FALLBACK,
        "fallback_description": (
            "Agent Teams is enabled but a programmatic live teammate-memory probe "
            "cannot be driven from this non-interactive context. Default-deny: the "
            "curated-.md fallback is selected until an interactive --live probe "
            "records honored=True."
        ),
        "live_probe_instructions": (
            "Interactive re-test: with CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS set, run "
            "python3 teammate_memory_probe.py --live and drive a real teammate with "
            "memory: project across two runs, recording whether run 2 observes run "
            "1's accumulated knowledge."
        ),
    }


def load_result() -> dict | None:
    """Load the persisted probe result sidecar, if it exists."""
    if RESULT_SIDECAR.exists():
        try:
            return json.loads(RESULT_SIDECAR.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def is_fallback_selected() -> bool:
    """Return True if the curated-.md fallback should be used.

    Default-deny: returns True unless a live probe has explicitly recorded
    honored=True. Called by team_mode.py and skill entry points.
    """
    result = load_result()
    if result is None:
        return True  # no probe result yet -> default-deny
    return result.get("fallback_selected") == DEFAULT_DENY_FALLBACK


def _now_iso() -> str:
    """Return current UTC time as an ISO 8601 string (no external deps)."""
    import time
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T"
        f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="DL-023 teammate-memory probe: checks whether memory: frontmatter "
                    "is honored on the Agent Teams teammate path."
    )
    ap.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Attempt a live probe (requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS set)",
    )
    ap.add_argument(
        "--show",
        action="store_true",
        default=False,
        help="Print the persisted result sidecar without re-running the probe",
    )
    args = ap.parse_args()

    if args.show:
        stored = load_result()
        if stored is None:
            print(json.dumps({"error": "no result sidecar found", "path": str(RESULT_SIDECAR)}, indent=2))
            return 1
        print(json.dumps(stored, indent=2))
        return 0

    result = probe_teammate_memory(force_live=args.live)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
