"""Unit tests for RefactoringSuggestionsTool."""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
    RefactoringSuggestionsTool,
)

# Use project files for testing (within project boundary)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SAMPLE_PYTHON = str(
    PROJECT_ROOT / "tree_sitter_analyzer" / "languages" / "java_plugin.py"
)
SAMPLE_GENERIC = str(PROJECT_ROOT / "tree_sitter_analyzer" / "mcp" / "server.py")


@pytest.fixture
def tool():
    t = RefactoringSuggestionsTool(".")
    t.set_project_path(".")
    return t


def _run(coro):
    return asyncio.run(coro)


class TestRefactoringSuggestionsTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "refactoring_suggestions"
        assert "file_path" in defn["inputSchema"]["properties"]
        assert "max_suggestions" in defn["inputSchema"]["properties"]

    def test_validate_arguments_missing_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_valid(self, tool):
        assert tool.validate_arguments({"file_path": "some_file.py"})

    def test_python_analysis_works(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        assert "total_suggestions" in result
        assert "summary" in result
        assert "suggestions" in result

    def test_python_detects_long_function(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        long_funcs = [s for s in suggestions if s["name"] == "long_function"]
        assert len(long_funcs) >= 1

    def test_python_detects_deep_nesting(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        deep = [s for s in suggestions if s["name"] == "deep_nesting"]
        assert len(deep) >= 1

    def test_python_detects_large_class(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        large_classes = [s for s in suggestions if s["name"] == "reduce_class_size"]
        assert len(large_classes) >= 1

    def test_max_suggestions_limit(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON, "max_suggestions": 3}))
        assert result["total_suggestions"] <= 3

    def test_file_not_found(self, tool):
        result = _run(tool.execute({"file_path": "nonexistent_file.py"}))
        assert "error" in result

    def test_summary_format(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        summary = result["summary"]
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_suggestions_have_priority(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        for s in suggestions:
            assert "priority_score" in s
            assert isinstance(s["priority_score"], int)

    def test_suggestions_sorted_by_priority(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        scores = [s["priority_score"] for s in suggestions]
        assert scores == sorted(scores, reverse=True)

    def test_suggestions_have_line_ranges(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_PYTHON}))
        suggestions = result["suggestions"]
        for s in suggestions:
            if "line_range" in s:
                lr = s["line_range"]
                assert "start" in lr
                assert "end" in lr
                assert lr["start"] <= lr["end"]

    def test_include_extractions_false(self, tool):
        result = _run(
            tool.execute({"file_path": SAMPLE_PYTHON, "include_extractions": False})
        )
        extractions = [s for s in result["suggestions"] if s["type"] == "extraction"]
        assert len(extractions) == 0

    def test_server_file_analysis(self, tool):
        result = _run(tool.execute({"file_path": SAMPLE_GENERIC}))
        assert result["total_suggestions"] >= 0
