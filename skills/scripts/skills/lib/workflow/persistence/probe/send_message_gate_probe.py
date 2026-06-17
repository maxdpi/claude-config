#!/usr/bin/env python3
"""Item D / DL-031 -- SendMessage availability gate probe (assumption A4).

GATING QUESTION (DL-031):
  Is the `SendMessage` tool actually INVOCABLE only when Agent Teams is enabled
  (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), as the official docs state, or is
  it available regardless?

Why this probe exists
---------------------
The `subagent_transcript` probe recorded `send_message.available: true` with
Teams UNSET, but its SOLE evidence was that the Agent-tool RESULT STRING said
"use SendMessage ... to continue this agent". A tool being *mentioned* in result
prose is not the same as the tool being *invocable* (result-text scraping is a
weak evidence class — the runtime emits such hint strings regardless of whether
the tool is gated). DL-031 supersedes that with an invocation-outcome test.

Authoritative prior
-------------------
`docs/claude_code docs/build/sub-agents.md` line 653:
  "The `SendMessage` tool is only available when agent teams are enabled via
   `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`."

Design (live invocation spike)
------------------------------
A complete spike would, for each of {Teams UNSET, Teams SET}:
  1. Spawn a fresh subagent via the Agent tool and capture its agentId.
  2. ATTEMPT to invoke `SendMessage(to=agentId, ...)`.
  3. Record the observed outcome: success vs InputValidationError / unknown-tool.

`SendMessage` is a Claude Code RUNTIME tool, not a Python-importable API, so this
outcome can only be produced from an INTERACTIVE Claude session driving the two
trials. Run from a non-interactive Python context this probe cannot invoke it and
honestly records `INCONCLUSIVE_NONINTERACTIVE` (R-4) — never an unevidenced
"available". Per DL-031/A-DOC-AUTHORITATIVE, the official doc (line 653) is then
the authoritative prior: SendMessage is gated behind Teams.

Verdict enum: {GATED_BY_TEAMS, RUNTIME_DIVERGENCE, INCONCLUSIVE_NONINTERACTIVE}.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

RESULT_SIDECAR = Path(__file__).with_name("send_message_gate_probe_result.json")
AGENT_TEAMS_ENV = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
DOC_CITATION = "docs/claude_code docs/build/sub-agents.md:653"


def _now_iso() -> str:
    import time
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T"
        f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )


def probe_send_message_gate(interactive: bool = False) -> dict:
    """Resolve the SendMessage availability gate verdict.

    Args:
        interactive: Set True only when an interactive Claude session is driving
            real invocation trials and filling in observed outcomes. A plain
            Python run leaves it False and records INCONCLUSIVE_NONINTERACTIVE.

    Returns:
        Machine-readable result dict (also written to the sidecar).
    """
    env_value = os.environ.get(AGENT_TEAMS_ENV, "")

    # A non-interactive Python process cannot invoke the runtime SendMessage tool,
    # so the per-trial observed outcome is the same honest "not invocable here".
    trials = [
        {
            "agent_teams_env": "<unset>",
            "expected_per_doc": "SendMessage NOT available",
            "observed_outcome": (
                "not invocable from a non-interactive Python probe; "
                "no real invocation attempt could be made"
            ),
        },
        {
            "agent_teams_env": "1",
            "expected_per_doc": "SendMessage available",
            "observed_outcome": (
                "not invocable from a non-interactive Python probe; "
                "no real invocation attempt could be made"
            ),
        },
    ]

    verdict = "INCONCLUSIVE_NONINTERACTIVE"
    result = {
        "probe": "send_message_gate",
        "assumption": "A4",
        "decision_log": "DL-031",
        "captured_at": _now_iso(),
        "agent_teams_env_at_capture": env_value or "<unset>",
        "interactive_session": bool(interactive),
        "trials": trials,
        "verdict": verdict,
        "verdict_enum": ["GATED_BY_TEAMS", "RUNTIME_DIVERGENCE", "INCONCLUSIVE_NONINTERACTIVE"],
        "authoritative_prior": {
            "citation": DOC_CITATION,
            "statement": (
                "The SendMessage tool is only available when agent teams are "
                "enabled via CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1."
            ),
        },
        "resolution": (
            "INCONCLUSIVE_NONINTERACTIVE: a real invocation spike requires an "
            "interactive Agent Teams session and could not be performed from this "
            "non-interactive context. Per DL-031/A-DOC-AUTHORITATIVE, defer to the "
            "official doc (gated behind Teams). The prior result-string-scrape "
            "claim of 'available:true' with Teams UNSET is NOT reproduced here: it "
            "was advertisement, not an invocation outcome. Interactive re-test is "
            "required to claim any runtime divergence."
        ),
        "operational_risk": (
            "LOW: the substrate does not depend on SendMessage. DL-009 resume "
            "re-invokes the entry point; SendMessage is not adopted as a resume "
            "mechanism. This gate only matters if the substrate ever delegates "
            "session-scoped resume to native SendMessage."
        ),
        "supersedes": "subagent_transcript_probe_result.json#send_message (result-string evidence)",
        "live_probe_instructions": (
            "Interactive re-test: in a Claude session, (1) with "
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS unset, spawn a subagent and "
            "attempt SendMessage(to=<agentId>); record success vs error class. "
            "(2) Repeat with the env set to 1. Fill trials[].observed_outcome and "
            "set verdict to GATED_BY_TEAMS or RUNTIME_DIVERGENCE accordingly."
        ),
    }
    RESULT_SIDECAR.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def load_result() -> dict | None:
    if RESULT_SIDECAR.exists():
        try:
            return json.loads(RESULT_SIDECAR.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="DL-031 SendMessage gate probe: tests whether SendMessage is "
                    "invocable only with Agent Teams enabled."
    )
    ap.add_argument("--show", action="store_true", default=False,
                    help="Print the persisted result sidecar without re-running.")
    ap.add_argument("--interactive", action="store_true", default=False,
                    help="Mark this run as an interactive invocation spike.")
    args = ap.parse_args()

    if args.show:
        stored = load_result()
        print(json.dumps(stored or {"error": "no result sidecar found"}, indent=2))
        return 0 if stored else 1

    result = probe_send_message_gate(interactive=args.interactive)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
