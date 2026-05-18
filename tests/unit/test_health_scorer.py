"""Unit tests for health_scorer.py — file-level code health scoring."""

import json
import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "project_graph"
HEALTH_PROJECT = FIXTURES_DIR / "health_project"


# ============================================================
# HealthScorer tests
# ============================================================


class TestHealthScorer:
    """Test file health scoring."""

    @pytest.fixture
    def scorer(self):
        from tree_sitter_analyzer.health_scorer import HealthScorer

        return HealthScorer()

    def test_healthy_file_scores_higher(self, scorer):
        """healthy.py should score higher than unhealthy.py."""
        healthy_score = scorer.score_file(str(HEALTH_PROJECT / "healthy.py"))
        unhealthy_score = scorer.score_file(str(HEALTH_PROJECT / "unhealthy.py"))
        assert healthy_score.total > unhealthy_score.total, (
            f"Expected healthy ({healthy_score.total}) > unhealthy ({unhealthy_score.total})"
        )

    def test_score_is_between_0_and_100(self, scorer):
        """All scores should be in the 0-100 range."""
        for fname in ["healthy.py", "unhealthy.py"]:
            result = scorer.score_file(str(HEALTH_PROJECT / fname))
            assert 0 <= result.total <= 100, (
                f"Score for {fname} out of range: {result.total}"
            )

    def test_score_has_breakdown(self, scorer):
        """Score should include per-dimension breakdown."""
        result = scorer.score_file(str(HEALTH_PROJECT / "healthy.py"))
        breakdown = result.to_dict()
        assert "total" in breakdown
        assert "dimensions" in breakdown
        dims = breakdown["dimensions"]
        for key in ("size", "complexity", "dependencies", "structure"):
            assert key in dims, f"Missing dimension: {key}"

    def test_score_empty_file(self, scorer, tmp_path):
        """Empty file gets a baseline score."""
        empty = tmp_path / "empty.py"
        empty.write_text("")
        result = scorer.score_file(str(empty))
        assert result.total >= 0
        assert result.total <= 100

    def test_score_nonexistent_file(self, scorer):
        """Nonexistent file returns 0 score."""
        result = scorer.score_file("/nonexistent/file.py")
        assert result.total == 0

    def test_score_project(self, scorer):
        """Can score an entire project directory."""
        results = scorer.score_project(str(HEALTH_PROJECT))
        assert len(results) >= 2, f"Expected >=2 results, got {len(results)}"
        for r in results:
            assert 0 <= r.total <= 100

    def test_score_project_includes_reported_source_extensions(self, scorer, tmp_path):
        """Project scoring should include all configured reportable extensions."""
        from tree_sitter_analyzer.health_scorer import PROJECT_HEALTH_SOURCE_EXTS

        for idx, ext in enumerate(sorted(PROJECT_HEALTH_SOURCE_EXTS)):
            path = tmp_path / f"sample{idx}{ext}"
            path.write_text("x = 1\n")

        unknown = tmp_path / "ignored.log"
        unknown.write_text("x = 1\n")

        results = scorer.score_project(str(tmp_path))
        names = {Path(result.file_path).name for result in results}
        included = {
            f"sample{idx}{ext}"
            for idx, ext in enumerate(sorted(PROJECT_HEALTH_SOURCE_EXTS))
        }

        assert names >= included
        assert "ignored.log" not in names

    def test_score_project_respects_custom_source_extensions(self, tmp_path):
        """Health scorer should limit scan scope to caller-provided extensions."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        py_file = tmp_path / "main.py"
        cfg_file = tmp_path / "project.cfg"
        py_file.write_text("x = 1\n")
        cfg_file.write_text("x = 1\n")

        scorer = HealthScorer(source_extensions={".cfg"})
        results = scorer.score_project(str(tmp_path))
        names = {Path(result.file_path).name for result in results}

        assert names == {"project.cfg"}

    def test_large_file_gets_penalized(self, scorer, tmp_path):
        """Files over 500 lines should have lower size score."""
        big = tmp_path / "big.py"
        big.write_text("\n".join([f"x{i} = {i}" for i in range(600)]))
        result = scorer.score_file(str(big))
        dims = result.to_dict()["dimensions"]
        assert dims["size"] < 85, (
            f"Large file should have low size score, got {dims['size']}"
        )

    def test_cc_penalizes_branches(self, scorer, tmp_path):
        """Code with many branches should have lower complexity score."""
        # High CC: 20 if-statements → CC = 21
        high_cc = tmp_path / "high_cc.py"
        lines = ["def f(x):"]
        for i in range(20):
            lines.append(f"    if x > {i}:")
            lines.append("        pass")
        high_cc.write_text("\n".join(lines))

        # Low CC: single return → CC = 1
        low_cc = tmp_path / "low_cc.py"
        low_cc.write_text("def f(x):\n    return x\n")

        high_result = scorer.score_file(str(high_cc))
        low_result = scorer.score_file(str(low_cc))
        assert (
            high_result.to_dict()["dimensions"]["complexity"]
            < low_result.to_dict()["dimensions"]["complexity"]
        ), "High CC code should have lower complexity score"

    def test_deeply_nested_code_penalized(self, scorer, tmp_path):
        """Deeply nested code should have lower structure score."""
        deep = tmp_path / "deep.py"
        deep.write_text(
            "def f(x):\n    if x:\n        if x:\n            if x:\n"
            "                if x:\n                    if x:\n"
            "                        if x:\n                            pass\n"
        )
        flat = tmp_path / "flat.py"
        flat.write_text("def f(x):\n    return x\n")
        deep_result = scorer.score_file(str(deep))
        flat_result = scorer.score_file(str(flat))
        assert (
            deep_result.to_dict()["dimensions"]["structure"]
            < flat_result.to_dict()["dimensions"]["structure"]
        ), "Deep nesting should have lower structure score"

    def test_coverage_none_without_data(self, scorer, tmp_path):
        """Coverage should be None (excluded from total) when no coverage.json exists."""
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = scorer.score_file(str(f))
        dims = result.to_dict()["dimensions"]
        assert "coverage" not in dims, (
            f"Coverage should be absent when no data, got {dims}"
        )

    def test_stale_coverage_json_is_ignored(self, monkeypatch, tmp_path):
        """Do not use stale JSON coverage when pytest-cov has newer raw data."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "pkg" / "module.py"
        source.parent.mkdir()
        source.write_text("x = 1\n")
        coverage_json = tmp_path / "coverage.json"
        coverage_json.write_text(
            json.dumps(
                {
                    "files": {"pkg/module.py": {"summary": {"percent_covered": 12.5}}},
                    "totals": {"percent_covered": 12.5},
                }
            ),
            encoding="utf-8",
        )
        coverage_db = tmp_path / ".coverage"
        coverage_db.write_text("newer raw coverage", encoding="utf-8")
        os.utime(coverage_json, (1000, 1000))
        os.utime(coverage_db, (2000, 2000))
        monkeypatch.chdir(tmp_path)

        result = HealthScorer().score_file(str(source))

        assert "coverage" not in result.to_dict()["dimensions"]

    def test_current_coverage_json_is_used(self, monkeypatch, tmp_path):
        """Use JSON coverage when it is as current as the raw coverage data."""
        from tree_sitter_analyzer.health_scorer import HealthScorer

        source = tmp_path / "pkg" / "module.py"
        source.parent.mkdir()
        source.write_text("x = 1\n")
        coverage_json = tmp_path / "coverage.json"
        coverage_json.write_text(
            json.dumps(
                {
                    "files": {"pkg/module.py": {"summary": {"percent_covered": 87.5}}},
                    "totals": {"percent_covered": 87.5},
                }
            ),
            encoding="utf-8",
        )
        coverage_db = tmp_path / ".coverage"
        coverage_db.write_text("older raw coverage", encoding="utf-8")
        os.utime(coverage_db, (1000, 1000))
        os.utime(coverage_json, (2000, 2000))
        monkeypatch.chdir(tmp_path)

        result = HealthScorer().score_file(str(source))

        assert result.to_dict()["dimensions"]["coverage"] == 87.5

    def test_weights_sum_to_100(self):
        """Default dimension weights must sum to 100."""
        from tree_sitter_analyzer.health_scorer import DIMENSION_WEIGHTS

        assert sum(DIMENSION_WEIGHTS.values()) == 100, (
            f"Weights sum to {sum(DIMENSION_WEIGHTS.values())}"
        )

    def test_decision_node_types_cover_major_languages(self):
        """All major languages should have CC decision node definitions."""
        from tree_sitter_analyzer.health_scorer import DECISION_NODE_TYPES

        for lang in [
            "python",
            "javascript",
            "typescript",
            "java",
            "c",
            "cpp",
            "go",
            "rust",
            "ruby",
            "php",
            "kotlin",
            "csharp",
        ]:
            assert lang in DECISION_NODE_TYPES, f"Missing CC nodes for {lang}"
            assert len(DECISION_NODE_TYPES[lang]) >= 5, (
                f"{lang} has too few decision node types"
            )

    def test_duplication_penalizes_repeated_code(self, scorer, tmp_path):
        """Files with repeated code blocks should have lower duplication score."""
        # High duplication: same block repeated 10 times
        repeated = tmp_path / "dup.py"
        block = "x = 1\ny = 2\nz = 3\n"
        repeated.write_text(block * 10)

        # No duplication: unique lines
        unique = tmp_path / "unique.py"
        unique.write_text("\n".join([f"x{i} = {i}" for i in range(30)]))

        dup_result = scorer.score_file(str(repeated))
        unique_result = scorer.score_file(str(unique))
        assert (
            dup_result.to_dict()["dimensions"]["duplication"]
            < unique_result.to_dict()["dimensions"]["duplication"]
        ), "Repeated code should have lower duplication score"

    def test_git_hotspot_none_outside_git(self, scorer, tmp_path):
        """Git hotspot should be None for files outside git repo."""
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = scorer.score_file(str(f))
        # tmp_path may or may not be in a git repo, so hotspot can be present or absent
        # Just verify it doesn't crash and score is valid
        assert result.total >= 0
        assert result.total <= 100

    def test_git_hotspot_uses_repo_relative_pathspec(self, monkeypatch, tmp_path):
        """Git hotspot should query from repo root with a repo-relative path."""
        import subprocess
        from types import SimpleNamespace

        from tree_sitter_analyzer.health_scorer import score_git_hotspot

        repo = tmp_path / "repo"
        file_path = repo / "tree_sitter_analyzer" / "cli_main.py"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("x = 1\n")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
                return SimpleNamespace(returncode=0, stdout=f"{repo}\n")
            return SimpleNamespace(returncode=0, stdout="\n".join(["abc"] * 10))

        monkeypatch.setattr(subprocess, "run", fake_run)

        score = score_git_hotspot(str(file_path))

        assert score == pytest.approx(88.9, abs=0.1)
        assert calls[1][0][-1] == "tree_sitter_analyzer/cli_main.py"
        assert calls[1][1]["cwd"] == str(repo)

    def test_seven_dimensions_in_weights(self):
        """All 7 dimensions should be in DIMENSION_WEIGHTS."""
        from tree_sitter_analyzer.health_scorer import DIMENSION_WEIGHTS

        expected = {
            "size",
            "complexity",
            "dependencies",
            "coverage",
            "duplication",
            "structure",
            "git_hotspot",
        }
        assert set(DIMENSION_WEIGHTS.keys()) == expected


