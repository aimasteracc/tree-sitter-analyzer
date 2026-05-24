#!/usr/bin/env python3
"""Tests for codegraph_symbol_search MCP tool — FTS5-powered instant symbol lookup."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import CodeGraphSymbolSearchTool


@pytest.fixture
def indexed_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    (project / "app.py").write_text(
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return self._find_user(user_id)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        pass\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    return svc.get_user(1)\n"
    )

    (project / "utils.py").write_text(
        "def format_user(user):\n"
        "    return str(user)\n"
        "\n"
        "def validate_input(data):\n"
        "    return bool(data)\n"
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    cache.close()
    return project


class TestCodeGraphSymbolSearchToolDefinition:
    def test_tool_name(self):
        tool = CodeGraphSymbolSearchTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_symbol_search"

    def test_schema_requires_query(self):
        tool = CodeGraphSymbolSearchTool()
        schema = tool.get_tool_schema()
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_schema_has_kind_filter(self):
        tool = CodeGraphSymbolSearchTool()
        schema = tool.get_tool_schema()
        kind_prop = schema["properties"]["kind"]
        assert "function" in kind_prop["enum"]
        assert "class" in kind_prop["enum"]


class TestCodeGraphSymbolSearchValidation:
    def test_validate_requires_query(self):
        tool = CodeGraphSymbolSearchTool()
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments({})

    def test_validate_passes_with_query(self):
        tool = CodeGraphSymbolSearchTool()
        assert tool.validate_arguments({"query": "UserService"}) is True


@pytest.mark.asyncio
class TestCodeGraphSymbolSearchExecution:
    async def test_exact_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] >= 1
        names = [r["name"] for r in result["results"]]
        assert "UserService" in names

    async def test_fuzzy_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~user", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] >= 1

    async def test_wildcard_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "handle_*", "output_format": "json"})
        assert result["success"] is True
        names = [r["name"] for r in result["results"]]
        assert "handle_request" in names

    async def test_language_filter(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "UserService", "language": "python", "output_format": "json"}
        )
        assert result["success"] is True
        assert result.get("language_filter") == "python"

    async def test_kind_filter_function(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "~user", "kind": "function", "output_format": "json"}
        )
        assert result["success"] is True
        for r in result["results"]:
            assert r["kind"] == "function"

    async def test_kind_filter_class(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "UserService", "kind": "class", "output_format": "json"}
        )
        assert result["success"] is True
        for r in result["results"]:
            assert r["kind"] == "class"

    async def test_limit(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "~", "limit": 1, "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] <= 1

    async def test_no_match(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute(
            {"query": "NonExistentSymbol", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["match_count"] == 0

    async def test_result_has_file_and_line(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert result["match_count"] >= 1
        hit = result["results"][0]
        assert "file" in hit
        assert "line" in hit
        assert hit["line"] > 0

    async def test_toon_output_format(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "toon"})
        assert result["success"] is True
        assert "toon_content" in result

    async def test_data_source_field(self, indexed_project):
        tool = CodeGraphSymbolSearchTool(str(indexed_project))
        result = await tool.execute({"query": "UserService", "output_format": "json"})
        assert "data_source" in result
        assert result["data_source"] in ("fts5", "linear_scan")


@pytest.mark.asyncio
class TestCodeGraphSymbolSearchNoCache:
    async def test_search_on_empty_project(self, tmp_path):
        project = tmp_path / "empty_proj"
        project.mkdir()
        tool = CodeGraphSymbolSearchTool(str(project))
        result = await tool.execute({"query": "anything", "output_format": "json"})
        assert result["success"] is True
        assert result["match_count"] == 0


class TestCodeGraphSymbolSearchRegistration:
    def test_tool_registered_in_server(self):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        assert "codegraph_symbol_search" in tools

    def test_callers_registered_in_server(self):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        assert "codegraph_callers" in tools

    def test_callees_registered_in_server(self):
        from tree_sitter_analyzer.mcp.server import _create_tool_registry

        _, tools = _create_tool_registry(None)
        assert "codegraph_callees" in tools
