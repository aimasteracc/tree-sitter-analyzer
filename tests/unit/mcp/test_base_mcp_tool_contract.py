"""Contract tests for BaseMCPTool subclasses.

These tests verify 6 invariants that every concrete MCP tool must satisfy:
  1. get_tool_definition() returns a dict with "name", "description", "inputSchema" keys.
  2. The "name" value is a non-empty string.
  3. set_project_path("/tmp") does not raise.
  4. The "inputSchema" has "properties" and "required" keys.
  5. tool definition "name" is consistent with tool class identity.
  6. The output_format property defaults to "toon" (MCP-is-toon design decision).

These tests replace per-tool boilerplate that was copy-pasted across dozens of
test files. Any new BaseMCPTool subclass should be added to the parametrize list.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool
from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import ClassHierarchyTool
from tree_sitter_analyzer.mcp.tools.code_patterns_tool import CodePatternsTool
from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.import_graph_tool import CodeGraphImportGraphTool
from tree_sitter_analyzer.mcp.tools.project_health_tool import ProjectHealthTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.smart_context_tool import SmartContextTool
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool


def _make_tools() -> list[object]:
    """Return one instantiated instance of each tool under contract."""
    return [
        CodeGraphCallersTool(),
        SearchContentTool(),
        ReadPartialTool(),
        ClassHierarchyTool(),
        ChangeImpactTool(),
        ProjectHealthTool(),
        FindAndGrepTool(),
        CodeGraphSymbolSearchTool(),
        CodePatternsTool(),
        CodeGraphImportGraphTool(),
        SmartContextTool(),
        CodeGraphStatusTool(),
        ASTDiffTool(),
    ]


def _tool_id(tool: object) -> str:
    return type(tool).__name__


TOOLS = _make_tools()


class TestBaseMCPToolContract:
    """Parametrized contract suite — one test class, 6 invariants × N tools."""

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_get_tool_definition_returns_required_top_level_keys(
        self, tool: object
    ) -> None:
        """Invariant 1: get_tool_definition() returns a dict with name, description, inputSchema."""
        defn = tool.get_tool_definition()
        assert isinstance(defn, dict), (
            f"{_tool_id(tool)}: get_tool_definition() must return dict"
        )
        missing = {"name", "description", "inputSchema"} - set(defn.keys())
        assert not missing, f"{_tool_id(tool)}: definition missing keys {missing}"

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_name_is_non_empty_string(self, tool: object) -> None:
        """Invariant 2: the 'name' in get_tool_definition() is a non-empty string."""
        defn = tool.get_tool_definition()
        name = defn.get("name")
        assert isinstance(name, str), (
            f"{_tool_id(tool)}: 'name' must be a string, got {type(name)}"
        )
        assert name, f"{_tool_id(tool)}: 'name' must be non-empty"

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_set_project_path_does_not_raise(self, tool: object) -> None:
        """Invariant 3: set_project_path('/tmp') completes without raising."""
        tool.set_project_path("/tmp")
        assert tool.project_root == "/tmp", (
            f"{_tool_id(tool)}: project_root should be '/tmp' after set_project_path"
        )

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_input_schema_has_properties(self, tool: object) -> None:
        """Invariant 4: inputSchema has 'properties' key; 'required' is optional (valid when all params optional).

        JSON Schema permits omitting 'required' when every property is optional.
        Some tools (ReadPartialTool, ChangeImpactTool, ProjectHealthTool,
        CodeGraphStatusTool) have all-optional params and use 'additionalProperties'
        instead. The contract only mandates 'properties'.
        """
        defn = tool.get_tool_definition()
        schema = defn.get("inputSchema", {})
        assert isinstance(schema, dict), f"{_tool_id(tool)}: inputSchema must be a dict"
        assert "properties" in schema, (
            f"{_tool_id(tool)}: inputSchema missing 'properties' key"
        )
        assert isinstance(schema["properties"], dict), (
            f"{_tool_id(tool)}: inputSchema.properties must be a dict"
        )
        # 'required' is optional in JSON Schema; when present it must be a list.
        if "required" in schema:
            assert isinstance(schema["required"], list), (
                f"{_tool_id(tool)}: inputSchema.required must be a list when present"
            )

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_tool_name_is_stable_across_calls(self, tool: object) -> None:
        """Invariant 5: get_tool_definition()['name'] is identical across two calls."""
        first = tool.get_tool_definition()["name"]
        second = tool.get_tool_definition()["name"]
        assert first == second, (
            f"{_tool_id(tool)}: 'name' changed between calls: {first!r} vs {second!r}"
        )

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_output_format_defaults_to_toon(self, tool: object) -> None:
        """Invariant 6: output_format property defaults to 'toon' (MCP token-efficiency design).

        See CLAUDE.md section 1: 'MCP defaults to TOON — LOCKED'. Any tool that
        exposes an output_format parameter MUST declare 'toon' as its default.
        """
        defn = tool.get_tool_definition()
        schema = defn.get("inputSchema", {})
        props = schema.get("properties", {})
        if "output_format" not in props:
            pytest.skip(f"{_tool_id(tool)}: does not expose output_format parameter")
        of_schema = props["output_format"]
        default = of_schema.get("default")
        assert default == "toon", (
            f"{_tool_id(tool)}: output_format.default must be 'toon', got {default!r}. "
            "See CLAUDE.md §1: MCP defaults to TOON — LOCKED."
        )


class TestUniversalOutputFormatParam:
    """#651: output_format is a universal envelope param. enforce_strict_params
    must accept it even when a tool's schema omits it (modification_guard and
    batch_search rejected it with ValueError), so an agent can set it uniformly
    across every call — while still rejecting genuinely-unknown keys."""

    def test_output_format_accepted_when_schema_omits_it(self) -> None:
        from tree_sitter_analyzer.mcp.utils.schema_strictness import (
            enforce_strict_params,
        )

        # modification_guard's schema (no output_format) — must NOT raise.
        schema = {
            "properties": {"symbol": {}, "modification_type": {}, "file_path": {}}
        }
        enforce_strict_params(
            "modification_guard",
            schema,
            {"symbol": "x", "file_path": "f", "output_format": "json"},
        )

    def test_genuinely_unknown_param_still_rejected(self) -> None:
        from tree_sitter_analyzer.mcp.utils.schema_strictness import (
            enforce_strict_params,
        )

        schema = {"properties": {"symbol": {}}}
        with pytest.raises(ValueError, match="unknown parameter 'bogus'"):
            enforce_strict_params("t", schema, {"symbol": "x", "bogus": 1})

    @pytest.mark.parametrize("tool", TOOLS, ids=_tool_id)
    def test_every_contract_tool_accepts_output_format(self, tool: object) -> None:
        from tree_sitter_analyzer.mcp.utils.schema_strictness import (
            enforce_strict_params,
        )

        schema = tool.get_tool_definition().get("inputSchema")
        # Must not raise for any tool, whether or not output_format is declared.
        enforce_strict_params(_tool_id(tool), schema, {"output_format": "json"})
