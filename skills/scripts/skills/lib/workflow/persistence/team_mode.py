#!/usr/bin/env python3
"""Orchestration mode selection: Agent Teams vs Agent-tool subagent fallback.

Detects CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS. When set, the lead (main session)
spawns workers as Agent Teams teammates in natural language. When unset, the lead
spawns them as Agent-tool subagents (`Agent(subagent_type=...)`). Both paths emit
identical durable events (TaskCreated / TaskCompleted via M-003 hooks) so resume
works across both paths (DL-007/DL-009).

The fallback (mode="workflow") uses Agent-tool subagents, NOT a workflow.mjs or
a python --step CLI. The mode name "workflow" is a substrate label only; no
workflow.mjs is involved for adversarial skills.

Never pre-author team config or task dirs: Agent Teams dirs are ephemeral
and must not be seeded before the session starts (A3).

Resume integration
------------------
compute_remaining_tasks() already lives in resume.py and is the canonical
function for deriving incomplete tasks from the durable event log. Import
and use it from there; do NOT duplicate the logic here (DL-007).

    from skills.lib.workflow.persistence.resume import compute_remaining_tasks
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

OrchestrationMode = Literal["agent_teams", "workflow"]

#: Environment variable that gates Agent Teams mode (also used by resume.py).
AGENT_TEAMS_ENV: str = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"


@dataclass
class ModeDescriptor:
    """Selected orchestration mode with diagnostic info."""

    mode: OrchestrationMode
    agent_teams_available: bool
    env_var: str
    env_value: str | None


def select_orchestration_mode() -> ModeDescriptor:
    """Detect whether Agent Teams is available and return the active mode.

    Returns:
        ModeDescriptor with mode="agent_teams" if
        CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is a non-empty string,
        otherwise mode="workflow".

    Note: The env var must be set to a non-empty string to activate Agent
    Teams. An empty string (the default in settings.json) means "off" so
    settings.json can document the var without activating it accidentally.

    The fallback path (mode="workflow") uses Agent-tool subagents instead of
    Agent Teams teammates. It produces IDENTICAL durable event types and
    projection as the team path — same TaskCreated / TaskCompleted events via
    M-003 hooks — so resume works across both paths (DL-007). No workflow.mjs
    or python --step CLI is involved in the fallback for adversarial skills.
    """
    env_value = os.environ.get(AGENT_TEAMS_ENV)
    available = bool(env_value)  # non-empty string -> available

    return ModeDescriptor(
        mode="agent_teams" if available else "workflow",
        agent_teams_available=available,
        env_var=AGENT_TEAMS_ENV,
        env_value=env_value,
    )


def read_orchestration_mode(run: Any) -> str | None:
    """Read the mode recorded in a run's ``run-state.json`` at creation time.

    A run's orchestration mode is a historical fact fixed when the run was
    created (DL-T1-01); resume must prefer this recorded value over the live
    env var, which can differ from the session that created the run. Co-located
    here because this module already owns the mode vocabulary (DL-T1-03).

    Args:
        run: Any object exposing a ``run_state`` Path (``RunHandle`` or
            ``RunDir`` both qualify).

    Returns:
        The persisted ``orchestration_mode`` string, or ``None`` when the
        run-state file or the field is absent (legacy runs created before the
        field existed) — the caller then falls back to the live env var.
    """
    try:
        data = json.loads(run.run_state.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data.get("orchestration_mode")


def is_agent_teams_available() -> bool:
    """Convenience predicate; prefer select_orchestration_mode() for logging.

    Use select_orchestration_mode() when you need diagnostic context (env var
    name/value) for error messages or startup output. is_agent_teams_available()
    is for simple boolean branches in skill entry points. (ref: DL-009)
    """
    return select_orchestration_mode().agent_teams_available
