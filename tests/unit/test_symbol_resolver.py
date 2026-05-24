#!/usr/bin/env python3
"""Tests for symbol_resolver engine and codegraph_resolve MCP tool."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.symbol_resolve_tool import (
    CodeGraphSymbolResolveTool,
)
from tree_sitter_analyzer.symbol_resolver import SymbolResolver


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

    (project / "models.py").write_text(
        "class User:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "\n"
        "    def display(self):\n"
        "        return self.name\n"
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    cache.close()
    return project


class TestSymbolResolverEngine:
    def test_resolve_function(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.resolve("handle_request")
        assert len(result.definitions) >= 1
        assert result.definitions[0].name == "handle_request"
        assert result.definitions[0].kind == "function"
        assert "app.py" in result.definitions[0].file
        cache.close()

    def test_resolve_class(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.resolve("UserService")
        assert len(result.definitions) >= 1
        assert result.definitions[0].name == "UserService"
        assert result.definitions[0].kind == "class"
        cache.close()

    def test_resolve_method(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.resolve("get_user")
        assert len(result.definitions) >= 1
        assert result.definitions[0].name == "get_user"
        cache.close()

    def test_resolve_nonexistent(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.resolve("nonexistent_symbol_xyz")
        assert len(result.definitions) == 0
        cache.close()

    def test_resolve_to_dict(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.resolve("UserService")
        d = result.to_dict()
        assert d["symbol"] == "UserService"
        assert d["definition_count"] >= 1
        assert len(d["definitions"]) >= 1
        assert "file" in d["definitions"][0]
        cache.close()

    def test_find_references(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.find_references("get_user")
        assert len(result.definitions) >= 1
        assert len(result.references) >= 0
        d = result.to_dict()
        assert d["symbol"] == "get_user"
        assert "reference_count" in d
        cache.close()

    def test_qualified_name_resolution(self, indexed_project):
        cache = ASTCache(str(indexed_project))
        resolver = SymbolResolver(cache)
        result = resolver.resolve("UserService.get_user")
        assert len(result.definitions) >= 1
        assert result.definitions[0].name == "get_user"
        cache.close()

    def test_definition_location_to_dict(self):
        from tree_sitter_analyzer.symbol_resolver import DefinitionLocation

        loc = DefinitionLocation(
            file="app.py",
            name="Foo",
            kind="class",
            line=1,
            end_line=10,
            language="python",
            confidence=0.9,
            context="class Foo:",
        )
        d = loc.to_dict()
        assert d["file"] == "app.py"
        assert d["name"] == "Foo"
        assert d["confidence"] == 0.9
        assert d["context"] == "class Foo:"

    def test_reference_location_to_dict(self):
        from tree_sitter_analyzer.symbol_resolver import ReferenceLocation

        loc = ReferenceLocation(
            file="app.py",
            name="Foo",
            kind="function",
            line=5,
            end_line=5,
            language="python",
            reference_type="call_site",
        )
        d = loc.to_dict()
        assert d["file"] == "app.py"
        assert d["reference_type"] == "call_site"


class TestCodeGraphSymbolResolveToolDefinition:
    def test_tool_name(self):
        tool = CodeGraphSymbolResolveTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_resolve"

    def test_schema_requires_symbol(self):
        tool = CodeGraphSymbolResolveTool()
        schema = tool.get_tool_schema()
        assert "symbol" in schema["properties"]
        assert "symbol" in schema["required"]

    def test_schema_has_mode(self):
        tool = CodeGraphSymbolResolveTool()
        schema = tool.get_tool_schema()
        mode_prop = schema["properties"]["mode"]
        assert "resolve" in mode_prop["enum"]
        assert "references" in mode_prop["enum"]


class TestCodeGraphSymbolResolveValidation:
    def test_validate_requires_symbol(self):
        tool = CodeGraphSymbolResolveTool()
        with pytest.raises(ValueError, match="symbol is required"):
            tool.validate_arguments({})

    def test_validate_passes_with_symbol(self):
        tool = CodeGraphSymbolResolveTool()
        assert tool.validate_arguments({"symbol": "UserService"}) is True


@pytest.mark.asyncio
class TestCodeGraphSymbolResolveExecution:
    async def test_resolve_mode(self, indexed_project):
        tool = CodeGraphSymbolResolveTool(str(indexed_project))
        result = await tool.execute(
            {"symbol": "UserService", "mode": "resolve", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["symbol"] == "UserService"
        assert result["definition_count"] >= 1
        assert len(result["definitions"]) >= 1
        assert "file" in result["definitions"][0]

    async def test_references_mode(self, indexed_project):
        tool = CodeGraphSymbolResolveTool(str(indexed_project))
        result = await tool.execute(
            {"symbol": "get_user", "mode": "references", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["definition_count"] >= 1
        assert "reference_count" in result
        assert "references" in result

    async def test_nonexistent_symbol(self, indexed_project):
        tool = CodeGraphSymbolResolveTool(str(indexed_project))
        result = await tool.execute(
            {"symbol": "does_not_exist", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["definition_count"] == 0
        assert "hint" in result

    async def test_toon_format(self, indexed_project):
        tool = CodeGraphSymbolResolveTool(str(indexed_project))
        result = await tool.execute(
            {"symbol": "UserService", "output_format": "toon"}
        )
        assert "toon_content" in result

    async def test_empty_cache_error(self, tmp_path):
        project = tmp_path / "empty"
        project.mkdir()
        tool = CodeGraphSymbolResolveTool(str(project))
        result = await tool.execute(
            {"symbol": "anything", "output_format": "json"}
        )
        assert result["success"] is False
        assert "empty" in result["error"].lower()

    async def test_resolve_function_definition(self, indexed_project):
        tool = CodeGraphSymbolResolveTool(str(indexed_project))
        result = await tool.execute(
            {"symbol": "format_user", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["definition_count"] >= 1
        defs = result["definitions"]
        assert any("utils.py" in d["file"] for d in defs)

    async def test_resolve_class_in_different_file(self, indexed_project):
        tool = CodeGraphSymbolResolveTool(str(indexed_project))
        result = await tool.execute(
            {"symbol": "User", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["definition_count"] >= 1
        defs = result["definitions"]
        assert any("models.py" in d["file"] for d in defs)
