"""Structural extraction helpers for the STRUCTURAL-CONTRACT parity layer.

HONEST FRAMING
==============
The old Python skills were script-as-orchestrator: ``python3 -m skills.X --step N``
PRINTS dispatch prose for an LLM to act on — it does not compute a final artifact
deterministically.  The new ``.mjs`` likewise needs the Workflow tool + an LLM to
produce artifacts.  So you CANNOT diff final outputs offline.

What you CAN verify automatically is that the port preserved the skill's
STRUCTURE/CONTRACT: the same phase sequence, the same exploration fan-out shape,
the same output schema keys.  That is what this module extracts.

It catches "the port silently dropped a phase / changed the agent fan-out /
renamed an output key" — it does NOT prove semantic output equivalence (that
needs the live behavioural test kit).

Public API
----------
extract_mjs_structure(path) -> dict
    Parse a ``skills/<name>/workflow.mjs`` and return:
    {
        "phases":       list[str],          # meta.phases titles in order
        "phase_trust":  dict[str, str],     # meta.phaseTrust map
        "agent_calls":  int,                # count of agent( calls
        "agent_types":  list[str],          # agentType:'...' values found
        "output_keys":  list[str],          # top-level keys of the returned artifact
    }

extract_python_structure(skill, ref="0a2a9ac") -> dict
    Recover the old Python orchestrator at git ref ``ref`` and return:
    {
        "steps":               list[str],   # step names in order
        "step_count":          int,         # total declared steps
        "dispatch_agent_types": list[str],  # agent_type / role strings dispatched
        "output_keys":         list[str],   # declared output schema keys (best-effort)
    }
    Uses ``git show`` / ``git archive`` + Python ``ast`` to parse the source
    WITHOUT importing it (the old modules depend on deleted shared libs).
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Resolve the canonical git repo root from the worktree's .git pointer."""
    worktree = Path(__file__).resolve().parent.parent.parent  # tests/tools -> tests -> root
    git_file = worktree / ".git"
    if git_file.is_file():
        # Worktree: .git contains "gitdir: <main-repo>/.git/worktrees/<name>"
        content = git_file.read_text().strip()
        if content.startswith("gitdir:"):
            gitdir = Path(content.split(":", 1)[1].strip())
            # Navigate up from .git/worktrees/<name>/ to repo root
            return gitdir.parent.parent.parent
    # Ordinary repo
    return worktree


_REPO_ROOT: Path = _repo_root()


# ---------------------------------------------------------------------------
# .mjs extractor
# ---------------------------------------------------------------------------

# Patterns for meta block extraction
_META_PHASES_RE = re.compile(
    r'phases\s*:\s*\[([^\]]*)\]',
    re.DOTALL,
)
_META_PHASE_TRUST_RE = re.compile(
    r'phaseTrust\s*:\s*\{([^}]*)\}',
    re.DOTALL,
)
_STRING_VALUE_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')

# agent() call detection — matches agent( at start of a call site
_AGENT_CALL_RE = re.compile(r'\bagent\s*\(')
# agentType:'...' or agentType:"..."
_AGENT_TYPE_RE = re.compile(r'agentType\s*:\s*["\']([^"\']+)["\']')
# top-level return { key1, key2, ... } — last return statement
_RETURN_KEYS_RE = re.compile(r'\breturn\s*\{([^}]*)\}')


