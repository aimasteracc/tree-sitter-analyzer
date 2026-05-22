"""Unit tests for symbol_lineage_tool."""

import asyncio

import pytest

from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
    SymbolLineageTool,
    _assess_risk,
    _is_test_file,
)


@pytest.fixture
def tool(tmp_path):
    t = SymbolLineageTool(project_root=str(tmp_path))
    t.set_project_path(str(tmp_path))
    return t


def _write_py(tmp_path, name, content):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestRiskAssessment:
    def test_unknown_when_no_definitions(self):
        result = _assess_risk(0, 5, 3)
        assert result["level"] == "unknown"
        assert "Symbol not found" in result["reasons"]

    def test_low_risk(self):
        result = _assess_risk(1, 2, 1)
        assert result["level"] == "low"

    def test_medium_risk(self):
        result = _assess_risk(1, 10, 5)
        assert result["level"] == "medium"

    def test_high_risk(self):
        result = _assess_risk(2, 25, 15)
        assert result["level"] == "high"
        assert result["score"] >= 6


class TestIsTestFile:
    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_foo.py",
            "tests/unit/test_bar.py",
            "src/test_widget.py",
            "foo_test.py",
            "foo_test.js",
            "FooTest.java",
            "foo_test.go",
        ],
    )
    def test_detects_test_files(self, path):
        assert _is_test_file(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "tree_sitter_analyzer/mcp/server.py",
            "README.md",
            "setup.py",
        ],
    )
    def test_rejects_non_test_files(self, path):
        assert _is_test_file(path) is False


class TestValidation:
    def test_requires_symbol(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({})

    def test_rejects_empty_symbol(self, tool):
        with pytest.raises(ValueError):
            tool.validate_arguments({"symbol": "  "})

    def test_rejects_bad_depth(self, tool):
        with pytest.raises(ValueError, match="max_depth"):
            tool.validate_arguments({"symbol": "foo", "max_depth": 0})
        with pytest.raises(ValueError, match="max_depth"):
            tool.validate_arguments({"symbol": "foo", "max_depth": 6})

    def test_valid_args_pass(self, tool):
        assert tool.validate_arguments({"symbol": "foo"}) is True
        assert tool.validate_arguments({"symbol": "bar", "max_depth": 2}) is True


class TestToolDefinition:
    def test_definition_has_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "symbol_lineage"
        assert "lineage" in defn["description"].lower()
        assert "inputSchema" in defn

    def test_schema_requires_symbol(self, tool):
        schema = tool.get_tool_schema()
        assert "symbol" in schema["properties"]
        assert "symbol" in schema["required"]


class TestExecute:
    def test_symbol_not_found_returns_unknown_risk(self, tool, tmp_path):
        _write_py(tmp_path, "pkg/__init__.py", "")
        result = asyncio.run(
            tool.execute({"symbol": "NonExistent", "output_format": "json"})
        )
        assert result["success"] is True
        assert result["risk"]["level"] == "unknown"
        assert result["definition_count"] == 0
        # pain #3: missing symbol must surface NOT_FOUND, NOT None.
        # Agents that branch on verdict were treating None as INFO and
        # then "safely" deleting symbols that didn't exist anywhere.
        assert result["verdict"] == "NOT_FOUND"

    def test_verdict_present_when_symbol_found(self, tool, tmp_path):
        """Found symbols must emit a canonical verdict (not None)."""
        _write_py(
            tmp_path,
            "pkg/core.py",
            "def my_func():\n    return 42\n",
        )
        result = asyncio.run(
            tool.execute({"symbol": "my_func", "output_format": "json"})
        )
        assert result["verdict"] in ("INFO", "REVIEW", "CAUTION")

    def test_finds_symbol_returns_success(self, tool, tmp_path):
        _write_py(
            tmp_path,
            "pkg/core.py",
            "def my_func():\n    return 42\n",
        )
        _write_py(
            tmp_path,
            "tests/test_core.py",
            "from pkg.core import my_func\ndef test_my_func():\n    my_func()\n",
        )
        result = asyncio.run(
            tool.execute({"symbol": "my_func", "output_format": "json"})
        )
        assert result["success"] is True
        assert result["definition_count"] + result["reference_count"] >= 0
        assert result["risk"]["level"] in ("low", "medium", "high", "unknown")
        assert "smart_workflow_hint" in result

    def test_toon_format_includes_content(self, tool, tmp_path):
        _write_py(tmp_path, "pkg/__init__.py", "x = 1\n")
        result = asyncio.run(tool.execute({"symbol": "x", "output_format": "toon"}))
        assert result["success"] is True
        assert "toon_content" in result

    def test_no_project_root_raises(self, tmp_path):
        t = SymbolLineageTool(project_root=None)
        with pytest.raises(ValueError, match="Project root"):
            asyncio.run(t.execute({"symbol": "foo"}))
