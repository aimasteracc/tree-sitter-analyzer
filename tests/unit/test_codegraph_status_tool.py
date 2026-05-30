"""Tests for CodeGraph Status tool — index health at-a-glance."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
    CodeGraphStatusTool,
)


@pytest.fixture
def tool():
    return CodeGraphStatusTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphStatusTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_status"

    def test_description_starts_with_index_health(self, tool):
        defn = tool.get_tool_definition()
        assert defn["description"].startswith("INDEX HEALTH")

    def test_annotations_all_four_hints(self, tool):
        defn = tool.get_tool_definition()
        annotations = defn["annotations"]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        assert annotations["openWorldHint"] is False

    def test_schema_strict_no_additional_properties(self, tool):
        schema = tool.get_tool_schema()
        assert schema["additionalProperties"] is False

    def test_schema_output_format_default_is_toon(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_schema_include_lag_default_true(self, tool):
        schema = tool.get_tool_schema()
        assert schema["properties"]["include_lag"]["default"] is True


class TestValidateArguments:
    def test_empty_args_accepted(self, tool):
        assert tool.validate_arguments({}) is True

    def test_include_lag_must_be_bool(self, tool):
        with pytest.raises(ValueError, match="include_lag"):
            tool.validate_arguments({"include_lag": "yes"})


class TestExecuteNoProjectRoot:
    @pytest.mark.asyncio
    async def test_no_project_root_returns_not_found(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert result["verdict"] == "NOT_FOUND"
        assert result["indexed"] is False
        assert result["total_files"] == 0
        assert result["total_symbols"] == 0
        assert result["project_root"] is None
        assert "project_root" in result["hint"]


class TestExecuteNoCache:
    @pytest.mark.asyncio
    async def test_project_set_but_no_cache_returns_warn(self, tool_with_root):
        result = await tool_with_root.execute({"output_format": "json"})
        assert result["verdict"] == "WARN"
        assert result["indexed"] is False
        assert result["total_files"] == 0
        assert result["cache_path"] is None
        assert "warm" in result["hint"].lower() or "index" in result["hint"].lower()


class TestExecuteWithIndex:
    @pytest.mark.asyncio
    async def test_indexed_returns_info_verdict(self, tool_with_root, tmp_path):
        # Create the cache db file so the tool walks the success branch.
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

        mock_stats = {
            "total_files": 42,
            "total_symbols": 1337,
            "fts5_available": True,
            "schema_version": 3,
        }
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = mock_stats

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute(
                {"output_format": "json", "include_lag": False}
            )

        assert result["verdict"] == "INFO"
        assert result["indexed"] is True
        assert result["total_files"] == 42
        assert result["total_symbols"] == 1337
        assert result["fts5_available"] is True
        assert result["schema_version"] == 3
        # include_lag=False → lag_seconds stays None
        assert result["lag_seconds"] is None

    @pytest.mark.asyncio
    async def test_total_edges_reported_for_graph_density(
        self, tool_with_root, tmp_path
    ):
        """total_edges must be present — README 'ahead' claim vs CodeGraph."""
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 10,
            "total_symbols": 100,
            "fts5_available": True,
            "schema_version": 3,
        }
        # get_cross_file_stats provides the edge count used for graph density.
        mock_cache.get_cross_file_stats.return_value = {"total": 250}

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute(
                {"output_format": "json", "include_lag": False}
            )

        assert result["verdict"] == "INFO"
        assert "total_edges" in result, (
            "total_edges must be present (README 'ahead' vs CodeGraph graph density signal)"
        )
        assert result["total_edges"] == 250

    @pytest.mark.asyncio
    async def test_total_edges_zero_when_cross_file_stats_fails(
        self, tool_with_root, tmp_path
    ):
        """total_edges is 0 when get_cross_file_stats raises (graceful fallback)."""
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 5,
            "total_symbols": 50,
            "fts5_available": True,
            "schema_version": 2,
        }
        mock_cache.get_cross_file_stats.side_effect = RuntimeError("edge table missing")

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute(
                {"output_format": "json", "include_lag": False}
            )

        assert result["verdict"] == "INFO"
        assert result["total_edges"] == 0

    @pytest.mark.asyncio
    async def test_indexed_with_lag_computes_seconds(self, tool_with_root, tmp_path):
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        cache_file = cache_dir / "index.db"
        cache_file.write_bytes(b"sqlite3-fake")
        # Source file newer than the cache → positive lag expected.
        src = tmp_path / "newer.py"
        src.write_text("x = 1\n")
        old_time = os.path.getmtime(cache_file) - 100.0
        os.utime(cache_file, (old_time, old_time))

        mock_stats = {
            "total_files": 5,
            "total_symbols": 10,
            "fts5_available": False,
            "schema_version": 2,
        }
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = mock_stats

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute(
                {"output_format": "json", "include_lag": True}
            )

        assert result["verdict"] == "INFO"
        assert result["indexed"] is True
        assert isinstance(result["lag_seconds"], float)
        assert result["lag_seconds"] >= 0.0

    @pytest.mark.asyncio
    async def test_cache_exists_but_empty_returns_warn(self, tool_with_root, tmp_path):
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"sqlite3-fake")

        mock_stats = {
            "total_files": 0,
            "total_symbols": 0,
            "fts5_available": False,
        }
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = mock_stats

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute({"output_format": "json"})

        assert result["verdict"] == "WARN"
        assert result["indexed"] is False
        # Cache file exists even though it's empty → path surfaces for debugging.
        assert result["cache_path"] is not None


class TestExecuteOutputFormat:
    @pytest.mark.asyncio
    async def test_toon_format_default(self, tool):
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_json_format_no_toon_blob(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert "toon_content" not in result
        assert result["verdict"] == "NOT_FOUND"
