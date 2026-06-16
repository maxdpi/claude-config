#!/usr/bin/env python3
"""Static integrity tests for the native-runtime migration.

No live LLM or session required. Pure structural checks that codify
manual verification done during the migration of 10 skills from
the deleted Python --step runtime to native runtimes:

  Linear (7):     skills/<name>/workflow.mjs  (Workflow tool)
  Adversarial (3): skills/<name>/team.md      (Agent Teams)

Non-ported (excluded from #1/#2): cc-history, doc-sync.
"""
from __future__ import annotations

import compileall
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SCRIPTS = REPO / "skills" / "scripts"
SETTINGS = REPO / "settings.json"
FIXTURES = REPO / "tests" / "fixtures"

# Ensure skills/scripts is importable for #5 and #6
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# ---------------------------------------------------------------------------
# Skill classifications
# ---------------------------------------------------------------------------
LINEAR_SKILLS = [
    "arxiv-to-md",
    "codebase-analysis",
    "incoherence",
    "leon-writing-style",
    "planner",
    "prompt-engineer",
    "refactor",
]

ADVERSARIAL_SKILLS = [
    "decision-critic",
    "deepthink",
    "problem-analysis",
]

PORTED_SKILLS = LINEAR_SKILLS + ADVERSARIAL_SKILLS

# Skills still on Python — excluded from ported-skill assertions
EXCLUDED_SKILLS = {"cc-history", "doc-sync"}


# ===========================================================================
# Test 1: No ported SKILL.md invokes a deleted --step CLI
# ===========================================================================
class TestNoStepCLIInSkillMd:
    """Assert SKILL.md files for ported skills contain no --step / python3 -m orchestration."""

    DELETED_PATTERNS = [
        re.compile(r"--step"),
        re.compile(r"python3\s+-m\s+skills\."),
    ]

    @pytest.mark.parametrize("skill", PORTED_SKILLS)
    def test_no_step_invocation(self, skill: str) -> None:
        skill_md = SKILLS / skill / "SKILL.md"
        assert skill_md.exists(), f"SKILL.md missing for ported skill: {skill}"
        text = skill_md.read_text(encoding="utf-8")
        for pat in self.DELETED_PATTERNS:
            match = pat.search(text)
            assert match is None, (
                f"{skill}/SKILL.md still references deleted CLI pattern "
                f"'{pat.pattern}' at: {match.group()!r}"
            )


# ===========================================================================
# Test 2: Each ported skill names its native runtime in SKILL.md
# ===========================================================================
class TestNativeRuntimeReference:
    """Linear skills must mention workflow.mjs/Workflow tool; adversarial mention team.md/Agent Team."""

    @pytest.mark.parametrize("skill", LINEAR_SKILLS)
    def test_linear_skill_references_workflow(self, skill: str) -> None:
        skill_md = SKILLS / skill / "SKILL.md"
        assert skill_md.exists(), f"SKILL.md missing for {skill}"
        text = skill_md.read_text(encoding="utf-8")
        assert re.search(r"workflow\.mjs|Workflow tool|Workflow Tool", text), (
            f"{skill}/SKILL.md must reference 'workflow.mjs' or 'Workflow tool'"
        )

    @pytest.mark.parametrize("skill", ADVERSARIAL_SKILLS)
    def test_adversarial_skill_references_team(self, skill: str) -> None:
        skill_md = SKILLS / skill / "SKILL.md"
        assert skill_md.exists(), f"SKILL.md missing for {skill}"
        text = skill_md.read_text(encoding="utf-8")
        assert re.search(r"team\.md|Agent Team|Agent Teams", text), (
            f"{skill}/SKILL.md must reference 'team.md' or 'Agent Team(s)'"
        )


