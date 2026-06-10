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
