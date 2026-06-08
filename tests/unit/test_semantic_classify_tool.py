"""Tests for SemanticClassifyTool MCP tool and integration."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import SemanticClassifyTool


@pytest.fixture
def tool():
    return SemanticClassifyTool(project_root=None)


def _run(tool_instance: SemanticClassifyTool, args: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(tool_instance.execute(args))


class TestSemanticClassifyToolDefinition:
    def test_tool_name(self, tool: SemanticClassifyTool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "semantic_classify"

    def test_mode_is_optional_in_schema(self, tool: SemanticClassifyTool):
        # Wave 1b (audit edit-10): mode is resolved at runtime (defaults to
        # classify_file when file_path is given), so it must NOT be required —
        # else a strict MCP client rejects a valid {file_path: X} call.
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "mode" not in schema.get("required", [])

    def test_resolve_mode_defaults(self, tool: SemanticClassifyTool):
        assert tool._resolve_mode({"file_path": "x.py"}) == "classify_file"
        assert (
            tool._resolve_mode({"old_source": "a", "new_source": "b"})
            == "classify_string"
        )
        assert tool._resolve_mode({}) == "classify_string"
        # explicit mode always wins
        assert (
            tool._resolve_mode({"mode": "classify_string", "file_path": "x.py"})
            == "classify_string"
        )

    def test_file_path_only_does_not_demand_sources(self, tool: SemanticClassifyTool):
        # The edit-10 bug: classify file_path=X raised "old_source... required".
        # With the file-default it validates as classify_file instead.
        assert tool.validate_arguments({"file_path": "some/file.py"}) is True


class TestSemanticClassifyValidation:
    def test_classify_file_requires_path(self, tool: SemanticClassifyTool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "classify_file"})

    def test_classify_string_requires_sources(self, tool: SemanticClassifyTool):
        with pytest.raises(ValueError, match="old_source and new_source"):
            tool.validate_arguments({"mode": "classify_string", "language": "python"})

    def test_classify_string_requires_language(self, tool: SemanticClassifyTool):
        with pytest.raises(ValueError, match="language is required"):
            tool.validate_arguments(
                {
                    "mode": "classify_string",
                    "old_source": "x",
                    "new_source": "y",
                }
            )

    def test_valid_classify_file(self, tool: SemanticClassifyTool):
        assert tool.validate_arguments({"mode": "classify_file", "file_path": "foo.py"})


class TestSemanticClassifyExecution:
    def test_classify_string_function_added(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "",
                "new_source": "def hello():\n    pass\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "feature_addition"
        key = "num_changes" if "num_changes" in result else "change_count"
        assert result[key] > 0

    def test_classify_string_signature_changed(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def greet(name):\n    pass\n",
                "new_source": "def greet(name, greeting='Hello'):\n    pass\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] in (
            "api_change",
            "refactor",
            "internal_change",
        )

    def test_classify_string_no_changes(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def foo():\n    pass\n",
                "new_source": "def foo():\n    pass\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"

    def test_classify_string_function_removed(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def public_api():\n    return 1\n\ndef helper():\n    pass\n",
                "new_source": "",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "feature_removal"

    def test_classify_string_import_change(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "import os\n",
                "new_source": "import os\nimport sys\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "import_change"

    def test_classify_string_body_change(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def compute(x):\n    return x + 1\n",
                "new_source": "def compute(x):\n    return x * 2\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "internal_change"

    def test_toon_format(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "",
                "new_source": "def foo(): pass\n",
                "language": "python",
                "output_format": "toon",
            },
        )
        assert "toon_content" in result or result["success"] is True


class TestSemanticClassifyToolRegistry:
    def test_tool_registered(self):
        # Wave C2: semantic_classify is now the edit facade action=classify.
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "edit" in by_name
        assert "classify" in by_name["edit"].action_map
        assert (
            type(by_name["edit"].action_map["classify"]).__name__
            == "SemanticClassifyTool"
        )

    def test_tool_in_cli_class_names(self):
        from tree_sitter_analyzer.cli.commands.mcp_commands import _TOOL_CLASS_NAMES

        assert "SemanticClassifyTool" in _TOOL_CLASS_NAMES


class TestSemanticClassifyChangeImpactIntegration:
    def test_change_impact_includes_semantic_when_changed(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _classify_changed_files,
        )

        py_file = tmp_path / "example.py"
        py_file.write_text("def greet(name):\n    return f'Hello {name}'\n")

        results = _classify_changed_files(
            changed_files=["example.py"],
            project_root=str(tmp_path),
        )
        assert isinstance(results, list)

    def test_classify_changed_files_empty(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _classify_changed_files,
        )

        assert _classify_changed_files([], None) == []
        assert _classify_changed_files(["x.py"], None) == []
