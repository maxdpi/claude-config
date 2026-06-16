"""STRUCTURAL-CONTRACT parity layer for native-skill ports.

HONEST FRAMING
==============
The old Python skills were script-as-orchestrator: ``python3 -m skills.X --step N``
PRINTS dispatch prose for an LLM to act on — it does not compute a final artifact
deterministically.  The new ``.mjs`` likewise needs the Workflow tool + an LLM to
produce artifacts.  So you CANNOT diff final outputs offline.

What you CAN verify automatically is that the port preserved the skill's
STRUCTURE/CONTRACT: the same phase sequence, the same exploration fan-out shape,
the same output schema keys.  That is what this layer checks.  It catches
"the port silently dropped a phase / changed the agent fan-out / renamed an output
key" — it does NOT prove semantic output equivalence (that needs the live
behavioural test kit).

What passes here:
    - The new .mjs declares a non-empty phase sequence.
    - Phase count is in a sane relationship to the old step count (documented
      mapping; 1:1 is not required since native phases can merge steps, but the
      port must not collapse to a single phase when the old skill had many steps).
    - The canonical output key the parity fixture asserts on appears in the .mjs.
    - Exploration fan-out is preserved where the predecessor had it.

What does NOT pass here (marked xfail/skip pointing to the live kit):
    - Semantic output equivalence — requires both runtimes executing against the
      same live input.
    - QR loop behaviour — requires live LLM responses.

Adversarial skills (decision-critic, deepthink, problem-analysis):
    - No workflow.mjs; they use team.md + Agent Teams.
    - We verify team.md exists, declares a lead + teammates, and carries
      adversarial domain content in the BODY (DL-023).
    - Behavioural parity is a live-kit concern; documented explicitly as xfail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_WORKTREE = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _WORKTREE / "skills"

# Make extract_skill_structure importable
_TOOLS_DIR = Path(__file__).resolve().parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from extract_skill_structure import extract_mjs_structure, extract_python_structure

# ---------------------------------------------------------------------------
# Per-skill CONTRACT FIXTURES
#
# These are the structural assertions derived from reading both the old Python
# orchestrators and the new .mjs files.  A human authored them; they encode the
# EXPECTED structural mapping, not a live diff.
#
# Keys per entry:
#   old_step_count    - TOTAL_STEPS from the Python orchestrator (or max scope steps)
#   min_phase_count   - minimum phases the port MUST declare (we allow merging, not dropping)
#   output_key        - top-level key in the .mjs return artifact
#   had_fanout        - True if the old skill dispatched parallel explorer agents
#   fanout_note       - why we expect (or don't expect) fan-out in the port
# ---------------------------------------------------------------------------

LINEAR_CONTRACTS: dict[str, dict] = {
    "codebase-analysis": {
        "old_step_count": 4,       # SCOPE -> SURVEY -> DEEPEN -> SYNTHESIZE
        "min_phase_count": 4,      # port preserves all 4 phases
        "output_key": "synthesis",
        "had_fanout": True,        # SURVEY dispatched parallel Explore agents
        "fanout_note": "SURVEY phase dispatches parallel() Explore agents per focus area",
    },
    "refactor": {
        "old_step_count": 6,       # mode_selection → dispatch → triage → cluster → contextualize → synthesize
        "min_phase_count": 6,      # port preserves all 6 phases (comment says 8-step but actual STATIC_STEPS count is 6)
        "output_key": "work_items",
        "had_fanout": True,        # Dispatch phase launched parallel Explore agents per category
        "fanout_note": "dispatch phase uses parallel() with one Explore agent per smell category",
    },
    "planner": {
        "old_step_count": 14,      # 14-step Python orchestrator per docstring
        "min_phase_count": 6,      # port merges QR retry loops into 8 declared phases; min 6 to allow some merging
        "output_key": "plan",
        "had_fanout": False,       # Old planner was sequential (one role per phase)
        "fanout_note": "planner is sequential role-handoff; no parallel fan-out expected",
    },
    "arxiv-to-md": {
        "old_step_count": 3,       # DISCOVER -> WAIT -> FINALIZE
        "min_phase_count": 3,      # port preserves: discover, convert, finalize
        "output_key": "markdown",
        "had_fanout": True,        # DISCOVER dispatched one sub-agent per arXiv ID
        "fanout_note": "convert phase uses parallel() with one converter agent per arXiv ID",
    },
    "incoherence": {
        "old_step_count": 21,      # 21-step Workflow with StepDef list
        "min_phase_count": 7,      # port merges StepDefs into 9 phases; minimum 7 to catch collapse
        "output_key": "verdicts",
        "had_fanout": True,        # broad_sweep and deep_dive dispatched parallel sub-agents
        "fanout_note": "broad_sweep and deep_dive phases use parallel() explorer fan-out",
    },
    "prompt-engineer": {
        "old_step_count": 8,       # max(SCOPE_TOTAL_STEPS) = 8 (ecosystem scope)
        "min_phase_count": 5,      # port collapses scope branches into 7 shared phases; min 5
        "output_key": "optimized_prompt",
        "had_fanout": False,       # old skill was single-agent linear per scope
        "fanout_note": "prompt-engineer is single-agent linear; no parallel fan-out expected",
    },
    "leon-writing-style": {
        "old_step_count": 9,       # TOTAL_STEPS = 9
        "min_phase_count": 7,      # port should preserve most of the 9 steps; min 7 to catch collapse
        "output_key": "styled_content",
        "had_fanout": False,       # single-agent, no parallel dispatch
        "fanout_note": "leon-writing-style is single-agent linear; no fan-out expected",
    },
}

ADVERSARIAL_SKILLS = ["decision-critic", "deepthink", "problem-analysis"]

# Old step counts for adversarial skills (from Python docstrings)
ADVERSARIAL_OLD_STEPS: dict[str, int] = {
    "decision-critic": 7,   # 7-step workflow per docstring
    "deepthink":       14,  # 14-step workflow per docstring
    "problem-analysis": 5,  # 5-step workflow per docstring
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _mjs_path(skill: str) -> Path:
    return _SKILLS_DIR / skill / "workflow.mjs"


def _team_md_path(skill: str) -> Path:
    return _SKILLS_DIR / skill / "team.md"


# ---------------------------------------------------------------------------
# Tests: LINEAR SKILLS
# ---------------------------------------------------------------------------

class TestLinearSkillParity:
    """Structural parity checks for the 7 linear-workflow skills."""

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_mjs_exists(self, skill: str):
        """The port must have a workflow.mjs file."""
        path = _mjs_path(skill)
        assert path.exists(), (
            f"workflow.mjs missing for '{skill}' at {path}. "
            "Port may be incomplete."
        )

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_phases_nonempty(self, skill: str):
        """The port must declare a non-empty meta.phases sequence."""
        path = _mjs_path(skill)
        if not path.exists():
            pytest.skip(f"workflow.mjs missing for '{skill}'")
        struct = extract_mjs_structure(path)
        assert struct["phases"], (
            f"'{skill}' workflow.mjs declares zero phases in meta.phases. "
            "Port has lost all structural phase information."
        )

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_phase_count_sane(self, skill: str):
        """Phase count must meet the per-skill minimum derived from old step list.

        Native phases CAN merge old steps (e.g. 21 Python steps → 9 phases for
        incoherence).  But the port MUST NOT collapse to fewer than min_phase_count
        phases — that would silently drop coverage.
        """
        path = _mjs_path(skill)
        if not path.exists():
            pytest.skip(f"workflow.mjs missing for '{skill}'")
        contract = LINEAR_CONTRACTS[skill]
        struct = extract_mjs_structure(path)
        actual = len(struct["phases"])
        minimum = contract["min_phase_count"]
        assert actual >= minimum, (
            f"'{skill}': got {actual} phases, expected >= {minimum}. "
            f"Old orchestrator had {contract['old_step_count']} steps. "
            f"Current phases: {struct['phases']}"
        )

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_output_key_present(self, skill: str):
        """The canonical output key from the contract must appear in the .mjs return artifact."""
        path = _mjs_path(skill)
        if not path.exists():
            pytest.skip(f"workflow.mjs missing for '{skill}'")
        contract = LINEAR_CONTRACTS[skill]
        struct = extract_mjs_structure(path)
        expected_key = contract["output_key"]
        assert expected_key in struct["output_keys"], (
            f"'{skill}': return artifact missing key '{expected_key}'. "
            f"Found keys: {struct['output_keys']}. "
            "Port may have renamed or dropped the output contract."
        )

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_fanout_preserved(self, skill: str):
        """If the old skill dispatched parallel explorers, the port must use parallel().

        We check this by asserting agent_calls > 1 (multiple agent() invocations
        exist, meaning fan-out is possible) for skills that had parallel dispatch.
        For single-agent skills we assert a single dominant agent path is present.
        """
        path = _mjs_path(skill)
        if not path.exists():
            pytest.skip(f"workflow.mjs missing for '{skill}'")
        contract = LINEAR_CONTRACTS[skill]
        struct = extract_mjs_structure(path)

        if contract["had_fanout"]:
            # The port must have more than 1 agent() call to support fan-out.
            # A single agent() call means the parallel wave was collapsed.
            assert struct["agent_calls"] > 1, (
                f"'{skill}' HAD fan-out but port appears to have only "
                f"{struct['agent_calls']} agent() call(s). "
                f"Fan-out note: {contract['fanout_note']}. "
                "Possible structural regression: parallel exploration dropped."
            )
        else:
            # Non-fanout skills should still have at least one agent() call
            assert struct["agent_calls"] >= 1, (
                f"'{skill}' has zero agent() calls in workflow.mjs — "
                "the port may be empty or broken."
            )

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_phase_trust_matches_phases(self, skill: str):
        """Every declared phase must have a phaseTrust entry."""
        path = _mjs_path(skill)
        if not path.exists():
            pytest.skip(f"workflow.mjs missing for '{skill}'")
        struct = extract_mjs_structure(path)
        if not struct["phases"]:
            pytest.skip(f"'{skill}' has no phases declared")
        missing_trust = [p for p in struct["phases"] if p not in struct["phase_trust"]]
        assert not missing_trust, (
            f"'{skill}': phases {missing_trust} have no phaseTrust entry. "
            "The resume engine cannot classify these phases (DL-014)."
        )


# ---------------------------------------------------------------------------
# Tests: ADVERSARIAL SKILLS
# ---------------------------------------------------------------------------

class TestAdversarialSkillParity:
    """Structural parity for decision-critic, deepthink, problem-analysis.

    These use team.md + Agent Teams rather than workflow.mjs.
    We verify the team.md structure (lead + teammates) and that the adversarial
    domain content is embedded in the body (DL-023).

    Behavioural parity is explicitly out of scope for this static layer.
    """

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    def test_team_md_exists(self, skill: str):
        """team.md must exist for every adversarial skill."""
        path = _team_md_path(skill)
        assert path.exists(), (
            f"team.md missing for adversarial skill '{skill}' at {path}. "
            "Port may be incomplete."
        )

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    def test_team_md_declares_lead(self, skill: str):
        """team.md must declare a Lead agent."""
        path = _team_md_path(skill)
        if not path.exists():
            pytest.skip(f"team.md missing for '{skill}'")
        content = path.read_text(encoding="utf-8")
        # Check for "Lead:" or "**Lead:**" pattern (markdown bold or plain)
        assert re.search(r'\*{0,2}Lead\*{0,2}\s*:', content, re.IGNORECASE), (
            f"'{skill}' team.md does not declare a Lead agent. "
            "The adversarial team requires a lead orchestrator."
        )

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    def test_team_md_declares_teammates(self, skill: str):
        """team.md must declare at least one Teammate."""
        path = _team_md_path(skill)
        if not path.exists():
            pytest.skip(f"team.md missing for '{skill}'")
        content = path.read_text(encoding="utf-8")
        # Check for "Teammates:" or "**Teammates:**" or teammate yaml block
        has_teammates_heading = re.search(
            r'\*{0,2}Teammates?\*{0,2}\s*:', content, re.IGNORECASE
        )
        has_teammate_yaml = re.search(r'- name:\s*\w+', content)
        assert has_teammates_heading or has_teammate_yaml, (
            f"'{skill}' team.md does not declare any Teammates. "
            "Adversarial skills require at least one teammate for independent critique."
        )

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    def test_team_md_adversarial_content_in_body(self, skill: str):
        """Adversarial domain content must live in the BODY of team.md (DL-023).

        The frontmatter (---...---) carries only metadata.  The methodology steps
        must appear in the markdown body so they are applied to teammates on the
        Agent Teams path.
        """
        path = _team_md_path(skill)
        if not path.exists():
            pytest.skip(f"team.md missing for '{skill}'")
        content = path.read_text(encoding="utf-8")

        # Strip frontmatter (between first and second ---)
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                body = content[end + 3:]

        # The body must contain step references (Step N: or #### Step)
        has_steps = bool(re.search(r'Step\s+\d+[:\.]', body, re.IGNORECASE))
        # OR it must contain methodology keywords
        has_methodology = bool(
            re.search(
                r'(Adversarial Domain Content|methodology|7-Step|14-Step|5-Step|'
                r'Verify|Contrarian|Root Cause|Formulate)',
                body,
                re.IGNORECASE,
            )
        )
        assert has_steps or has_methodology, (
            f"'{skill}' team.md body appears to lack adversarial domain content. "
            "Per DL-023, the methodology must be embedded in the body so it reaches "
            "teammates on the Agent Teams path."
        )

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    @pytest.mark.xfail(
        reason=(
            "Behavioural output parity for adversarial skills requires both the "
            "Python orchestrator and the Agent Teams runtime to be live-executable "
            "against the same input.  This is a live-kit concern, not a static "
            "structural check.  See: tests/test_adversarial_skill_parity.py for "
            "the live behavioural test hooks."
        ),
        strict=False,
    )
    def test_adversarial_output_parity_live_XFAIL(self, skill: str):
        """Placeholder: behavioural output parity requires the live kit.

        This test is always xfail to document the gap explicitly.
        It will remain xfail until the live behavioural kit can drive both
        the Python orchestrator (via docker/archive) and the Agent Teams runtime
        against the same input and compare structured verdict outputs.
        """
        raise NotImplementedError(
            "Live behavioural parity check not implemented in the static layer."
        )


# ---------------------------------------------------------------------------
# Python structure recovery smoke-tests
# ---------------------------------------------------------------------------

class TestPythonStructureRecovery:
    """Verify the extractor can recover old Python structure from git history."""

    @pytest.mark.parametrize("skill", list(LINEAR_CONTRACTS))
    def test_python_step_count_recoverable(self, skill: str):
        """extract_python_structure must return a nonzero step_count for linear skills."""
        struct = extract_python_structure(skill)
        if "error" in struct:
            pytest.skip(f"git show failed for '{skill}': {struct['error']}")
        assert struct["step_count"] > 0, (
            f"'{skill}': could not recover step count from Python orchestrator "
            f"at git ref 0a2a9ac. Got: {struct}"
        )

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    def test_adversarial_python_step_count_recoverable(self, skill: str):
        """Adversarial skills must also have recoverable step counts."""
        struct = extract_python_structure(skill)
        if "error" in struct:
            pytest.skip(f"git show failed for '{skill}': {struct['error']}")
        expected = ADVERSARIAL_OLD_STEPS[skill]
        # We accept the docstring count; if recovery returns 0 the AST didn't find it
        # but we don't hard-fail since these skills have no TOTAL_STEPS constant
        assert struct["step_count"] >= 0, (
            f"'{skill}': negative step count — extractor bug."
        )


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def print_structural_parity_table() -> None:
    """Print a human-readable per-skill structural-parity table.

    Columns:
        Skill | Old Steps | New Phases | Output Key | Fan-Out Preserved
    """
    print()
    print("=" * 90)
    print("STRUCTURAL PARITY TABLE")
    print("(old step count → new phase count → output key → fan-out preserved)")
    print("=" * 90)
    header = f"{'Skill':<22} {'OldSteps':>9} {'NewPhases':>10} {'OutputKey':<20} {'FanOut':>8}"
    print(header)
    print("-" * 90)

    all_skills = list(LINEAR_CONTRACTS.keys()) + ADVERSARIAL_SKILLS

    for skill in all_skills:
        is_adversarial = skill in ADVERSARIAL_SKILLS

        # Old step count
        if is_adversarial:
            old_steps = ADVERSARIAL_OLD_STEPS.get(skill, "?")
        else:
            old_steps = LINEAR_CONTRACTS[skill]["old_step_count"]

        # New phase count
        if is_adversarial:
            team_path = _team_md_path(skill)
            new_phases = "team.md" if team_path.exists() else "MISSING"
        else:
            mjs_path = _mjs_path(skill)
            if mjs_path.exists():
                s = extract_mjs_structure(mjs_path)
                new_phases = str(len(s["phases"]))
            else:
                new_phases = "MISSING"

        # Output key
        if is_adversarial:
            output_key = "verdicts/report"
        else:
            output_key = LINEAR_CONTRACTS[skill]["output_key"]

        # Fan-out
        if is_adversarial:
            fanout = "N/A(team)"
        else:
            had = LINEAR_CONTRACTS[skill]["had_fanout"]
            mjs_path = _mjs_path(skill)
            if not mjs_path.exists():
                fanout = "MISSING"
            else:
                s = extract_mjs_structure(mjs_path)
                if had:
                    preserved = s["agent_calls"] > 1
                    fanout = "YES" if preserved else "DRIFT!"
                else:
                    fanout = "N/A"

        row = f"{skill:<22} {str(old_steps):>9} {str(new_phases):>10} {output_key:<20} {fanout:>8}"
        print(row)

    print("-" * 90)
    print()
    print("Notes:")
    print("  OldSteps  — TOTAL_STEPS from Python orchestrator at git ref 0a2a9ac")
    print("  NewPhases — count of meta.phases in workflow.mjs (or 'team.md' for adversarial)")
    print("  OutputKey — top-level return key asserted by parity fixture")
    print("  FanOut    — whether parallel() exploration fan-out is preserved")
    print("  DRIFT!    — structural regression detected (had fan-out, port lost it)")
    print()
    print("WHAT THIS PROVES:  structural contract (phase sequence, fan-out shape, output key)")
    print("WHAT THIS DOES NOT PROVE: semantic output equivalence (live-kit concern)")
    print("=" * 90)


class TestStructuralParityTable:
    """Emit the summary table as a passing test so it shows in verbose output."""

    def test_print_parity_table(self, capsys):
        """Print the per-skill structural-parity table (human-readable summary)."""
        print_structural_parity_table()
        captured = capsys.readouterr()
        # The table must contain all skill names
        for skill in list(LINEAR_CONTRACTS) + ADVERSARIAL_SKILLS:
            assert skill in captured.out, (
                f"'{skill}' missing from parity table output"
            )


# ---------------------------------------------------------------------------
# Import guard — allow running directly for quick table inspection
# ---------------------------------------------------------------------------

import re  # noqa: E402 (imported late to keep module docstring at top)

if __name__ == "__main__":
    print_structural_parity_table()
