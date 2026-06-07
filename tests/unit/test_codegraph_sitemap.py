"""Tests for codegraph_sitemap MCP tool and CLI parity."""

import json
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


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows path drift — tracked separately",
)
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


@pytest.fixture()
def large_indexed_project(tmp_path):
    """A project whose symbol count exceeds the default max_symbols cap.

    Used to exercise F3 (overview-output-budget): a large repo must not emit
    an unbounded wall of symbols in api/flat sitemap modes.
    """
    project = tmp_path / "big"
    project.mkdir()
    pkg = project / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    # 60 files x 10 public functions = 600 public symbols, well over the
    # default cap of 300.
    for i in range(60):
        body = "".join(
            f"def func_{i}_{j}(a, b):\n    return a + b\n\n\n" for j in range(10)
        )
        (pkg / f"mod_{i:03d}.py").write_text(body)
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(project))
    result = cache.index_project()
    assert result["indexed"] >= 60, f"Expected ≥60 indexed files, got {result}"
    cache.close()
    return project


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows path drift in sitemap indexed-path fixtures; "
    "tracked: Windows-path-normalisation",
)
class TestSitemapOutputBudget:
    """F3: bound sitemap symbol output so large repos don't emit a wall of text."""

    def _make_tool(self, project_root):
        from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
            CodeGraphSitemapTool,
        )

        return CodeGraphSitemapTool(project_root=str(project_root))

    @pytest.mark.asyncio
    async def test_flat_mode_capped_by_default(self, large_indexed_project):
        tool = self._make_tool(large_indexed_project)
        result = await tool.execute(
            {"mode": "flat", "max_files": 500, "output_format": "json"}
        )
        # Schema keys unchanged.
        assert "symbols_by_kind" in result
        assert "counts" in result
        emitted = sum(len(v) for v in result["symbols_by_kind"].values())
        # Bounded by default well under the 600 indexed symbols.
        assert emitted <= 300, f"flat mode emitted {emitted} symbols, expected ≤300"
        # Explicit truncation marker present and pointing at the param.
        assert result["truncated"] is True
        assert "max_symbols" in result["truncation_note"]
        # counts still report the true (untruncated) totals.
        assert result["counts"].get("function", 0) >= 600

    @pytest.mark.asyncio
    async def test_api_mode_capped_by_default(self, large_indexed_project):
        tool = self._make_tool(large_indexed_project)
        result = await tool.execute(
            {"mode": "api", "max_files": 500, "output_format": "json"}
        )
        assert "public_api" in result
        assert len(result["public_api"]) <= 300
        assert result["truncated"] is True
        assert "max_symbols" in result["truncation_note"]
        # The scalar counts reflect the true totals, not the truncated list.
        assert result["public_function_count"] >= 600

    @pytest.mark.asyncio
    async def test_max_symbols_param_expands_list(self, large_indexed_project):
        tool = self._make_tool(large_indexed_project)
        result = await tool.execute(
            {
                "mode": "flat",
                "max_files": 500,
                "max_symbols": 1000,
                "output_format": "json",
            }
        )
        emitted = sum(len(v) for v in result["symbols_by_kind"].values())
        assert emitted >= 600, f"expected ≥600 with max_symbols=1000, got {emitted}"
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_small_project_not_truncated(self, indexed_project):
        tool = self._make_tool(indexed_project)
        result = await tool.execute({"mode": "flat", "output_format": "json"})
        assert result["truncated"] is False


def test_sitemap_builders_normalize_cached_slash_paths(tmp_path):
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
        CodeGraphSitemapTool,
    )

    tool = CodeGraphSitemapTool(project_root=str(tmp_path))
    files = [
        {
            "file": "app/main.py",
            "language": "python",
            "symbols": [],
            "structure": {},
            "symbol_count": 1,
            "functions": [{"kind": "function", "name": "run", "line": 1}],
            "classes": [],
            "imports": [],
        }
    ]

    assert "main.py" in tool._build_full_map(files)["sitemap"]["app"]
    assert tool._build_module_metrics(files)["modules"][0]["directory"] == "app"


