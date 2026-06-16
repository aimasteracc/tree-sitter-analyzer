"""Tests for codegraph_autoindex MCP tool — transparent AST cache warming."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.auto_index_tool import CodeGraphAutoIndexTool
from tree_sitter_analyzer.mcp.utils import auto_index_guard


@pytest.fixture
def tool():
    return CodeGraphAutoIndexTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphAutoIndexTool(str(tmp_path))


@pytest.fixture
def warm_cache_root(tmp_path):
    """A project whose on-disk cache is fully populated, but whose
    in-memory auto-index guard is cold — mirroring a fresh process that
    finds a warm cache on disk (the #1004 repro condition).
    """
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "from a import f\n\ndef g():\n    return f()\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10, workers=0)
    finally:
        cache.close()
    # Cold guard: this process never "warmed" the cache via ensure_indexed,
    # so is_indexed() returns False even though the cache has rows on disk.
    auto_index_guard.reset()
    yield tmp_path
    auto_index_guard.reset()


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_autoindex"

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"status", "warm", "reset"}
        assert mode["default"] == "status"

    def test_schema_output_format_default_toon(self, tool):
        assert (
            tool.get_tool_schema()["properties"]["output_format"]["default"] == "toon"
        )

    def test_annotations_not_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is False
        assert hints["destructiveHint"] is True


class TestValidation:
    def test_valid_status(self, tool):
        assert tool.validate_arguments({"mode": "status"}) is True

    def test_valid_warm(self, tool):
        assert tool.validate_arguments({"mode": "warm"}) is True

    def test_valid_reset(self, tool):
        assert tool.validate_arguments({"mode": "reset"}) is True

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "delete"})


@pytest.mark.asyncio
class TestExecute:
    async def test_status_no_project_root_returns_warn(self, tool):
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["verdict"] == "WARN"
        assert result["indexed"] is False

    async def test_status_empty_project_returns_info(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "status", "output_format": "json"}
        )
        assert result["success"] is True
        assert "indexed" in result

    async def test_toon_format_default(self, tool_with_root):
        result = await tool_with_root.execute({"mode": "status"})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_reset_mode_runs_without_error(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "reset", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_warm_mode_returns_indexed_true(self, tool_with_root):
        # DF-8: verify warm mode returns indexed=true and cache_stats after successful index
        result = await tool_with_root.execute(
            {"mode": "warm", "max_files": 100, "output_format": "json"}
        )
        assert result["success"] is True
        assert result["indexed"] is True
        assert result["cache_stats"] is not None
        assert isinstance(result["cache_stats"], dict)

    async def test_status_warm_cache_reports_indexed_true(self, warm_cache_root):
        # #1004: a fresh process must report a populated on-disk cache as
        # indexed=True, not lie with indexed=False because the in-memory
        # guard is cold.
        tool = CodeGraphAutoIndexTool(str(warm_cache_root))
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["indexed"] is True
        assert result["cache_stats"] is not None
        assert result["cache_stats"]["total_files"] == 2

    async def test_status_indexed_matches_actual_row_count(self, warm_cache_root):
        # #1004 contract: indexed reflects whether ast_index has rows.
        tool = CodeGraphAutoIndexTool(str(warm_cache_root))
        result = await tool.execute({"mode": "status", "output_format": "json"})
        cache = ASTCache(str(warm_cache_root))
        try:
            actual_rows = cache.get_stats()["total_files"]
        finally:
            cache.close()
        assert actual_rows == 2
        assert result["indexed"] == (actual_rows > 0)

    async def test_status_built_marker_distinct_from_indexed(self, warm_cache_root):
        # #1004: built_marker reflects the in-memory guard ("did THIS
        # process warm it"); indexed reflects on-disk rows. On a warm cache
        # in a fresh process they diverge — that divergence is the truth
        # the field separation exposes.
        tool = CodeGraphAutoIndexTool(str(warm_cache_root))
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["indexed"] is True
        assert result["built_marker"] is False

    async def test_status_empty_cache_reports_indexed_false(self, tool_with_root):
        # An empty tmp project has no rows → indexed must be False and
        # cache_stats reflects the (empty) real cache, never a bare None lie.
        result = await tool_with_root.execute(
            {"mode": "status", "output_format": "json"}
        )
        assert result["indexed"] is False
        assert result["cache_stats"] is not None
        assert result["cache_stats"]["total_files"] == 0
