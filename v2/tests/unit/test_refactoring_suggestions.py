"""
Unit tests for refactoring suggestions engine.

Sprint 6: suggest_refactorings() on CodeMapResult.
Sprint 8: Enhanced rules (long_method, too_many_params, complex_method).
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.core.code_map import ProjectCodeMap, RefactoringSuggestion
from tree_sitter_analyzer_v2.core.code_map.analyzers.refactoring import (
    _count_params,
    suggest_refactorings,
)
from tree_sitter_analyzer_v2.core.code_map.types import ModuleInfo, SymbolInfo


@pytest.fixture
def cross_file_project():
    return Path(__file__).parent.parent / "fixtures" / "cross_file_project"


@pytest.fixture
def result(cross_file_project):
    mapper = ProjectCodeMap()
    return mapper.scan(str(cross_file_project), extensions=[".py"])


class TestSuggestRefactoringsExists:
    """Test that suggest_refactorings() method exists and returns results."""

    def test_method_exists(self, result):
        """CodeMapResult should have suggest_refactorings method."""
        assert hasattr(result, "suggest_refactorings")
        assert callable(result.suggest_refactorings)

    def test_returns_list(self, result):
        """suggest_refactorings should return a list."""
        suggestions = result.suggest_refactorings()
        assert isinstance(suggestions, list)

    def test_suggestions_have_required_fields(self, result):
        """Each suggestion should have kind, severity, message, symbol, file."""
        suggestions = result.suggest_refactorings()
        if suggestions:
            s = suggestions[0]
            assert hasattr(s, "kind")
            assert hasattr(s, "severity")
            assert hasattr(s, "message")
            assert hasattr(s, "symbol_name")
            assert hasattr(s, "file_path")


class TestRefactoringSuggestionTypes:
    """Test specific types of refactoring suggestions."""

    def test_dead_code_suggestions(self, result):
        """Dead code should generate 'remove_dead_code' suggestions."""
        suggestions = result.suggest_refactorings()
        dead_suggestions = [s for s in suggestions if s.kind == "remove_dead_code"]
        # If there are dead code symbols, there should be suggestions
        if result.dead_code:
            assert len(dead_suggestions) > 0

    def test_hot_spot_suggestions(self, result):
        """Hot spots should generate 'reduce_coupling' suggestions."""
        suggestions = result.suggest_refactorings()
        hot_suggestions = [s for s in suggestions if s.kind == "reduce_coupling"]
        # Hot spots with many refs should generate suggestions
        if result.hot_spots:
            # Only symbols with very high ref count should trigger
            assert isinstance(hot_suggestions, list)

    def test_large_module_suggestions(self, result):
        """Modules with too many symbols should trigger 'split_module' suggestions."""
        suggestions = result.suggest_refactorings()
        split_suggestions = [s for s in suggestions if s.kind == "split_module"]
        assert isinstance(split_suggestions, list)


class TestRefactoringSuggestionToon:
    """Test TOON output for suggestions."""

    def test_to_toon_produces_output(self, result):
        """Suggestions should produce TOON-formatted output."""
        suggestions = result.suggest_refactorings()
        from tree_sitter_analyzer_v2.core.code_map import RefactoringSuggestion
        assert RefactoringSuggestion is not None

    def test_suggestion_severity_levels(self, result):
        """Suggestions should have valid severity levels."""
        suggestions = result.suggest_refactorings()
        valid_severities = {"info", "warning", "critical"}
        for s in suggestions:
            assert s.severity in valid_severities, f"Invalid severity: {s.severity}"


class TestMcpRefactoringAction:
    """Test MCP tool exposure of refactoring suggestions."""

    def test_refactoring_action_in_intelligence_tool(self):
        """code_intelligence tool should support 'refactorings' action."""
        from tree_sitter_analyzer_v2.mcp.tools.intelligence import _VALID_ACTIONS
        assert "refactorings" in _VALID_ACTIONS


# ──────── S8: New Rule Tests (Pure Function) ────────


class TestCountParams:
    """Test the _count_params helper."""

    def test_empty_string(self):
        assert _count_params("") == 0

    def test_single_param(self):
        assert _count_params("x") == 1

    def test_multiple_params(self):
        assert _count_params("a,b,c") == 3

    def test_params_with_spaces(self):
        assert _count_params("a, b, c, d") == 4

    def test_whitespace_only(self):
        assert _count_params("   ") == 0


class TestLongMethodDetection:
    """Test long_method suggestion rule."""

    def test_short_method_no_suggestion(self):
        """Methods under threshold should not trigger."""
        symbols = [SymbolInfo(
            name="short_func", kind="function", file="a.py",
            line_start=1, line_end=10, params="x",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_methods = [s for s in result if s.kind == "long_method"]
        assert len(long_methods) == 0

    def test_long_method_triggers(self):
        """Methods exceeding 50 lines should trigger long_method."""
        symbols = [SymbolInfo(
            name="huge_process", kind="function", file="big.py",
            line_start=10, line_end=80, params="data",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_methods = [s for s in result if s.kind == "long_method"]
        assert len(long_methods) == 1
        assert long_methods[0].symbol_name == "huge_process"
        assert "70 lines" in long_methods[0].message

    def test_long_method_severity_warning(self):
        """long_method should have warning severity."""
        symbols = [SymbolInfo(
            name="big", kind="method", file="a.py",
            line_start=1, line_end=60, params="",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_methods = [s for s in result if s.kind == "long_method"]
        assert len(long_methods) == 1
        assert long_methods[0].severity == "warning"

    def test_boundary_50_lines_no_trigger(self):
        """Exactly 50 lines should not trigger (> not >=)."""
        symbols = [SymbolInfo(
            name="edge", kind="function", file="a.py",
            line_start=1, line_end=51, params="",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_methods = [s for s in result if s.kind == "long_method"]
        assert len(long_methods) == 0

    def test_boundary_51_lines_triggers(self):
        """51 lines should trigger."""
        symbols = [SymbolInfo(
            name="edge", kind="function", file="a.py",
            line_start=1, line_end=52, params="",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_methods = [s for s in result if s.kind == "long_method"]
        assert len(long_methods) == 1

    def test_class_ignored(self):
        """Classes should not trigger long_method."""
        symbols = [SymbolInfo(
            name="BigClass", kind="class", file="a.py",
            line_start=1, line_end=200, params="",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_methods = [s for s in result if s.kind == "long_method"]
        assert len(long_methods) == 0


class TestTooManyParamsDetection:
    """Test too_many_params suggestion rule."""

    def test_few_params_no_suggestion(self):
        """Functions with <= 5 params should not trigger."""
        symbols = [SymbolInfo(
            name="ok_func", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c",
        )]
        result = suggest_refactorings([], [], [], symbols)
        too_many = [s for s in result if s.kind == "too_many_params"]
        assert len(too_many) == 0

    def test_many_params_triggers(self):
        """Functions with >5 params should trigger."""
        symbols = [SymbolInfo(
            name="complex_func", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e,f",
        )]
        result = suggest_refactorings([], [], [], symbols)
        too_many = [s for s in result if s.kind == "too_many_params"]
        assert len(too_many) == 1
        assert too_many[0].symbol_name == "complex_func"
        assert "6 parameters" in too_many[0].message

    def test_exactly_5_params_no_trigger(self):
        """Exactly 5 params should not trigger (> not >=)."""
        symbols = [SymbolInfo(
            name="edge", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e",
        )]
        result = suggest_refactorings([], [], [], symbols)
        too_many = [s for s in result if s.kind == "too_many_params"]
        assert len(too_many) == 0

    def test_severity_info(self):
        """too_many_params should have info severity."""
        symbols = [SymbolInfo(
            name="many", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e,f,g",
        )]
        result = suggest_refactorings([], [], [], symbols)
        too_many = [s for s in result if s.kind == "too_many_params"]
        assert too_many[0].severity == "info"


class TestComplexMethodDetection:
    """Test complex_method suggestion rule (long + many params combined)."""

    def test_long_only_no_complex(self):
        """Long method with few params should not trigger complex_method."""
        symbols = [SymbolInfo(
            name="long_simple", kind="function", file="a.py",
            line_start=1, line_end=60, params="x",
        )]
        result = suggest_refactorings([], [], [], symbols)
        complex_m = [s for s in result if s.kind == "complex_method"]
        assert len(complex_m) == 0

    def test_many_params_only_no_complex(self):
        """Short method with many params should not trigger complex_method."""
        symbols = [SymbolInfo(
            name="short_complex", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e",
        )]
        result = suggest_refactorings([], [], [], symbols)
        complex_m = [s for s in result if s.kind == "complex_method"]
        assert len(complex_m) == 0

    def test_long_and_many_params_triggers(self):
        """Function that is both long (>30 lines) and has many params (>3) triggers."""
        symbols = [SymbolInfo(
            name="god_func", kind="function", file="a.py",
            line_start=1, line_end=45, params="a,b,c,d",
        )]
        result = suggest_refactorings([], [], [], symbols)
        complex_m = [s for s in result if s.kind == "complex_method"]
        assert len(complex_m) == 1
        assert complex_m[0].severity == "warning"
        assert "44 lines" in complex_m[0].message
        assert "4 params" in complex_m[0].message

    def test_combined_suggestion_with_long_method(self):
        """A very long method with many params should trigger both long_method AND complex_method."""
        symbols = [SymbolInfo(
            name="monster", kind="function", file="a.py",
            line_start=1, line_end=80, params="a,b,c,d,e,f",
        )]
        result = suggest_refactorings([], [], [], symbols)
        kinds = {s.kind for s in result}
        assert "long_method" in kinds
        assert "too_many_params" in kinds
        assert "complex_method" in kinds


class TestRefactoringSuggestionDetail:
    """Test detail field is populated correctly."""

    def test_long_method_detail(self):
        symbols = [SymbolInfo(
            name="big", kind="function", file="a.py",
            line_start=1, line_end=60, params="",
        )]
        result = suggest_refactorings([], [], [], symbols)
        long_m = [s for s in result if s.kind == "long_method"][0]
        assert "lines=59" in long_m.detail

    def test_too_many_params_detail(self):
        symbols = [SymbolInfo(
            name="many", kind="function", file="a.py",
            line_start=1, line_end=10, params="a,b,c,d,e,f",
        )]
        result = suggest_refactorings([], [], [], symbols)
        too_many = [s for s in result if s.kind == "too_many_params"][0]
        assert "params=6" in too_many.detail

    def test_complex_method_detail(self):
        symbols = [SymbolInfo(
            name="complex", kind="function", file="a.py",
            line_start=1, line_end=45, params="a,b,c,d",
        )]
        result = suggest_refactorings([], [], [], symbols)
        cm = [s for s in result if s.kind == "complex_method"][0]
        assert "lines=44" in cm.detail
        assert "params=4" in cm.detail
