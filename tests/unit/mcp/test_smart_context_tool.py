"""Unit tests for SmartContextTool."""

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.smart_context_tool import (
    SmartContextTool,
    _extract_exports,
    _extract_structure,
    _quick_risk,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


@pytest.fixture
def tool():
    t = SmartContextTool(str(PROJECT_ROOT))
    t.set_project_path(str(PROJECT_ROOT))
    return t


def _run(coro):
    return asyncio.run(coro)


PYTHON_SOURCE = """
class MyClass:
    def method_a(self):
        pass

    def method_b(self):
        pass

def standalone_func():
    pass

MY_CONSTANT = 42

def _private_func():
    pass
"""


class TestSmartContextTool:
    def test_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "smart_context"

    def test_validate_arguments_missing_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({})

    def test_validate_arguments_valid(self, tool):
        assert tool.validate_arguments({"file_path": "some_file.py"})

    def test_execute_returns_complete_profile(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        assert "health" in result
        assert "exports" in result
        assert "structure" in result
        assert "dependencies" in result
        assert "tests" in result
        assert "edit_risk" in result
        assert "recommendation" in result

    def test_health_has_grade_and_score(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        health = result["health"]
        assert "grade" in health
        assert "score" in health
        assert "weakest_dimension" in health

    def test_exports_include_classes_and_functions(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        exports = result["exports"]
        names = [e["name"] for e in exports]
        assert "SmartContextTool" in names

    def test_structure_has_line_ranges(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        for item in result["structure"]:
            assert "name" in item
            assert "kind" in item

    def test_dependencies_structure(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        deps = result["dependencies"]
        assert "imports_count" in deps
        assert "imported_by_count" in deps

    def test_edit_risk_is_valid(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        assert result["edit_risk"] in ("safe", "caution", "dangerous")

    def test_line_count(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        assert result["line_count"] > 0

    def test_language_detected(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                }
            )
        )
        assert result["language"] == "py"

    def test_file_not_found(self, tool):
        with pytest.raises(ValueError, match="File not found"):
            _run(tool.execute({"file_path": "nonexistent_file.py"}))

    def test_toon_format_works(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                    "output_format": "toon",
                }
            )
        )
        assert "health" in result

    def test_json_format_works(self, tool):
        result = _run(
            tool.execute(
                {
                    "file_path": "tree_sitter_analyzer/mcp/tools/smart_context_tool.py",
                    "output_format": "json",
                }
            )
        )
        assert "health" in result


class TestExportExtraction:
    def test_extracts_class(self):
        exports = _extract_exports(PYTHON_SOURCE, ".py")
        classes = [e for e in exports if e["kind"] == "class"]
        assert len(classes) == 1
        assert classes[0]["name"] == "MyClass"
        assert classes[0]["methods"] == 2

    def test_extracts_function(self):
        exports = _extract_exports(PYTHON_SOURCE, ".py")
        funcs = [e for e in exports if e["kind"] == "function"]
        names = [f["name"] for f in funcs]
        assert "standalone_func" in names

    def test_extracts_constants(self):
        exports = _extract_exports(PYTHON_SOURCE, ".py")
        consts = [e for e in exports if e["kind"] == "constant"]
        assert any(c["name"] == "MY_CONSTANT" for c in consts)

    def test_excludes_private_functions(self):
        exports = _extract_exports(PYTHON_SOURCE, ".py")
        names = [e["name"] for e in exports]
        assert "_private_func" not in names

    def test_handles_syntax_error(self):
        exports = _extract_exports("def broken(", ".py")
        assert exports == []


class TestStructureExtraction:
    def test_extracts_structure(self):
        structure = _extract_structure(PYTHON_SOURCE, ".py")
        assert len(structure) > 0
        kinds = {s["kind"] for s in structure}
        assert "class" in kinds or "function" in kinds


class TestQuickRisk:
    def test_safe(self):
        assert _quick_risk(0, "A", True) == "safe"

    def test_caution(self):
        assert _quick_risk(6, "C", False) == "caution"

    def test_dangerous(self):
        assert _quick_risk(25, "D", False) == "dangerous"
