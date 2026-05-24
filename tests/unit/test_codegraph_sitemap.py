"""Tests for codegraph_sitemap MCP tool and CLI parity."""

import contextlib
import sys
from io import StringIO

import pytest


@pytest.fixture()
def indexed_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app").mkdir()
    (project / "app" / "__init__.py").write_text("")
    (project / "app" / "main.py").write_text(
        '"""Main module."""\n'
        "import os\n"
        "\n\n"
        "def public_func(x: int) -> str:\n"
        "    return str(x)\n"
        "\n\n"
        "def _private_helper():\n"
        "    pass\n"
        "\n\n"
        "class UserController:\n"
        "    def get_user(self, uid):\n"
        "        return uid\n"
        "\n"
        "    def _internal(self):\n"
        "        pass\n"
    )
    (project / "app" / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(project))
    result = cache.index_project()
    assert result["indexed"] >= 2, f"Expected ≥2 indexed files, got {result}"
    cache.close()
    return project


class TestSitemapTool:
    def _make_tool(self, project_root):
        from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
            CodeGraphSitemapTool,
        )

        tool = CodeGraphSitemapTool(project_root=str(project_root))
        return tool

    @pytest.mark.asyncio
    async def test_full_mode(self, indexed_project):

        tool = self._make_tool(indexed_project)
        result = await tool.execute({"mode": "full", "output_format": "json"})
        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["file_count"] >= 2
        assert result["total_symbols"] > 0
        sitemap = result["sitemap"]
        assert "app" in sitemap

    @pytest.mark.asyncio
    async def test_api_mode(self, indexed_project):

        tool = self._make_tool(indexed_project)
        result = await tool.execute({"mode": "api", "output_format": "json"})
        assert result["success"] is True
        api = result["public_api"]
        names = [a["name"] for a in api]
        assert "public_func" in names
        assert "UserController" in names
        assert "_private_helper" not in names

    @pytest.mark.asyncio
    async def test_module_mode(self, indexed_project):

        tool = self._make_tool(indexed_project)
        result = await tool.execute({"mode": "module", "output_format": "json"})
        assert result["success"] is True
        modules = result["modules"]
        assert len(modules) >= 1
        mod_names = [m["directory"] for m in modules]
        assert any("app" in m for m in mod_names)

    @pytest.mark.asyncio
    async def test_flat_mode(self, indexed_project):

        tool = self._make_tool(indexed_project)
        result = await tool.execute({"mode": "flat", "output_format": "json"})
        assert result["success"] is True
        counts = result["counts"]
        assert counts.get("function", 0) > 0

    @pytest.mark.asyncio
    async def test_language_filter(self, indexed_project):

        tool = self._make_tool(indexed_project)
        result = await tool.execute(
            {"mode": "flat", "language": "python", "output_format": "json"}
        )
        assert result["success"] is True
        assert result.get("language_filter") == "python"

    @pytest.mark.asyncio
    async def test_directory_filter(self, indexed_project):

        tool = self._make_tool(indexed_project)
        result = await tool.execute(
            {"mode": "flat", "directory": "app", "output_format": "json"}
        )
        assert result["success"] is True
        assert result["file_count"] >= 1

    @pytest.mark.asyncio
    async def test_empty_cache(self, tmp_path):

        project = tmp_path / "empty"
        project.mkdir()
        tool = self._make_tool(project)
        result = await tool.execute({"mode": "full", "output_format": "json"})
        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"
        assert result["file_count"] == 0

    def test_tool_definition(self, indexed_project):
        tool = self._make_tool(indexed_project)
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_sitemap"
        assert "inputSchema" in defn

    def test_validate_arguments_bad_mode(self, indexed_project):
        tool = self._make_tool(indexed_project)
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "bogus"})


class TestSitemapCLI:
    def test_cli_smoke(self, indexed_project, monkeypatch):
        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                str(indexed_project),
                "--codegraph-sitemap",
                "--codegraph-sitemap-mode",
                "flat",
                "--format",
                "json",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        with contextlib.suppress(SystemExit):
            main()

    def test_cli_api_mode(self, indexed_project, monkeypatch):
        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                str(indexed_project),
                "--codegraph-sitemap",
                "--codegraph-sitemap-mode",
                "api",
                "--format",
                "json",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        with contextlib.suppress(SystemExit):
            main()

    def test_cli_module_mode(self, indexed_project, monkeypatch):
        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                str(indexed_project),
                "--codegraph-sitemap",
                "--codegraph-sitemap-mode",
                "module",
                "--format",
                "json",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        with contextlib.suppress(SystemExit):
            main()
