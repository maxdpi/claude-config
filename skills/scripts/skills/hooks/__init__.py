#!/usr/bin/env python3
"""Claude Code hook entrypoints for the durable persistence substrate (M-003).

Each module in this package is a standalone hook script invoked by the
Claude Code hook system.  All hooks:
  - read their JSON payload from stdin (CC hook convention).
  - exit with code 0 regardless of internal errors (non-fatal, DL-019).
  - never write inside ~/.claude/teams or ~/.claude/tasks (DL-002).
"""