# ===========================================================================
# Test 3: Every skills/*/workflow.mjs is syntactically valid
# ===========================================================================
class TestWorkflowMjsSyntax:
    """Validate each workflow.mjs in the WORKFLOW-TOOL DIALECT.

    A workflow.mjs is NOT a plain ES module: it is `export const meta = {...}`
    followed by a BARE body (top-level await/return, injected globals like
    phase()/agent()). Raw `node --check` is the WRONG validator here -- top-level
    `return` (the artifact) is illegal in a module, so node --check would reject
    the correct form. We validate the body by wrapping it in an async function.

    REGRESSION GUARD (S2, 2026-06-16): the ports were originally written with an
    `export async function run() {...}` wrapper to satisfy a naive `node --check`
    -- but the Workflow tool rejects any `export` beyond meta ("Unexpected keyword
    'export'") and the skills failed to launch. test_no_export_after_meta below
    pins the bare-body form so the wrapper can never come back.
    """

    _node = shutil.which("node")

    @staticmethod
    def _wrap_for_check(text: str) -> str:
        # Drop the single `export` on meta, wrap the rest in an async function so
        # the top-level `return` (the artifact) becomes valid for a syntax check.
        return "async function __wf(){\n" + text.replace("export const meta", "const meta", 1) + "\n}\n"

    @pytest.mark.parametrize(
        "mjs",
        [pytest.param(p, id=p.parent.name) for p in sorted(SKILLS.glob("*/workflow.mjs"))],
    )
    def test_body_valid_in_workflow_context(self, mjs: Path, tmp_path: Path) -> None:
        if self._node is None:
            pytest.skip("node not found on PATH — install Node.js to enable MJS syntax checks")
        probe = tmp_path / "probe.mjs"
        probe.write_text(self._wrap_for_check(mjs.read_text(encoding="utf-8")), encoding="utf-8")
        result = subprocess.run([self._node, "--check", str(probe)], capture_output=True, text=True)
        assert result.returncode == 0, (
            f"workflow.mjs body is not valid JS in the Workflow async context for "
            f"{mjs.relative_to(REPO)}:\n{result.stderr}"
        )

    @pytest.mark.parametrize(
        "mjs",
        [pytest.param(p, id=p.parent.name) for p in sorted(SKILLS.glob("*/workflow.mjs"))],
    )
    def test_meta_export_present(self, mjs: Path) -> None:
        text = mjs.read_text(encoding="utf-8")
        assert "export const meta = {" in text, (
            f"{mjs.relative_to(REPO)} must begin with 'export const meta = {{'"
        )

    @pytest.mark.parametrize(
        "mjs",
        [pytest.param(p, id=p.parent.name) for p in sorted(SKILLS.glob("*/workflow.mjs"))],
    )
    def test_no_export_after_meta(self, mjs: Path) -> None:
        """The Workflow tool rejects any `export` beyond `export const meta` --
        the body must be bare, NEVER wrapped in `export function run()` (S2 bug)."""
        text = mjs.read_text(encoding="utf-8")
        rest = text.replace("export const meta", "", 1)  # drop the one allowed export
        stray = re.search(r"\bexport\b", rest)
        assert stray is None, (
            f"{mjs.relative_to(REPO)}: found a second 'export' (e.g. a run() wrapper). "
            "The Workflow tool requires a BARE body after 'export const meta' "
            "(top-level await/return), not 'export function run()'."
        )
        # And no run() wrapper of any kind.
        assert re.search(r"\bfunction\s+run\b", text) is None, (
            f"{mjs.relative_to(REPO)}: contains a 'function run' wrapper -- the body "
            "must be top-level (bare) for the Workflow tool."
        )

    @pytest.mark.parametrize(
        "mjs",
        [pytest.param(p, id=p.parent.name) for p in sorted(SKILLS.glob("*/workflow.mjs"))],
    )
    def test_bare_body_uses_injected_globals(self, mjs: Path) -> None:
        text = mjs.read_text(encoding="utf-8")
        assert "phases" in text and re.search(r"\bphase\(", text) and re.search(r"\bagent\(", text), (
            f"{mjs.relative_to(REPO)} must declare meta.phases and call phase()/agent() "
            "in its bare body"
        )

    def test_check_mjs_syntax_script_passes(self) -> None:
        """The standalone check_mjs_syntax.sh script must exit 0 when node is present."""
        script = REPO / "tests" / "tools" / "check_mjs_syntax.sh"
        assert script.exists(), "tests/tools/check_mjs_syntax.sh is missing"
        assert os.access(script, os.X_OK), "check_mjs_syntax.sh is not executable"
        if self._node is None:
            pytest.skip("node not found on PATH")
        result = subprocess.run([str(script)], capture_output=True, text=True)
        assert result.returncode == 0, (
            f"check_mjs_syntax.sh exited {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )


# ===========================================================================
# Test 4: No surviving Python imports a deleted symbol
# ===========================================================================
class TestNoDeletedSymbolImports:
    """grep skills/scripts/ for imports of deleted modules/symbols; assert zero matches."""

    # Patterns that unambiguously reference deleted code
    DELETED_MODULE_PATTERNS = [
        # Deleted Python modules
        r"skills\.lib\.workflow\.cli",
        r"prompts\.subagent",
        # Deleted AST sub-package — must NOT match stdlib `ast` imports
        r"skills\.lib\.workflow\.ast",
        # Deleted dispatch symbols
        r"\broster_dispatch\b",
        r"\btask_tool_instruction\b",
        r"\bparallel_constraint\b",
        r"\brender_subagent_dispatch\b",
        r"\bSubagentDispatchNode\b",
    ]

    @pytest.mark.parametrize("pattern", DELETED_MODULE_PATTERNS)
    def test_no_deleted_import(self, pattern: str) -> None:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", pattern, str(SCRIPTS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0 or result.stdout.strip() == "", (
            f"Found reference to deleted symbol '{pattern}':\n{result.stdout}"
        )

    def test_no_workflow_ast_import_distinct_from_stdlib(self) -> None:
        """Confirm skills.lib.workflow.ast (deleted subpackage) is distinct from stdlib ast."""
        # stdlib `import ast` is fine; `from skills.lib.workflow.ast` is not
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", r"from.*workflow.*ast\|import.*workflow.*ast", str(SCRIPTS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0 or result.stdout.strip() == "", (
            f"Found import of deleted workflow.ast subpackage:\n{result.stdout}"
        )


