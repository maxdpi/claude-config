#!/usr/bin/env python3
"""Orchestration mode selection: Agent Teams vs Workflow-tool fallback.

Detects CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS. When set, skills drive
Agent Teams. When unset, they fall back to the Workflow tool + Agent-tool
subagents, producing identical durable events either way (DL-007/DL-009).

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

import os
from dataclasses import dataclass
from typing import Literal

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

    The fallback path (mode="workflow") produces IDENTICAL durable event
    types and projection as the team path — same TaskCreated / TaskCompleted
    events via M-003 hooks — so resume works across both paths (DL-007).
    """
    env_value = os.environ.get(AGENT_TEAMS_ENV)
    available = bool(env_value)  # non-empty string -> available

    return ModeDescriptor(
        mode="agent_teams" if available else "workflow",
        agent_teams_available=available,
        env_var=AGENT_TEAMS_ENV,
        env_value=env_value,
    )


def is_agent_teams_available() -> bool:
    """Convenience predicate; prefer select_orchestration_mode() for logging.

    Use select_orchestration_mode() when you need diagnostic context (env var
    name/value) for error messages or startup output. is_agent_teams_available()
    is for simple boolean branches in skill entry points. (ref: DL-009)
    """
    return select_orchestration_mode().agent_teams_available
