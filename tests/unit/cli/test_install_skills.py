"""Tests for --install-skills CLI command (D1 — First-Run Experience Pack).

RED-first tests written before the implementation.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# D1a — bundled skills exist inside the package at install time
# ---------------------------------------------------------------------------


class TestBundledSkillsPackage:
    def test_skills_dir_exists_in_package(self):
        """tree_sitter_analyzer/skills/ must exist as a package-level directory."""
        import tree_sitter_analyzer.skills as skills_pkg

        pkg_path = Path(skills_pkg.__file__).parent  # type: ignore[arg-type]
        assert pkg_path.is_dir()

    def test_exactly_13_tsa_skill_dirs(self):
        """Bundled skills dir must contain exactly 13 tsa-* subdirectories."""
        import tree_sitter_analyzer.skills as skills_pkg

        pkg_path = Path(skills_pkg.__file__).parent  # type: ignore[arg-type]
        tsa_dirs = [
            d for d in pkg_path.iterdir() if d.is_dir() and d.name.startswith("tsa-")
        ]
        assert len(tsa_dirs) == 13

    def test_each_skill_dir_has_skill_md(self):
        """Every bundled tsa-* dir must contain SKILL.md."""
        import tree_sitter_analyzer.skills as skills_pkg

        pkg_path = Path(skills_pkg.__file__).parent  # type: ignore[arg-type]
        for d in pkg_path.iterdir():
            if d.is_dir() and d.name.startswith("tsa-"):
                assert (d / "SKILL.md").is_file(), f"{d.name} missing SKILL.md"

    def test_known_skill_names_present(self):
        """Spot-check: the 13 expected skill names are all present."""
        import tree_sitter_analyzer.skills as skills_pkg

        pkg_path = Path(skills_pkg.__file__).parent  # type: ignore[arg-type]
        expected = {
            "tsa-constraints",
            "tsa-deps",
            "tsa-edit-safety",
            "tsa-edit-then-verify",
            "tsa-find",
            "tsa-graph",
            "tsa-health-watch",
            "tsa-index",
            "tsa-landing",
            "tsa-pr-review",
            "tsa-refactor-queue",
            "tsa-structure",
            "tsa-temporal",
        }
        found = {
            d.name
            for d in pkg_path.iterdir()
            if d.is_dir() and d.name.startswith("tsa-")
        }
        assert found == expected


# ---------------------------------------------------------------------------
# D1b — install_skills helper: copy, no-overwrite, idempotent
# ---------------------------------------------------------------------------


class TestInstallSkillsHelper:
    def test_install_copies_skills_to_target(self, tmp_path):
        """install_skills should copy all 13 dirs into target/.claude/skills/."""
        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "myproject"
        target.mkdir()
        report = install_skills(target_dir=target)

        installed = [
            d.name
            for d in (target / ".claude" / "skills").iterdir()
            if d.is_dir() and d.name.startswith("tsa-")
        ]
        assert len(installed) == 13
        assert report["installed_count"] == 13
        assert report["skipped_count"] == 0

    def test_install_global_uses_home_dot_claude(self, tmp_path, monkeypatch):
        """With global=True, target must be ~/.claude/skills/."""
        monkeypatch.setenv("HOME", str(tmp_path))
        from tree_sitter_analyzer.cli.install_skills import install_skills

        report = install_skills(target_dir=None, global_install=True)
        skills_dir = tmp_path / ".claude" / "skills"
        assert skills_dir.exists()
        installed = [
            d.name
            for d in skills_dir.iterdir()
            if d.is_dir() and d.name.startswith("tsa-")
        ]
        assert len(installed) == 13
        assert report["installed_count"] == 13

    def test_no_overwrite_existing_skill(self, tmp_path):
        """If a skill dir already exists, it must be skipped (not overwritten)."""
        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "proj"
        target.mkdir()
        existing_skill = target / ".claude" / "skills" / "tsa-index"
        existing_skill.mkdir(parents=True)
        sentinel = existing_skill / "MY_CUSTOMIZATION.md"
        sentinel.write_text("custom", encoding="utf-8")

        report = install_skills(target_dir=target)
        # Sentinel must survive — no overwrite
        assert sentinel.is_file()
        assert report["skipped_count"] == 1
        assert report["installed_count"] == 12

    def test_idempotent_second_run(self, tmp_path):
        """Running install_skills twice must skip all dirs on the second run."""
        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "proj"
        target.mkdir()
        install_skills(target_dir=target)
        report2 = install_skills(target_dir=target)
        assert report2["installed_count"] == 0
        assert report2["skipped_count"] == 13


# ---------------------------------------------------------------------------
# D1c — CLI flag wiring (--install-skills registered in argument parser)
# ---------------------------------------------------------------------------


class TestInstallSkillsCLIFlag:
    def test_install_skills_flag_exists_in_parser(self):
        """--install-skills must be registered in the argument parser."""
        from tree_sitter_analyzer.cli_main import create_argument_parser

        parser = create_argument_parser()
        flags = {
            s for a in parser._actions for s in a.option_strings if s.startswith("--")
        }
        assert "--install-skills" in flags

    def test_install_skills_global_flag_exists_in_parser(self):
        """--install-skills-global must be registered alongside --install-skills."""
        from tree_sitter_analyzer.cli_main import create_argument_parser

        parser = create_argument_parser()
        flags = {
            s for a in parser._actions for s in a.option_strings if s.startswith("--")
        }
        assert "--install-skills-global" in flags


# ---------------------------------------------------------------------------
# D1d — wheel proof: bundled skills reachable via installed-package path
# ---------------------------------------------------------------------------


class TestBundledSkillsWheelPath:
    """Verify bundled skills are reachable via the SKILLS_DIR constant that
    the runtime (install_skills._bundled_skills_dir) uses at install time.

    This test is the counterpart to the wheel-level ``unzip -l dist/*.whl |
    grep -c skills/tsa-`` smoke check.  It catches the case where SKILLS_DIR
    diverges from the actual on-disk location (e.g. after a packaging change).
    """

    def test_skills_dir_constant_matches_file_parent(self):
        """SKILLS_DIR in __init__.py must agree with __file__.parent."""
        from tree_sitter_analyzer import skills as skills_pkg

        skills_dir = Path(skills_pkg.SKILLS_DIR)
        file_parent = Path(skills_pkg.__file__).parent  # type: ignore[arg-type]
        assert skills_dir == file_parent

    def test_exactly_13_tsa_dirs_via_skills_dir(self):
        """SKILLS_DIR must contain exactly 13 tsa-* subdirectories."""
        from tree_sitter_analyzer import skills as skills_pkg

        skills_dir = Path(skills_pkg.SKILLS_DIR)
        tsa_dirs = [
            d for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith("tsa-")
        ]
        assert len(tsa_dirs) == 13

    def test_each_skill_has_skill_md_via_skills_dir(self):
        """Every tsa-* dir reachable via SKILLS_DIR must contain SKILL.md."""
        from tree_sitter_analyzer import skills as skills_pkg

        skills_dir = Path(skills_pkg.SKILLS_DIR)
        for d in skills_dir.iterdir():
            if d.is_dir() and d.name.startswith("tsa-"):
                assert (d / "SKILL.md").is_file(), (
                    f"{d.name}: SKILL.md missing from SKILLS_DIR path"
                )


# ---------------------------------------------------------------------------
# D1e — path-validation guard: self-copy is rejected
# ---------------------------------------------------------------------------


class TestInstallSkillsPathValidation:
    def test_self_copy_is_rejected(self):
        """install_skills must raise ValueError if destination resolves into
        the bundled skills directory itself (prevents corrupting the package)."""
        # The bundled skills dir is e.g. .../tree_sitter_analyzer/skills/
        # We need to pass a target_dir such that <target_dir>/.claude/skills/
        # resolves to the bundled skills dir.  That path is two levels up:
        # bundled_skills_dir / ".." / ".." == package root at best — but a
        # simpler approach is to monkeypatch _resolve_target to point directly
        # at the bundled dir; however we can also just pass a crafted path.
        # Use a direct mock instead so the test is not fragile to path depth.
        from unittest.mock import patch

        import pytest

        from tree_sitter_analyzer.cli.install_skills import (
            _bundled_skills_dir,
            install_skills,
        )

        bundled = _bundled_skills_dir()

        with patch(
            "tree_sitter_analyzer.cli.install_skills._resolve_target",
            return_value=bundled,
        ):
            with pytest.raises(ValueError, match="self-copy"):
                install_skills(target_dir=None)


# ---------------------------------------------------------------------------
# D1f — handler dispatch: end-to-end CLI tests via special_commands
# ---------------------------------------------------------------------------


class TestInstallSkillsHandlerDispatch:
    def test_handle_install_skills_no_flag_returns_none(self, tmp_path):
        """Test _handle_install_skills returns None when no flags are set."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.cli.special_commands import (
            SpecialCommandContext,
            _handle_install_skills,
        )

        args = SimpleNamespace(
            install_skills=None,
            install_skills_global=False,
        )
        context = SpecialCommandContext(
            asyncio_run=lambda x: x,
            output_json=MagicMock(),
            output_error=MagicMock(),
            output_info=MagicMock(),
            output_list=MagicMock(),
            query_loader=MagicMock(),
        )

        rc = _handle_install_skills(args, context)
        assert rc is None

    def test_handle_install_skills_with_explicit_target(self, tmp_path):
        """Test --install-skills <dir> installs to <dir>/.claude/skills/."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.cli.special_commands import (
            SpecialCommandContext,
            _handle_install_skills,
        )

        target = tmp_path / "myproject"
        target.mkdir()

        captured = {}

        def capture_json(d):
            captured["json"] = d

        args = SimpleNamespace(
            install_skills=str(target),
            install_skills_global=False,
        )
        context = SpecialCommandContext(
            asyncio_run=lambda x: x,
            output_json=capture_json,
            output_error=MagicMock(),
            output_info=MagicMock(),
            output_list=MagicMock(),
            query_loader=MagicMock(),
        )

        rc = _handle_install_skills(args, context)

        assert rc == 0
        assert captured["json"]["success"] is True
        assert captured["json"]["installed_count"] == 13
        assert captured["json"]["skipped_count"] == 0
        assert (target / ".claude" / "skills").is_dir()

    def test_handle_install_skills_with_dot_target(self, tmp_path, monkeypatch):
        """Test --install-skills . installs to $CWD/.claude/skills/."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.cli.special_commands import (
            SpecialCommandContext,
            _handle_install_skills,
        )

        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.chdir(project)

        captured = {}

        def capture_json(d):
            captured["json"] = d

        args = SimpleNamespace(
            install_skills=".",
            install_skills_global=False,
        )
        context = SpecialCommandContext(
            asyncio_run=lambda x: x,
            output_json=capture_json,
            output_error=MagicMock(),
            output_info=MagicMock(),
            output_list=MagicMock(),
            query_loader=MagicMock(),
        )

        rc = _handle_install_skills(args, context)

        assert rc == 0
        assert captured["json"]["success"] is True
        assert captured["json"]["installed_count"] == 13
        assert (project / ".claude" / "skills").is_dir()

    def test_handle_install_skills_global_flag(self, tmp_path, monkeypatch):
        """Test --install-skills-global installs to ~/.claude/skills/."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.cli.special_commands import (
            SpecialCommandContext,
            _handle_install_skills,
        )

        monkeypatch.setenv("HOME", str(tmp_path))

        captured = {}

        def capture_json(d):
            captured["json"] = d

        args = SimpleNamespace(
            install_skills=None,
            install_skills_global=True,
        )
        context = SpecialCommandContext(
            asyncio_run=lambda x: x,
            output_json=capture_json,
            output_error=MagicMock(),
            output_info=MagicMock(),
            output_list=MagicMock(),
            query_loader=MagicMock(),
        )

        rc = _handle_install_skills(args, context)

        assert rc == 0
        assert captured["json"]["success"] is True
        assert captured["json"]["installed_count"] == 13
        assert (tmp_path / ".claude" / "skills").is_dir()


# ---------------------------------------------------------------------------
# D1g — error handling: permission errors and skip-existing messages
# ---------------------------------------------------------------------------


class TestInstallSkillsErrorHandling:
    def test_permission_error_on_mkdir_raised(self, tmp_path):
        """install_skills raises PermissionError when mkdir fails."""
        from unittest.mock import patch

        import pytest

        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "proj"
        target.mkdir()

        with patch(
            "tree_sitter_analyzer.cli.install_skills.Path.mkdir",
            side_effect=PermissionError("denied"),
        ):
            with pytest.raises(PermissionError, match="Cannot create skills directory"):
                install_skills(target_dir=target)

    def test_permission_error_on_copytree_raised(self, tmp_path):
        """install_skills propagates errors during copytree."""
        from unittest.mock import patch

        import pytest

        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "proj"
        target.mkdir()

        with patch(
            "tree_sitter_analyzer.cli.install_skills.shutil.copytree",
            side_effect=PermissionError("cannot copy"),
        ):
            with pytest.raises(PermissionError, match="cannot copy"):
                install_skills(target_dir=target)

    def test_skip_existing_prints_to_stderr(self, tmp_path, capsys):
        """When a skill already exists, skip message goes to stderr."""
        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "proj"
        target.mkdir()
        existing = target / ".claude" / "skills" / "tsa-index"
        existing.mkdir(parents=True)

        report = install_skills(target_dir=target)

        captured = capsys.readouterr()
        assert report["skipped_count"] == 1
        assert "Skipped (already exists)" in captured.err
        assert str(existing) in captured.err

    def test_installed_skill_prints_to_stderr(self, tmp_path, capsys):
        """When a skill is installed, message goes to stderr."""
        from tree_sitter_analyzer.cli.install_skills import install_skills

        target = tmp_path / "proj"
        target.mkdir()

        report = install_skills(target_dir=target)

        captured = capsys.readouterr()
        assert report["installed_count"] == 13
        assert "Installed:" in captured.err
        # path-separator agnostic (Windows prints backslashes)
        assert str(target / ".claude" / "skills" / "tsa-constraints") in captured.err


# ---------------------------------------------------------------------------
# D1h — content-sync guard: bundled wheel copy == .claude/skills source
# ---------------------------------------------------------------------------


class TestSkillContentSync:
    """The bundled package copy (tree_sitter_analyzer/skills/) MUST be
    byte-identical to the .claude/skills/ source of truth.

    If these ever diverge an agent installing the package gets stale content.
    Added for issue #437 (legacy tool names shipped in the wheel).
    """

    SKILL_NAMES = [
        "tsa-constraints",
        "tsa-deps",
        "tsa-edit-safety",
        "tsa-edit-then-verify",
        "tsa-find",
        "tsa-graph",
        "tsa-health-watch",
        "tsa-index",
        "tsa-landing",
        "tsa-pr-review",
        "tsa-refactor-queue",
        "tsa-structure",
        "tsa-temporal",
    ]

    def _repo_root(self) -> Path:
        """Locate the repository root relative to this test file."""
        # tests/unit/cli/test_install_skills.py → three parents up = repo root
        return Path(__file__).parent.parent.parent.parent

    def test_bundled_content_matches_claude_source_for_all_13_skills(self):
        """Bundled SKILL.md bytes must equal .claude/skills SKILL.md bytes.

        The bundled copy lives at tree_sitter_analyzer/skills/<name>/SKILL.md.
        The source-of-truth copy lives at .claude/skills/<name>/SKILL.md.
        They are synced at authoring time; this test detects drift.
        """
        repo = self._repo_root()
        bundled_base = repo / "tree_sitter_analyzer" / "skills"
        source_base = repo / ".claude" / "skills"

        mismatches = []
        for name in self.SKILL_NAMES:
            bundled_path = bundled_base / name / "SKILL.md"
            source_path = source_base / name / "SKILL.md"

            assert bundled_path.is_file(), f"Bundled SKILL.md missing: {bundled_path}"
            assert source_path.is_file(), f"Source SKILL.md missing: {source_path}"

            bundled_bytes = bundled_path.read_bytes()
            source_bytes = source_path.read_bytes()
            if bundled_bytes != source_bytes:
                mismatches.append(name)

        assert mismatches == [], (
            f"Bundled and .claude/skills copies diverged for: {mismatches}. "
            "Run: cp .claude/skills/<name>/SKILL.md tree_sitter_analyzer/skills/<name>/SKILL.md "
            "for each skill in the list."
        )

    def test_no_legacy_tool_names_in_skills(self):
        """Installed SKILL.md files must not contain legacy v1.x tool-call syntax.

        Legacy names: bare old-tool-name(...) patterns that the 8-facade MCP
        server does not register. Agents following these instructions fail on
        their first call (issue #437).

        The authoritative legacy set is LEGACY_TOOL_MAP keys from facade_map.py
        plus get_project_summary (was never in LEGACY_TOOL_MAP but appeared
        in skills). Canonical call form: ``edit action=safe`` not ``safe_to_edit()``.
        """
        import re

        # Subset of high-impact legacy names — most likely to appear in tool
        # call positions. Full set in facade_map.LEGACY_TOOL_MAP.
        LEGACY_CALL_NAMES = [
            "safe_to_edit",
            "analyze_change_impact",
            "check_project_health",
            "check_file_health",
            "check_constraints",
            "codegraph_callers",
            "codegraph_callees",
            "codegraph_pr_review",
            "codegraph_symbol_search",
            "codegraph_call_path",
            "analyze_dependencies",
            "codegraph_import_graph",
            "codegraph_sitemap",
            "extract_code_section",
            "find_and_grep",
            "search_content",
            "list_files",
            "check_code_scale",
            "analyze_code_structure",
            "query_code",
            "code_patterns",
            "semantic_classify",
            "refactoring_suggestions",
            "ast_diff",
            "codegraph_dead_code",
            "codegraph_overview",
            "codegraph_complexity_heatmap",
            "advise_parser_readiness",
            "get_agent_workflow",
            "get_project_summary",
            "smart_context",
            "codegraph_autoindex",
            "codegraph_full_index",
            "ast_cache",
            "codegraph_uml",
        ]

        repo = self._repo_root()
        bundled_base = repo / "tree_sitter_analyzer" / "skills"

        violations: dict[str, list[str]] = {}
        for name in self.SKILL_NAMES:
            skill_path = bundled_base / name / "SKILL.md"
            content = skill_path.read_text(encoding="utf-8")
            found = []
            for legacy in LEGACY_CALL_NAMES:
                # Match name immediately followed by ( — i.e. a function call
                if re.search(r"\b" + re.escape(legacy) + r"\s*\(", content):
                    found.append(legacy)
            if found:
                violations[name] = found

        assert violations == {}, (
            "Legacy tool-call names found in bundled skills (issue #437). "
            "Replace with facade+action form (e.g. 'safe_to_edit(' → "
            "'edit action=safe'). Violations: " + str(violations)
        )