# ===========================================================================
# Test 5: prompts/__init__.py exposes only the survivors
# ===========================================================================
class TestPromptsPackageExports:
    """skills.lib.workflow.prompts must export exactly format_step + format_file_content."""

    def test_prompts_importable(self) -> None:
        try:
            import skills.lib.workflow.prompts as prompts  # noqa: F401
        except ImportError as exc:
            pytest.fail(f"skills.lib.workflow.prompts failed to import: {exc}")

    def test_prompts_exports_exactly_survivors(self) -> None:
        import skills.lib.workflow.prompts as prompts

        exported = set(getattr(prompts, "__all__", []))
        expected = {"format_step", "format_file_content"}
        assert exported == expected, (
            f"prompts.__all__ = {exported!r}; expected exactly {expected!r}"
        )

    def test_prompts_no_subagent_reexport(self) -> None:
        import skills.lib.workflow.prompts as prompts

        assert not hasattr(prompts, "render_subagent_dispatch"), (
            "prompts still re-exports render_subagent_dispatch (deleted symbol)"
        )
        assert not hasattr(prompts, "SubagentDispatchNode"), (
            "prompts still re-exports SubagentDispatchNode (deleted symbol)"
        )


# ===========================================================================
# Test 6: All persistence modules import cleanly + compileall is clean
# ===========================================================================
class TestPersistenceModulesClean:
    """Each persistence submodule must import without errors; compileall must pass."""

    _PERSISTENCE_PKG = "skills.lib.workflow.persistence"

    @staticmethod
    def _persistence_submodule_names() -> list[str]:
        persistence_dir = SCRIPTS / "skills" / "lib" / "workflow" / "persistence"
        names = []
        for py in sorted(persistence_dir.glob("*.py")):
            if py.name == "__init__.py":
                continue
            stem = py.stem
            names.append(f"skills.lib.workflow.persistence.{stem}")
        return names

    @pytest.mark.parametrize(
        "modname",
        _persistence_submodule_names.__func__(),  # type: ignore[attr-defined]
    )
    def test_persistence_submodule_imports(self, modname: str) -> None:
        try:
            importlib.import_module(modname)
        except ImportError as exc:
            pytest.fail(f"{modname} failed to import: {exc}")

    def test_compileall_skills_lib(self) -> None:
        skills_lib = SCRIPTS / "skills" / "lib"
        ok = compileall.compile_dir(str(skills_lib), quiet=2, force=False)
        assert ok, f"compileall reported errors in {skills_lib}"

    def test_compileall_skills_hooks(self) -> None:
        skills_hooks = SCRIPTS / "skills" / "hooks"
        ok = compileall.compile_dir(str(skills_hooks), quiet=2, force=False)
        assert ok, f"compileall reported errors in {skills_hooks}"


