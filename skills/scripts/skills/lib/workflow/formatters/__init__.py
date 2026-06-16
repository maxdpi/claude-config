"""Formatters package (LEGACY -- migration target M-008b).

LEGACY: format_step() and build_next_command() print-and-exit step wrappers —
superseded by native Workflow tool / Agent Teams + durable substrate.
Scheduled for deletion in M-008b.

format_step() and build_next_command() print-and-exit step wrappers are
superseded by native Workflow-tool control flow (.mjs). Retained while
Python-CLI skills remain. When parity gate R-004 passes, delete this package
and remove all references across the skill suite.
Deletion gate: parity fixtures for all skills must pass (R-004) before
format_step() and build_next_command() are removed. (ref: DL-008)
"""
# No exports; formatters live in prompts/step.py until the package is removed.
