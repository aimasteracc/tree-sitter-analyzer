"""Tests for codegraph_xref MCP tool — instant multi-dimension cross-reference."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_xref_tool import CodeGraphXRefTool


@pytest.fixture
def tool():
    return CodeGraphXRefTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphXRefTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_xref"

    def test_description_mentions_codegraph_parity(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "CodeGraph" in desc

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False

    def test_schema_mode_default_symbol(self, tool):
        mode_prop = tool.get_tool_schema()["properties"]["mode"]
        assert mode_prop["default"] == "symbol"
        assert set(mode_prop["enum"]) == {"symbol", "file"}

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )


class TestValidation:
    def test_symbol_mode_requires_symbol(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({"mode": "symbol"})

    def test_file_mode_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "file"})

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "unknown", "symbol": "foo"})

    def test_valid_symbol_mode(self, tool):
        assert tool.validate_arguments({"mode": "symbol", "symbol": "foo"}) is True

    def test_valid_file_mode(self, tool):
        assert tool.validate_arguments({"mode": "file", "file_path": "app.py"}) is True


@pytest.mark.asyncio
class TestExecute:
    async def test_symbol_not_found_returns_not_found_verdict(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "symbol", "symbol": "no_such_symbol", "output_format": "json"}
        )
        assert result["verdict"] == "NOT_FOUND"

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "symbol", "symbol": "any_symbol"}
        )
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_symbol_mode_field_in_response(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "symbol", "symbol": "anything", "output_format": "json"}
        )
        assert result.get("mode") == "symbol"

    async def test_file_mode_field_in_response(self, tool_with_root, tmp_path):
        (tmp_path / "app.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "app.py", "output_format": "json"}
        )
        assert result.get("mode") == "file"


# ---------------------------------------------------------------------------
# #669 — xref file mode: agent_summary disambiguates the three counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestXRefFileModeAgentSummary:
    """#669: nav action=xref mode=file must include an agent_summary that
    disambiguates caller_count / import_dependent_count / file_dependent_count.

    Agents reading caller_count=0 mis-interpret it as 'no inbound deps' when
    import_dependent_count=5 already shows 5 files import the module.  A
    terse semantics note in agent_summary resolves the ambiguity.
    """

    async def test_file_mode_response_has_agent_summary(self, tool_with_root, tmp_path):
        """agent_summary must be present in file mode response."""
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        assert "agent_summary" in result

    async def test_file_mode_agent_summary_has_count_semantics(
        self, tool_with_root, tmp_path
    ):
        """agent_summary.count_semantics must be present and explain the three counts."""
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        summary = result.get("agent_summary", {})
        assert "count_semantics" in summary

    async def test_file_mode_agent_summary_carries_canonical_fields(
        self, tool_with_root, tmp_path
    ):
        # Codex P2 (round 3): execute() is also reached on the CLI-bridged
        # direct path (mcp_commands/_helpers.py) where the MCP success post-hook
        # does NOT run. The agent_summary we add must therefore carry the
        # canonical verdict + summary_line itself — not just count_semantics —
        # or consumers branching on agent_summary break on the direct path.
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        summary = result["agent_summary"]
        assert summary["verdict"] == result["verdict"]
        assert isinstance(summary["summary_line"], str) and summary["summary_line"]

    async def test_file_mode_top_level_summary_line_on_direct_path(
        self, tool_with_root, tmp_path
    ):
        # Codex P2 (round 4): --codegraph-xref --format json consumers read the
        # TOP-LEVEL summary_line, which the MCP post-hook would normally mirror.
        # On the direct execute() path the post-hook never runs, so the tool must
        # set the top-level summary_line itself (not only inside agent_summary).
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        assert isinstance(result["summary_line"], str) and result["summary_line"]
        assert result["summary_line"] == result["agent_summary"]["summary_line"]

    async def test_file_mode_count_semantics_mentions_callers(
        self, tool_with_root, tmp_path
    ):
        """count_semantics must explain caller_count (function-level call sites)."""
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        semantics = result.get("agent_summary", {}).get("count_semantics", "")
        assert "caller_count" in semantics

    async def test_file_mode_count_semantics_mentions_import_dependents(
        self, tool_with_root, tmp_path
    ):
        """count_semantics must explain import_dependent_count (files importing this module)."""
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        semantics = result.get("agent_summary", {}).get("count_semantics", "")
        assert "import_dependent_count" in semantics

    async def test_file_mode_count_semantics_mentions_file_dependents(
        self, tool_with_root, tmp_path
    ):
        """count_semantics must explain file_dependent_count (files with call edges)."""
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        result = await tool_with_root.execute(
            {"mode": "file", "file_path": "mod.py", "output_format": "json"}
        )
        semantics = result.get("agent_summary", {}).get("count_semantics", "")
        assert "file_dependent_count" in semantics