# ===========================================================================
# Test 7: JSON validity and hook event-key presence
# ===========================================================================
class TestJsonValidity:
    """settings.json and all fixture JSON files must parse; required hook keys must be present."""

    REQUIRED_HOOK_EVENTS = [
        "SessionStart",
        "Stop",
        "SessionEnd",
        "SubagentStart",
        "SubagentStop",
        "TaskCreated",
        "TaskCompleted",
        "TeammateIdle",
    ]

    def test_settings_json_parses(self) -> None:
        try:
            data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(f"settings.json is not valid JSON: {exc}")
        assert isinstance(data, dict), "settings.json root must be a JSON object"

    def test_settings_hooks_has_required_events(self) -> None:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {})
        assert isinstance(hooks, dict), "settings.json 'hooks' must be an object"
        missing = [ev for ev in self.REQUIRED_HOOK_EVENTS if ev not in hooks]
        assert not missing, (
            f"settings.json 'hooks' is missing required event keys: {missing}"
        )

    @pytest.mark.parametrize(
        "fixture_path",
        [
            pytest.param(p, id=str(p.relative_to(FIXTURES)))
            for p in sorted(FIXTURES.glob("**/*.json"))
        ],
    )
    def test_fixture_json_parses(self, fixture_path: Path) -> None:
        try:
            json.loads(fixture_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(f"{fixture_path.relative_to(REPO)} is not valid JSON: {exc}")


# ===========================================================================
# Test 8: Parity-fixture honesty
# ===========================================================================
class TestFixtureFidelityField:
    """Every parity fixture must carry a _fixture_fidelity/_note field flagging it as hand-authored."""

    PARITY_DIRS = [
        FIXTURES / "workflow_port_parity",
        FIXTURES / "adversarial_skill_parity",
    ]

    @pytest.mark.parametrize(
        "fixture_path",
        [
            pytest.param(p, id=str(p.relative_to(FIXTURES)))
            for parity_dir in [
                FIXTURES / "workflow_port_parity",
                FIXTURES / "adversarial_skill_parity",
            ]
            for p in sorted(parity_dir.glob("*.json"))
            if parity_dir.exists()
        ],
    )
    def test_fixture_has_fidelity_field(self, fixture_path: Path) -> None:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        has_fidelity = "_fixture_fidelity" in data
        has_note = "_note" in data
        assert has_fidelity or has_note, (
            f"{fixture_path.relative_to(REPO)} must contain a '_fixture_fidelity' or '_note' "
            "field to flag it as hand-authored (not live-captured)"
        )

    @pytest.mark.parametrize(
        "fixture_path",
        [
            pytest.param(p, id=str(p.relative_to(FIXTURES)))
            for parity_dir in [
                FIXTURES / "workflow_port_parity",
                FIXTURES / "adversarial_skill_parity",
            ]
            for p in sorted(parity_dir.glob("*.json"))
            if parity_dir.exists()
        ],
    )
    def test_fixture_fidelity_field_is_non_empty(self, fixture_path: Path) -> None:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        fidelity_value = data.get("_fixture_fidelity") or data.get("_note", "")
        assert fidelity_value and str(fidelity_value).strip(), (
            f"{fixture_path.relative_to(REPO)}: '_fixture_fidelity'/'_note' must be a "
            "non-empty string describing the hand-authored nature of the fixture"
        )


# ===========================================================================
# Test 9: Hook safety (grep-level)
# ===========================================================================
class TestHookSafety:
    """No hooks/ or persistence/ file must WRITE to ~/.claude/teams or ~/.claude/tasks paths."""

    SEARCH_ROOTS = [
        SCRIPTS / "skills" / "hooks",
        SCRIPTS / "skills" / "lib" / "workflow" / "persistence",
    ]

    # Patterns that suggest a write/create operation targeting the protected dirs.
    # Reads (open(path, 'r'), path.exists(), os.listdir) are acceptable.
    WRITE_PATTERNS = [
        # open(... "w" / "a" / "x" / "wb" / "ab")
        r'open\s*\(.*["\']\.claude/(?:teams|tasks).*["\'][waWAxb]',
        # os.mkdir / os.makedirs targeting teams or tasks
        r'os\.(?:mkdir|makedirs)\s*\(.*\.claude/(?:teams|tasks)',
        # pathlib .mkdir() on a path containing teams or tasks
        r'\.claude/(?:teams|tasks).*\.mkdir\(',
        # shutil.copy/move/rmtree into teams or tasks
        r'shutil\.(?:copy|move|rmtree)\s*\(.*\.claude/(?:teams|tasks)',
        # Path.write_text/.write_bytes on teams or tasks
        r'\.claude/(?:teams|tasks).*\.write_(?:text|bytes)\(',
    ]

    @pytest.mark.parametrize("pattern", WRITE_PATTERNS)
    def test_no_write_to_teams_or_tasks(self, pattern: str) -> None:
        for root in self.SEARCH_ROOTS:
            if not root.exists():
                continue
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", pattern, str(root)],
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0 or result.stdout.strip() == "", (
                f"Hook/persistence code appears to WRITE inside ~/.claude/teams or "
                f"~/.claude/tasks (pattern: {pattern!r}):\n{result.stdout}"
            )

    def test_no_hardcoded_teams_path_write(self) -> None:
        """Broad check: no open()/write/mkdir call combines a teams/tasks path literal.

        The probe/ subdirectory is excluded — it is a diagnostic two-phase tool that
        intentionally plants marker files to verify directory ephemerality; it is not
        production hook or substrate code.
        """
        # Patterns that combine a write-mode Python call with the protected path
        combined_write_patterns = [
            # open(".../.claude/teams...", "w"/"a"/"x"/"wb"/"ab")
            r'open\s*\(.*\.claude/(?:teams|tasks).*["\'][waWAxb]',
            # os.mkdir/makedirs(".../.claude/teams...")
            r'os\.(?:mkdir|makedirs)\s*\(.*\.claude/(?:teams|tasks)',
            # Path(".../.claude/teams...").mkdir(...)
            r'\.claude/(?:teams|tasks).*\.mkdir\s*\(',
            # .write_text/.write_bytes on a teams/tasks path
            r'\.claude/(?:teams|tasks).*\.write_(?:text|bytes)\s*\(',
            # shutil.copy/move into teams or tasks
            r'shutil\.(?:copy2?|move)\s*\(.*\.claude/(?:teams|tasks)',
        ]
        for root in self.SEARCH_ROOTS:
            if not root.exists():
                continue
            # Exclude probe/ — it is a diagnostic tool, not production code
            probe_dir = root / "probe"
            for pattern in combined_write_patterns:
                result = subprocess.run(
                    ["grep", "-rn", "--include=*.py",
                     "--exclude-dir=probe", pattern, str(root)],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode != 0 or result.stdout.strip() == "", (
                    f"Hook/persistence code contains a write call targeting "
                    f"~/.claude/teams or ~/.claude/tasks (pattern: {pattern!r}):\n"
                    f"{result.stdout}"
                )
            _ = probe_dir  # referenced above; suppress unused-variable warning
