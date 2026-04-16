"""
Tests for MCP tool schema examples.

Verifies that key tools have examples in their inputSchema
to improve AI model tool-calling accuracy.
"""
from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool


class TestToolSchemaExamples:
    """Verify key MCP tools have examples in their inputSchema."""

    def test_check_code_scale_has_examples(self) -> None:
        schema = AnalyzeScaleTool().get_tool_schema()
        assert "examples" in schema
        assert len(schema["examples"]) >= 1
        assert "file_path" in schema["examples"][0]

    def test_analyze_code_structure_has_examples(self) -> None:
        schema = AnalyzeCodeStructureTool().get_tool_schema()
        assert "examples" in schema
        assert any("format_type" in ex for ex in schema["examples"])

    def test_get_code_outline_has_examples(self) -> None:
        schema = GetCodeOutlineTool().get_tool_schema()
        assert "examples" in schema
        assert len(schema["examples"]) >= 1

    def test_query_code_has_examples(self) -> None:
        definition = QueryTool().get_tool_definition()
        schema = definition["inputSchema"]
        assert "examples" in schema
        assert any("query_key" in ex for ex in schema["examples"])

    def test_trace_impact_has_examples(self) -> None:
        definition = TraceImpactTool().get_tool_definition()
        schema = definition["inputSchema"]
        assert "examples" in schema
        assert any("symbol_name" in ex for ex in schema["examples"])

    def test_examples_have_valid_paths(self) -> None:
        """All examples must have absolute-looking paths."""
        # Tools with get_tool_schema method
        schema_tools = [
            AnalyzeScaleTool,
            AnalyzeCodeStructureTool,
            GetCodeOutlineTool,
        ]
        # Tools with get_tool_definition method (inputSchema nested)
        definition_tools = [QueryTool, TraceImpactTool]

        for ToolClass in schema_tools:
            schema = ToolClass().get_tool_schema()
            for example in schema.get("examples", []):
                if "file_path" in example:
                    assert example["file_path"].startswith("/"), (
                        f"{ToolClass.__name__} example file_path must be absolute: "
                        f"{example['file_path']}"
                    )

        for ToolClass in definition_tools:
            schema = ToolClass().get_tool_definition()["inputSchema"]
            for example in schema.get("examples", []):
                if "file_path" in example:
                    assert example["file_path"].startswith("/"), (
                        f"{ToolClass.__name__} example file_path must be absolute: "
                        f"{example['file_path']}"
                    )
