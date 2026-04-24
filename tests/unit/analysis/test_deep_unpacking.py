"""Tests for Deep Unpacking Analyzer."""
from __future__ import annotations

import tempfile

from tree_sitter_analyzer.analysis.deep_unpacking import (
    DeepUnpackingAnalyzer,
    DeepUnpackingResult,
)

ANALYZER = DeepUnpackingAnalyzer()


def _analyze(code: str) -> DeepUnpackingResult:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


class TestDeepUnpackingAssignment:
    """Tests for excessive tuple unpacking in assignments."""

    def test_no_unpacking(self) -> None:
        code = "x = 1\ny = 2\n"
        result = _analyze(code)
        assert result.total_hotspots == 0

    def test_simple_unpacking_below_threshold(self) -> None:
        code = "a, b, c = [1, 2, 3]\n"
        result = _analyze(code)
        assert result.total_hotspots == 0

    def test_unpacking_at_threshold(self) -> None:
        code = "a, b, c, d = [1, 2, 3, 4]\n"
        result = _analyze(code)
        assert result.total_hotspots == 1
        assert result.hotspots[0].variable_count == 4

    def test_unpacking_above_threshold(self) -> None:
        code = "a, b, c, d, e = range(5)\n"
        result = _analyze(code)
        assert result.total_hotspots == 1
        assert result.hotspots[0].variable_count == 5

    def test_unpacking_high_severity(self) -> None:
        code = "a, b, c, d, e, f = range(6)\n"
        result = _analyze(code)
        assert result.total_hotspots == 1
        assert result.hotspots[0].severity == "high"

    def test_unpacking_very_deep(self) -> None:
        code = "a, b, c, d, e, f, g, h = range(8)\n"
        result = _analyze(code)
        assert result.total_hotspots == 1
        assert result.hotspots[0].variable_count == 8
        assert result.hotspots[0].severity == "high"

    def test_multiple_unpacking(self) -> None:
        code = (
            "a, b, c, d = [1, 2, 3, 4]\n"
            "x, y, z, w, v = range(5)\n"
        )
        result = _analyze(code)
        assert result.total_hotspots == 2

    def test_regular_assignment_no_issue(self) -> None:
        code = "result = get_values()\n"
        result = _analyze(code)
        assert result.total_hotspots == 0

    def test_two_element_unpacking(self) -> None:
        code = "key, value = item\n"
        result = _analyze(code)
        assert result.total_hotspots == 0


class TestDeepUnpackingForLoop:
    """Tests for excessive tuple unpacking in for loops."""

    def test_for_unpacking_below_threshold(self) -> None:
        code = "for a, b, c in items:\n    pass\n"
        result = _analyze(code)
        assert result.total_hotspots == 0

    def test_for_unpacking_at_threshold(self) -> None:
        code = "for a, b, c, d in items:\n    pass\n"
        result = _analyze(code)
        assert result.total_hotspots == 1
        assert result.hotspots[0].variable_count == 4

    def test_for_unpacking_above_threshold(self) -> None:
        code = "for a, b, c, d, e in items:\n    pass\n"
        result = _analyze(code)
        assert result.total_hotspots == 1

    def test_for_simple_iteration(self) -> None:
        code = "for item in items:\n    pass\n"
        result = _analyze(code)
        assert result.total_hotspots == 0


class TestDeepUnpackingResult:
    """Tests for result object."""

    def test_to_dict(self) -> None:
        code = "a, b, c, d, e = range(5)\n"
        result = _analyze(code)
        d = result.to_dict()
        assert d["total_hotspots"] == 1
        assert len(d["hotspots"]) == 1
        assert d["hotspots"][0]["variable_count"] == 5

    def test_file_path_in_result(self) -> None:
        code = "x = 1\n"
        result = _analyze(code)
        assert result.file_path.endswith(".py")


class TestDeepUnpackingEdgeCases:
    """Tests for edge cases."""

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_hotspots == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False
        ) as f:
            f.write("const [a,b,c,d] = arr;")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.total_hotspots == 0

    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.total_hotspots == 0

    def test_nested_function_with_unpacking(self) -> None:
        code = (
            "def foo():\n"
            "    a, b, c, d, e = range(5)\n"
            "    return a\n"
        )
        result = _analyze(code)
        assert result.total_hotspots == 1
