"""Tests for CodeGraph Navigate tool — unified symbol navigation hub."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_navigate_tool import (
    CodeGraphNavigateTool,
    _transitive_callees,
    _transitive_callers,
)


@pytest.fixture
def tool():
    return CodeGraphNavigateTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphNavigateTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_navigate"

    def test_schema_requires_symbol(self, tool):
        schema = tool.get_tool_schema()
        assert "symbol" in schema["properties"]
        assert "symbol" in schema["required"]

    def test_schema_modes(self, tool):
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        assert "definition" in modes
        assert "references" in modes
        assert "hierarchy" in modes
        assert "full" in modes


class TestValidateArguments:
    def test_missing_symbol_raises(self, tool):
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({})

    def test_valid_symbol(self, tool):
        assert tool.validate_arguments({"symbol": "foo"}) is True


class TestExecuteDefinition:
    @pytest.mark.asyncio
    async def test_definition_no_cache(self, tool):
        with patch.object(tool, "get_cache", return_value=None):
            result = await tool.execute({"symbol": "foo", "mode": "definition"})
        assert result["success"] is True
        assert result["definition"]["found"] is False

    @pytest.mark.asyncio
    async def test_definition_with_cache(self, tool_with_root):
        mock_cache = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (10,)
        mock_cache.get_conn.return_value = mock_conn

        mock_resolver = MagicMock()
        mock_result = MagicMock()
        mock_result.definitions = []
        mock_result.resolved_via = "fts"
        mock_resolver.resolve.return_value = mock_result

        with (
            patch.object(tool_with_root, "get_cache", return_value=mock_cache),
            patch(
                "tree_sitter_analyzer.symbol_resolver.SymbolResolver",
                return_value=mock_resolver,
            ),
        ):
            result = await tool_with_root.execute(
                {"symbol": "parse_tree", "mode": "definition"}
            )
        assert result["success"] is True
        assert "definition" in result


class TestExecuteHierarchy:
    @pytest.mark.asyncio
    async def test_hierarchy_no_graph(self, tool):
        mock_graph = MagicMock()
        mock_graph.build.side_effect = Exception("no project")
        with patch.object(tool, "get_call_graph", return_value=mock_graph):
            result = await tool.execute({"symbol": "foo", "mode": "hierarchy"})
        assert result["success"] is True
        assert result["hierarchy"]["callers"] == []
        assert result["hierarchy"]["callees"] == []

    @pytest.mark.asyncio
    async def test_hierarchy_with_callers_and_callees(self, tool):
        mock_graph = MagicMock()
        mock_graph.callers_of.return_value = [
            {"name": "bar", "file": "b.py", "line": 5, "language": "python"},
        ]
        mock_graph.callees_of.return_value = [
            {"name": "baz", "file": "c.py", "line": 10, "language": "python"},
        ]
        with patch.object(tool, "get_call_graph", return_value=mock_graph):
            result = await tool.execute(
                {"symbol": "foo", "mode": "hierarchy", "depth": 1}
            )
        assert result["success"] is True
        assert result["hierarchy"]["caller_count"] == 1
        assert result["hierarchy"]["callees_count"] == 1
        assert result["hierarchy"]["callers"][0]["name"] == "bar"
        assert result["hierarchy"]["callees"][0]["name"] == "baz"

    @pytest.mark.asyncio
    async def test_hierarchy_transitive_depth(self, tool):
        mock_graph = MagicMock()
        mock_graph.build.return_value = None

        def callers_of(name, fp=None):
            if name == "foo":
                return [
                    {"name": "bar", "file": "b.py", "line": 5, "language": "python"},
                ]
            if name == "bar":
                return [
                    {"name": "baz", "file": "c.py", "line": 10, "language": "python"},
                ]
            return []

        mock_graph.callers_of.side_effect = callers_of
        mock_graph.callees_of.return_value = []
        with patch.object(tool, "get_call_graph", return_value=mock_graph):
            result = await tool.execute(
                {"symbol": "foo", "mode": "hierarchy", "depth": 3}
            )
        assert result["success"] is True
        tc = result["hierarchy"]["transitive_callers"]
        names = [r["name"] for r in tc]
        assert "bar" in names
        assert "baz" in names


class TestExecuteFull:
    @pytest.mark.asyncio
    async def test_full_mode(self, tool):
        mock_graph = MagicMock()
        mock_graph.build.return_value = None
        mock_graph.callers_of.return_value = []
        mock_graph.callees_of.return_value = []
        with (
            patch.object(tool, "get_cache", return_value=None),
            patch.object(tool, "get_call_graph", return_value=mock_graph),
        ):
            result = await tool.execute({"symbol": "foo", "mode": "full"})
        assert result["success"] is True
        assert "definition" in result
        assert "references" in result
        assert "hierarchy" in result


class TestExecuteOutputFormat:
    @pytest.mark.asyncio
    async def test_toon_format(self, tool):
        mock_graph = MagicMock()
        mock_graph.build.side_effect = Exception("no project")
        with patch.object(tool, "get_call_graph", return_value=mock_graph):
            result = await tool.execute(
                {"symbol": "foo", "mode": "hierarchy", "output_format": "toon"}
            )
        assert result["format"] == "toon"
        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_json_format(self, tool):
        mock_graph = MagicMock()
        mock_graph.build.side_effect = Exception("no project")
        with patch.object(tool, "get_call_graph", return_value=mock_graph):
            result = await tool.execute(
                {"symbol": "foo", "mode": "hierarchy", "output_format": "json"}
            )
        assert "toon_content" not in result
        assert "success" in result


class TestTransitiveHelpers:
    def test_transitive_callers_bounded(self):
        graph = MagicMock()

        def callers_of(name, fp=None):
            return [
                {
                    "name": f"{name}_caller",
                    "file": "f.py",
                    "line": 1,
                    "language": "python",
                }
            ]

        graph.callers_of.side_effect = callers_of
        result = _transitive_callers(graph, "root", None, 3)
        assert len(result) <= 50

    def test_transitive_callees_no_cycles(self):
        graph = MagicMock()

        def callees_of(name, fp=None):
            if name == "a":
                return [{"name": "b", "file": "f.py", "line": 1, "language": "python"}]
            if name == "b":
                return [{"name": "a", "file": "f.py", "line": 5, "language": "python"}]
            return []

        graph.callees_of.side_effect = callees_of
        result = _transitive_callees(graph, "a", None, 5)
        names = [r["name"] for r in result]
        assert names.count("a") <= 1
        assert names.count("b") <= 1


class TestProjectRootChanged:
    def test_resets_caches(self, tool_with_root):
        tool_with_root._call_graph = MagicMock()  # noqa: SLF001 — test setup write
        tool_with_root._cache = MagicMock()  # noqa: SLF001 — test setup write
        tool_with_root._on_project_root_changed(None)
        assert not tool_with_root.call_graph_initialized
        assert not tool_with_root.cache_initialized