class TestSitemapCLI:
    def _run_cli(self, indexed_project, monkeypatch, mode):
        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                "--project-root",
                str(indexed_project),
                "--codegraph-sitemap",
                "--codegraph-sitemap-mode",
                mode,
                "--format",
                "json",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        return json.loads(mock_stdout.getvalue())

    def test_cli_smoke(self, indexed_project, monkeypatch):
        result = self._run_cli(indexed_project, monkeypatch, "flat")
        assert result["success"] is True
        assert result["file_count"] == 3
        assert result["counts"].get("function", 0) > 0

    def test_cli_api_mode(self, indexed_project, monkeypatch):
        result = self._run_cli(indexed_project, monkeypatch, "api")
        assert result["success"] is True
        names = {item["name"] for item in result["public_api"]}
        assert "public_func" in names

    def test_cli_module_mode(self, indexed_project, monkeypatch):
        result = self._run_cli(indexed_project, monkeypatch, "module")
        assert result["success"] is True
        assert any("app" in module["directory"] for module in result["modules"])

    def test_cli_max_symbols_flag_truncates(self, large_indexed_project, monkeypatch):
        """F3 CLI parity: --codegraph-sitemap-max-symbols bounds the output."""
        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                "--project-root",
                str(large_indexed_project),
                "--codegraph-sitemap",
                "--codegraph-sitemap-mode",
                "flat",
                "--codegraph-sitemap-max-files",
                "500",
                "--codegraph-sitemap-max-symbols",
                "50",
                "--format",
                "json",
            ],
        )
        mock_stdout = StringIO()
        monkeypatch.setattr("sys.stdout", mock_stdout)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        result = json.loads(mock_stdout.getvalue())
        emitted = sum(len(v) for v in result["symbols_by_kind"].values())
        assert emitted <= 50
        assert result["truncated"] is True


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows path drift in sitemap indexed-path fixtures; "
    "tracked: Windows-path-normalisation",
)
class TestSitemapFileLimitTruncation:
    """Codex P2 #337 + reviewer P3s: the max_files LIMIT must also flag
    truncated, and non-positive budgets must be rejected."""

    def _tool(self, project_root):
        from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
            CodeGraphSitemapTool,
        )

        return CodeGraphSitemapTool(project_root=str(project_root))

    @pytest.mark.asyncio
    async def test_file_limit_sets_truncated_in_all_modes(self, large_indexed_project):
        """When more files exist than max_files, EVERY mode must report
        truncated=true with a note naming max_files — not silently drop files
        while claiming completeness (Codex P2 #337). full/module previously
        always returned truncated=false."""
        tool = self._tool(large_indexed_project)
        for mode in ("full", "module", "api", "flat"):
            result = await tool.execute(
                {"mode": mode, "max_files": 5, "output_format": "json"}
            )
            assert result["truncated"] is True, mode
            assert "max_files" in result["truncation_note"], (mode, result)
            assert result["file_count"] == 5, mode

    @pytest.mark.asyncio
    async def test_truncation_note_absent_when_complete(self, indexed_project):
        """A complete response must NOT carry an empty truncation_note (reviewer
        P3 — schema noise)."""
        tool = self._tool(indexed_project)
        result = await tool.execute({"mode": "full", "output_format": "json"})
        assert result["truncated"] is False
        assert "truncation_note" not in result

    @pytest.mark.asyncio
    async def test_non_positive_budget_rejected(self, indexed_project):
        """max_symbols / max_files < 1 must raise, not silently negative-slice
        (reviewer P3)."""
        tool = self._tool(indexed_project)
        for bad in ({"max_symbols": 0}, {"max_symbols": -1}, {"max_files": 0}):
            with pytest.raises(ValueError, match="positive integer"):
                await tool.execute({"mode": "flat", **bad, "output_format": "json"})