def extract_mjs_structure(path: Path | str) -> dict:
    """Parse a workflow.mjs and return its structural contract.

    Tolerant text/regex parsing — the .mjs is JS, not JSON.
    Never executes the file.

    Parameters
    ----------
    path:
        Absolute path to the workflow.mjs file.

    Returns
    -------
    dict with keys:
        phases, phase_trust, agent_calls, agent_types, output_keys
    """
    path = Path(path)
    src = path.read_text(encoding="utf-8")

    # ---- phases ----
    phases: list[str] = []
    m = _META_PHASES_RE.search(src)
    if m:
        for match in _STRING_VALUE_RE.finditer(m.group(1)):
            phases.append(match.group(1) or match.group(2))

    # ---- phase trust ----
    phase_trust: dict[str, str] = {}
    m = _META_PHASE_TRUST_RE.search(src)
    if m:
        block = m.group(1)
        # Each line: "phase_name": "trust_value",
        for entry in re.finditer(r'"([^"]+)"\s*:\s*"([^"]+)"', block):
            phase_trust[entry.group(1)] = entry.group(2)

    # ---- agent calls ----
    agent_calls = len(_AGENT_CALL_RE.findall(src))

    # ---- agent types ----
    agent_types_raw = _AGENT_TYPE_RE.findall(src)
    # Deduplicate while preserving order
    seen: set[str] = set()
    agent_types: list[str] = []
    for t in agent_types_raw:
        if t not in seen:
            seen.add(t)
            agent_types.append(t)

    # ---- output keys ----
    # Find the LAST return { ... } in the run() function body — that is the
    # skill's artifact.  Ignore early short-circuit returns.
    #
    # Two patterns to handle:
    #   return { key: value }  — explicit key: value pairs
    #   return { key }         — ES6 shorthand (variable name IS the key)
    #   return { key1, key2 }  — multiple shorthand keys
    output_keys: list[str] = []
    all_returns = list(_RETURN_KEYS_RE.finditer(src))
    if all_returns:
        last_return = all_returns[-1]
        block = last_return.group(1).strip()
        if block:
            # Try explicit key: value pattern first
            explicit_keys = []
            for key_match in re.finditer(r'(\w+)\s*:', block):
                key = key_match.group(1)
                if key not in {"label", "phase", "agentType", "model"}:
                    explicit_keys.append(key)
            if explicit_keys:
                output_keys = explicit_keys
            else:
                # ES6 shorthand: { key } or { key1, key2 }
                for key_match in re.finditer(r'(\w+)', block):
                    key = key_match.group(1)
                    if key not in {"label", "phase", "agentType", "model", "return"}:
                        output_keys.append(key)

    return {
        "phases": phases,
        "phase_trust": phase_trust,
        "agent_calls": agent_calls,
        "agent_types": agent_types,
        "output_keys": output_keys,
    }


# ---------------------------------------------------------------------------
# Python orchestrator extractor
# ---------------------------------------------------------------------------

# Mapping from skill slug to (python_package_dir, primary_script)
# The package dir is relative to skills/scripts/skills/<pkg>/<file>.py
_SKILL_PYTHON_MAP: dict[str, tuple[str, str]] = {
    "arxiv-to-md":       ("arxiv_to_md",      "main.py"),
    "codebase-analysis": ("codebase_analysis", "analyze.py"),
    "incoherence":       ("incoherence",       "incoherence.py"),
    "leon-writing-style":("leon_writing_style","writing_style.py"),
    "planner":           ("planner",           "orchestrator/planner.py"),
    "prompt-engineer":   ("prompt_engineer",   "optimize.py"),
    "refactor":          ("refactor",          "refactor.py"),
    # adversarial skills (no workflow.mjs — team.md based)
    "decision-critic":   ("decision_critic",   "decision_critic.py"),
    "deepthink":         ("deepthink",         "think.py"),
    "problem-analysis":  ("problem_analysis",  "analyze.py"),
}


def _git_show_source(skill: str, ref: str) -> str | None:
    """Recover Python source via ``git show <ref>:path``.

    Returns the source text, or None if the path doesn't exist at ref.
    Does NOT write any files to the working tree.
    """
    pkg, script = _SKILL_PYTHON_MAP[skill]
    git_path = f"skills/scripts/skills/{pkg}/{script}"
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{git_path}"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.SubprocessError, OSError):
        return None


# --- AST helpers (no import of the old module) ---

