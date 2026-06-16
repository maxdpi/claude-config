"""Plain-text prompt building blocks for workflows.

Prompts as strings composed via f-strings. No XML, no AST.
"""

# Pre-deletion update (#1, DL-025): the subagent.py re-exports are removed so
# `subagent.py` can be deleted in the shared-lib batch without breaking
# `from ...prompts import format_step`. Only the surviving formatters remain.
# DL-025 sequencing: this __init__ is updated to drop the subagent imports
# (exposing only format_step from step.py + format_file_content from file.py)
# BEFORE subagent.py is deleted, because the re-exports resolve at module load.
# Deleting subagent.py first would raise ImportError for every importer of the
# `prompts` package, not just users of subagent's own symbols. (ref: DL-025, R-006)
from .step import format_step
from .file import format_file_content

__all__ = [
    "format_step",
    "format_file_content",
]
