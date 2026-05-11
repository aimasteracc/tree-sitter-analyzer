"""Unit tests for health_scorer.py — file-level code health scoring."""

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
        assert healthy_score.total > unhealthy_score.total, \
            f"Expected healthy ({healthy_score.total}) > unhealthy ({unhealthy_score.total})"

    def test_score_is_between_0_and_100(self, scorer):
        """All scores should be in the 0-100 range."""
        for fname in ["healthy.py", "unhealthy.py"]:
            result = scorer.score_file(str(HEALTH_PROJECT / fname))
            assert 0 <= result.total <= 100, \
                f"Score for {fname} out of range: {result.total}"

    def test_score_has_breakdown(self, scorer):
        """Score should include per-dimension breakdown."""
        result = scorer.score_file(str(HEALTH_PROJECT / "healthy.py"))
        breakdown = result.to_dict()
        assert "total" in breakdown
        assert "dimensions" in breakdown
        dims = breakdown["dimensions"]
        for key in ("lines", "complexity", "dependencies", "comments", "coverage"):
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

    def test_large_file_gets_penalized(self, scorer, tmp_path):
        """Files over 500 lines should have lower line score."""
        big = tmp_path / "big.py"
        big.write_text("\n".join([f"x{i} = {i}" for i in range(600)]))
        result = scorer.score_file(str(big))
        # The lines dimension should be well below 100
        dims = result.to_dict()["dimensions"]
        assert dims["lines"] < 85, f"Large file should have low line score, got {dims['lines']}"

    def test_high_comment_ratio_helps_score(self, scorer, tmp_path):
        """File with good comment ratio should score well on comments dimension."""
        well_documented = tmp_path / "well_doc.py"
        content = '"""Module docstring."""\n\n# This is a comment\n# Another comment\ndef foo():\n    """Function docstring."""\n    # inline comment\n    return 1\n'
        well_documented.write_text(content)
        result = scorer.score_file(str(well_documented))
        dims = result.to_dict()["dimensions"]
        assert dims["comments"] > 30, f"Good comments should yield >30, got {dims['comments']}"

    def test_deeply_nested_code_penalized(self, scorer, tmp_path):
        """Deeply nested code should have lower complexity score."""
        deep = tmp_path / "deep.py"
        deep.write_text("def f(x):\n    if x:\n        if x:\n            if x:\n                if x:\n                    if x:\n                        if x:\n                            pass\n")
        flat = tmp_path / "flat.py"
        flat.write_text("def f(x):\n    return x\n")
        deep_result = scorer.score_file(str(deep))
        flat_result = scorer.score_file(str(flat))
        assert deep_result.to_dict()["dimensions"]["complexity"] < flat_result.to_dict()["dimensions"]["complexity"], \
            "Deep nesting should have lower complexity score"


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
            dimensions={"lines": 80, "complexity": 60, "dependencies": 90, "comments": 70, "coverage": 75},
        )
        assert score.file_path == "test.py"
        assert score.total == 75.0
        assert len(score.dimensions) == 5

    def test_health_score_to_dict(self):
        from tree_sitter_analyzer.health_scorer import HealthScore
        score = HealthScore(
            file_path="test.py",
            total=75.0,
            dimensions={"lines": 80, "complexity": 60, "dependencies": 90, "comments": 70, "coverage": 75},
        )
        d = score.to_dict()
        assert d["file"] == "test.py"
        assert d["total"] == 75.0
        assert d["dimensions"]["lines"] == 80

    def test_health_score_grade(self):
        from tree_sitter_analyzer.health_scorer import HealthScore
        assert HealthScore("f", 95, {}).grade == "A"
        assert HealthScore("f", 85, {}).grade == "B"
        assert HealthScore("f", 72, {}).grade == "C"
        assert HealthScore("f", 55, {}).grade == "D"
        assert HealthScore("f", 30, {}).grade == "F"