def _ast_extract_total_steps(tree: ast.Module, source: str) -> int | None:
    """Walk the AST to find TOTAL_STEPS or an equivalent count assignment."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "TOTAL_STEPS", "total_steps"
                ):
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, int
                    ):
                        return node.value.value
    return None


def _ast_extract_step_names(tree: ast.Module) -> list[str]:
    """Extract step names from STATIC_STEPS / SCOPE_STEPS / Workflow / StepDef patterns."""
    names: list[str] = []

    for node in ast.walk(tree):
        # Pattern: STATIC_STEPS = {1: ("Name", ...), ...}
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "STATIC_STEPS", "SCOPE_STEPS"
                ):
                    if isinstance(node.value, ast.Dict):
                        for val in node.value.values:
                            if isinstance(val, ast.Tuple) and val.elts:
                                first = val.elts[0]
                                if isinstance(first, ast.Constant) and isinstance(
                                    first.value, str
                                ):
                                    names.append(first.value)

        # Pattern: StepDef(id="...", title="...")
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == "StepDef") or (
                isinstance(func, ast.Attribute) and func.attr == "StepDef"
            ):
                for kw in node.keywords:
                    if kw.arg == "title" and isinstance(kw.value, ast.Constant):
                        names.append(kw.value.value)
                    # fall back to id if no title
                    elif kw.arg == "id" and isinstance(kw.value, ast.Constant):
                        if kw.value.value not in names:
                            names.append(kw.value.value)

    return names


def _ast_extract_dispatch_agent_types(tree: ast.Module) -> list[str]:
    """Find agent_type / agentType / role strings in the old orchestrator.

    Searches for keyword argument ``agent_type=`` or string constants like
    ``"general-purpose"``, ``"explorer"``, ``"haiku"`` etc that appear next
    to dispatch calls.
    """
    types: list[str] = []
    seen: set[str] = set()
    _KNOWN_ROLE_VALUES = {
        "general-purpose", "explorer", "haiku", "architect",
        "developer", "technical-writer", "quality-reviewer",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in ("agent_type", "agentType", "role") and isinstance(
                    kw.value, ast.Constant
                ):
                    v = kw.value.value
                    if v not in seen:
                        seen.add(v)
                        types.append(v)

        # Also capture string literals matching known roles
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in _KNOWN_ROLE_VALUES and node.value not in seen:
                seen.add(node.value)
                types.append(node.value)

    return types


def _ast_extract_output_keys(tree: ast.Module, source: str) -> list[str]:
    """Best-effort extraction of the orchestrator's declared output schema keys.

    Searches for:
    - Workflow step dicts whose title contains "synthesize" / "output"
    - Explicit "output_keys" / "OUTPUT_KEYS" assignments
    - Pattern-matching against known per-skill output conventions in source text
    """
    keys: list[str] = []

    # Check for explicit output key assignments in the source (regex fallback)
    for match in re.finditer(
        r'"(synthesis|work_items|plan|styled_content|markdown|optimized_prompt|verdicts|report)"',
        source,
    ):
        k = match.group(1)
        if k not in keys:
            keys.append(k)

    return keys


def extract_python_structure(skill: str, ref: str = "0a2a9ac") -> dict:
    """Recover the old Python orchestrator at git ref and extract its structure.

    Parameters
    ----------
    skill:
        Skill slug, e.g. ``"codebase-analysis"``.
    ref:
        Git ref where the Python skills are intact.  Default: ``"0a2a9ac"``
        (parent of the deletion commit ``afcb1ac``).

    Returns
    -------
    dict with keys:
        steps, step_count, dispatch_agent_types, output_keys

    Notes
    -----
    Uses ``git show`` + Python ``ast`` to parse the source WITHOUT importing it
    (the old modules depend on deleted shared libs, so import would fail).
    """
    source = _git_show_source(skill, ref)
    if source is None:
        return {
            "steps": [],
            "step_count": 0,
            "dispatch_agent_types": [],
            "output_keys": [],
            "error": f"git show failed for skill={skill!r} ref={ref!r}",
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "steps": [],
            "step_count": 0,
            "dispatch_agent_types": [],
            "output_keys": [],
            "error": f"AST parse error: {exc}",
        }

    # --- step count ---
    total_steps = _ast_extract_total_steps(tree, source)

    # --- step names ---
    step_names = _ast_extract_step_names(tree)

    # --- dispatch agent types ---
    agent_types = _ast_extract_dispatch_agent_types(tree)

    # --- output keys ---
    output_keys = _ast_extract_output_keys(tree, source)

    # If TOTAL_STEPS wasn't found as an assignment, derive from step names count
    if total_steps is None and step_names:
        total_steps = len(step_names)

    # For scope-branching skills (prompt_engineer), grab from SCOPE_TOTAL_STEPS
    if total_steps is None:
        for match in re.finditer(r'SCOPE_TOTAL_STEPS\s*=\s*\{([^}]+)\}', source):
            nums = re.findall(r':\s*(\d+)', match.group(1))
            if nums:
                total_steps = max(int(n) for n in nums)
                break

    # Fallback: extract from module-level docstring "N-step workflow" pattern
    # Handles e.g. "14-step planning workflow" in the planner
    if total_steps is None or total_steps == 0:
        for match in re.finditer(r'(\d+)-step\s+\w+\s*workflow', source[:2000]):
            total_steps = int(match.group(1))
            break

    return {
        "steps": step_names,
        "step_count": total_steps or 0,
        "dispatch_agent_types": agent_types,
        "output_keys": output_keys,
    }