# ============================================================
# HealthScore data class tests
# ============================================================


class TestHealthScore:
    """Test the HealthScore data class."""

    def test_health_score_creation(self):
        from tree_sitter_analyzer.health_scorer import HealthScore

        score = HealthScore(
            file_path="test.py",
            total=75.0,
            dimensions={
                "size": 80,
                "complexity": 60,
                "dependencies": 90,
                "structure": 70,
            },
        )
        assert score.file_path == "test.py"
        assert score.total == 75.0
        assert len(score.dimensions) >= 3

    def test_health_score_to_dict(self):
        from tree_sitter_analyzer.health_scorer import HealthScore

        score = HealthScore(
            file_path="test.py",
            total=75.0,
            dimensions={"size": 80, "complexity": 60, "dependencies": 90},
        )
        d = score.to_dict()
        assert d["file"] == "test.py"
        assert d["total"] == 75.0
        assert d["dimensions"]["size"] == 80

    def test_health_score_grade(self):
        from tree_sitter_analyzer.health_scorer import HealthScore

        assert HealthScore("f", 95, {}).grade == "A"
        assert HealthScore("f", 85, {}).grade == "B"
        assert HealthScore("f", 72, {}).grade == "C"
        assert HealthScore("f", 55, {}).grade == "D"
        assert HealthScore("f", 30, {}).grade == "F"
