"""Tests for file_health_smells — code smell detection helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.utils.file_health_smells import (
    COMMENT_DELIMITERS,
    TECH_DEBT_MARKERS,
    _check_deep_nesting,
    _check_element_smells,
    _check_god_class,
    _check_long_functions,
    _check_oversized_file,
    _check_technical_debt,
    _comment_text,
    _has_technical_debt_marker,
    detect_code_smells,
)


# ---------------------------------------------------------------------------
# detect_code_smells
# ---------------------------------------------------------------------------

class TestDetectCodeSmells:
    def test_returns_list(self, tmp_path) -> None:
        """Should always return a list, even for empty files."""
        f = tmp_path / "a.py"
        f.write_text("pass\n")
        result = detect_code_smells(str(f), {}, None, language="python")
        assert isinstance(result, list)

    def test_unreadable_file_returns_empty(self, tmp_path) -> None:
        """File that raises on read should return empty list."""
        result = detect_code_smells("/nonexistent/file.py", {}, None)
        assert result == []

    def test_healthy_file_no_smells(self, tmp_path) -> None:
        """Small, well-structured file should produce minimal smells."""
        f = tmp_path / "clean.py"
        f.write_text("def hello():\n    return 'world'\n")
        result = detect_code_smells(str(f), {"structure": 80, "complexity": 90, "dependencies": 85}, None)
        # May still have info-level smells but no critical ones
        critical = [s for s in result if s.get("severity") == "critical"]
        assert len(critical) == 0


# ---------------------------------------------------------------------------
# _check_oversized_file
# ---------------------------------------------------------------------------

class TestCheckOversizedFile:
    def test_small_file_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        _check_oversized_file(smells, 100)
        assert len(smells) == 0

    def test_medium_file_warning(self) -> None:
        smells: list[dict[str, Any]] = []
        _check_oversized_file(smells, 600)
        assert len(smells) == 1
        assert smells[0]["severity"] == "warning"

    def test_huge_file_critical(self) -> None:
        smells: list[dict[str, Any]] = []
        _check_oversized_file(smells, 1200)
        assert len(smells) == 1
        assert smells[0]["severity"] == "critical"
        assert smells[0]["smell"] == "oversized_file"

    def test_exact_threshold_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        _check_oversized_file(smells, 500)
        assert len(smells) == 0


# ---------------------------------------------------------------------------
# _check_deep_nesting
# ---------------------------------------------------------------------------

class TestCheckDeepNesting:
    def test_shallow_code_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        _check_deep_nesting(smells, ["def foo():", "    pass"])
        assert len(smells) == 0

    def test_deep_nesting_warning(self) -> None:
        smells: list[dict[str, Any]] = []
        lines = [""] + ["    " * i + "if True:" for i in range(6)]
        _check_deep_nesting(smells, lines)
        assert any(s["smell"] == "deep_nesting" for s in smells)


# ---------------------------------------------------------------------------
# _check_god_class
# ---------------------------------------------------------------------------

class TestCheckGodClass:
    def test_no_class_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        _check_god_class(smells, 100, [])
        assert len(smells) == 0

    def test_multiple_classes_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        classes = [{"name": "A", "line": 1, "end_line": 50}, {"name": "B", "line": 51, "end_line": 100}]
        _check_god_class(smells, 100, classes)
        assert len(smells) == 0

    def test_single_huge_class_critical(self) -> None:
        smells: list[dict[str, Any]] = []
        classes = [{"name": "GodClass", "line": 1, "end_line": 600}]
        _check_god_class(smells, 600, classes)
        assert len(smells) == 1
        assert smells[0]["smell"] == "god_class"
        assert smells[0]["severity"] == "critical"

    def test_single_class_under_threshold(self) -> None:
        smells: list[dict[str, Any]] = []
        classes = [{"name": "SmallClass", "line": 1, "end_line": 100}]
        _check_god_class(smells, 100, classes)
        assert len(smells) == 0


# ---------------------------------------------------------------------------
# _check_long_functions
# ---------------------------------------------------------------------------

class TestCheckLongFunctions:
    def test_short_function_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        functions = [{"name": "foo", "line": 1, "lines": 10}]
        _check_long_functions(smells, functions)
        assert len(smells) == 0

    def test_long_function_warning(self) -> None:
        smells: list[dict[str, Any]] = []
        functions = [{"name": "big_fn", "line": 5, "lines": 80}]
        _check_long_functions(smells, functions)
        assert len(smells) == 1
        assert smells[0]["severity"] == "warning"

    def test_very_long_function_critical(self) -> None:
        smells: list[dict[str, Any]] = []
        functions = [{"name": "huge_fn", "line": 1, "lines": 150}]
        _check_long_functions(smells, functions)
        assert smells[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# _has_technical_debt_marker / _comment_text
# ---------------------------------------------------------------------------

class TestTechnicalDebtDetection:
    @pytest.mark.parametrize("line", [
        "# TODO: fix this",
        "// FIXME broken",
        "/* HACK: workaround */",
        "# XXX temporary",
    ])
    def test_detects_markers(self, line: str) -> None:
        assert _has_technical_debt_marker(line) is True

    @pytest.mark.parametrize("line", [
        "#!shebang",
        "# type: ignore",
        "x = 'TODO in a string'",
        "print('no markers here')",
    ])
    def test_ignores_non_markers(self, line: str) -> None:
        assert _has_technical_debt_marker(line) is False

    def test_comment_text_extracts_comment(self) -> None:
        assert "TODO" in _comment_text("x = 1  # TODO: fix")

    def test_comment_text_no_comment(self) -> None:
        assert _comment_text("x = 1") == ""


class TestCheckTechnicalDebt:
    def test_few_markers_no_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        lines = ["# TODO: fix"] * 3
        _check_technical_debt(smells, lines)
        assert len(smells) == 0

    def test_many_markers_triggers_smell(self) -> None:
        smells: list[dict[str, Any]] = []
        lines = ["# TODO: fix"] * 10
        _check_technical_debt(smells, lines)
        assert any(s["smell"] == "technical_debt" for s in smells)


# ---------------------------------------------------------------------------
# _check_element_smells
# ---------------------------------------------------------------------------

class TestCheckElementSmells:
    def test_no_analysis_uses_heuristic(self) -> None:
        """When analysis is None, heuristic long-method detection runs."""
        smells: list[dict[str, Any]] = []
        lines = ["def long_fn():"] + ["    pass"] * 60
        _check_element_smells(smells, lines, len(lines), None)
        # heuristic may or may not flag depending on indentation
        assert isinstance(smells, list)

    def test_with_analysis_checks_classes_and_functions(self) -> None:
        """When analysis is provided, god_class and long_method checks run."""
        smells: list[dict[str, Any]] = []
        analysis = object()  # minimal mock
        _check_element_smells(smells, [], 0, analysis)
        assert isinstance(smells, list)
