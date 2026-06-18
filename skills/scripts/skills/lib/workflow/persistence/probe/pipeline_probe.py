#!/usr/bin/env python3
"""M-001 / DL-T1-05 — pipeline() availability and /tmp artifact-survival probe.

GATING QUESTION (DL-T1-05):
  Is the Workflow tool's `pipeline()` primitive (a) available as an SDK primitive
  and (b) able to relay /tmp filesystem artifacts written by an earlier stage into
  a downstream stage running under isolation:\"worktree\"?

Why this probe exists
---------------------
The arxiv-to-md convert->finalize coupling is filesystem-mediated: converter agents
write /tmp/arxiv_<id>/cleaned.md under isolation:\"worktree\"; finalize reads those
paths.  Re-expressing this coupling via pipeline() is only safe if:
  (a) pipeline() exists as an SDK primitive (not merely CI-pipeline prose), AND
  (b) /tmp artifacts written in stage 1 survive into stage 2 when stages run
      under worktree isolation.

Grep over docs/ finds zero SDK-primitive mentions of pipeline() — only unrelated
CI-pipeline prose.  This probe is the gate: M-006's convert->finalize restructuring
ships only if this probe records approved=true.  Otherwise the existing
parallel(convert)->agent(finalize) sequence is preserved unchanged (DL-T1-05).

Design
------
This probe cannot invoke the Workflow runtime from a non-interactive Python context.
It honestly records INCONCLUSIVE_NONINTERACTIVE and documents the required
interactive re-test.  Per DL-T1-05, the default outcome when inconclusive is to
keep the existing sequence (recommended_m006_path = \"sequence\").

Verdict enum: {APPROVED, REJECTED, INCONCLUSIVE_NONINTERACTIVE}.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RESULT_SIDECAR = Path(__file__).with_name("pipeline_probe_result.json")


def _now_iso() -> str:
    import time
    t = time.gmtime()
    return (
        f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T"
        f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}Z"
    )


def probe_pipeline(
    interactive: bool = False,
    pipeline_available: bool | None = None,
    tmp_survives: bool | None = None,
) -> dict:
    """Resolve the pipeline() availability and /tmp artifact-survival verdict.

    Args:
        interactive: Set True only when an interactive Claude session is driving
            real invocation trials and filling in observed outcomes.
        pipeline_available: Observed result of calling pipeline() in the Workflow
            tool.  None when not tested (non-interactive context).
        tmp_survives: Observed result of writing /tmp/probe_pipeline/marker.md in
            stage 1 and reading it back in stage 2.  None when not tested.

    Returns:
        Machine-readable result dict (also written to the sidecar).
    """
    if interactive and pipeline_available is not None:
        if pipeline_available and tmp_survives:
            verdict = "APPROVED"
        else:
            verdict = "REJECTED"
    else:
        verdict = "INCONCLUSIVE_NONINTERACTIVE"

    # The default M-006 path when inconclusive or rejected is to preserve the
    # existing parallel(convert)->agent(finalize) sequence (DL-T1-05 fallback).
    recommended_m006_path = "pipeline" if verdict == "APPROVED" else "sequence"

    result = {
        "probe": "pipeline",
        "decision_log": "DL-T1-05",
        "gates_milestone": "M-006 (arxiv convert->finalize restructuring)",
        "captured_at": _now_iso(),
        "interactive_session": bool(interactive),
        "checks": {
            "pipeline_available": pipeline_available,
            "tmp_artifact_survives_worktree_isolation": tmp_survives,
        },
        "verdict": verdict,
        "verdict_enum": ["APPROVED", "REJECTED", "INCONCLUSIVE_NONINTERACTIVE"],
        "recommended_m006_path": recommended_m006_path,
        "recommended_m006_path_enum": ["pipeline", "sequence"],
        "resolution": (
            "APPROVED: pipeline() is available and /tmp artifacts survive worktree "
            "isolation — M-006 may restructure convert->finalize via pipeline(). "
            if verdict == "APPROVED"
            else (
                "REJECTED: pipeline() is unavailable or /tmp artifacts are lost "
                "under worktree isolation — M-006 must preserve the existing "
                "parallel(convert)->agent(finalize) sequence unchanged. "
                if verdict == "REJECTED"
                else (
                    "INCONCLUSIVE_NONINTERACTIVE: a real invocation spike requires "
                    "an interactive Workflow-tool session and cannot be performed "
                    "from a non-interactive Python context.  Per DL-T1-05, the "
                    "default fallback is 'sequence' (keep the existing path)."
                )
            )
        ),
        "grep_evidence": (
            "grep -r 'pipeline' docs/ returns only CI-pipeline prose; "
            "zero SDK-primitive mentions of a pipeline() Workflow-tool function."
        ),
        "live_probe_instructions": (
            "Interactive re-test: in a Workflow-tool session, (1) call pipeline() "
            "with a two-stage toy flow where stage 1 writes "
            "/tmp/probe_pipeline/marker.md under isolation:\"worktree\" and stage 2 "
            "attempts to read it back; (2) record whether pipeline() resolves "
            "without error and whether the marker.md is readable in stage 2; "
            "(3) re-run this probe with --interactive "
            "--pipeline-available=true|false --tmp-survives=true|false."
        ),
    }
    RESULT_SIDECAR.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
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
        description=(
            "DL-T1-05 pipeline() availability probe: gates M-006 arxiv "
            "convert->finalize restructuring."
        )
    )
    ap.add_argument("--show", action="store_true", default=False,
                    help="Print the persisted result sidecar without re-running.")
    ap.add_argument("--interactive", action="store_true", default=False,
                    help="Mark this run as an interactive invocation spike.")
    ap.add_argument("--pipeline-available", choices=["true", "false"], default=None,
                    help="Whether pipeline() resolved without error (interactive only).")
    ap.add_argument("--tmp-survives", choices=["true", "false"], default=None,
                    help="Whether /tmp artifacts were readable in stage 2 (interactive only).")
    args = ap.parse_args()

    if args.show:
        stored = load_result()
        print(json.dumps(stored or {"error": "no result sidecar found"}, indent=2))
        return 0 if stored else 1

    pipeline_available = (
        args.pipeline_available == "true" if args.pipeline_available is not None else None
    )
    tmp_survives = (
        args.tmp_survives == "true" if args.tmp_survives is not None else None
    )

    result = probe_pipeline(
        interactive=args.interactive,
        pipeline_available=pipeline_available,
        tmp_survives=tmp_survives,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
