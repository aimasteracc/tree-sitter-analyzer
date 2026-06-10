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
