"""Tests for codegraph_metrics MCP tool — aggregated project intelligence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool import CodeGraphMetricsTool


@pytest.fixture
def tool():
    return CodeGraphMetricsTool()


@pytest.fixture
def tool_with_root(tmp_path):
    return CodeGraphMetricsTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_metrics"

    def test_description_mentions_codegraph_parity(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "CodeGraph" in desc

    def test_schema_has_sections_and_output_format(self, tool):
        schema = tool.get_tool_schema()
        assert "sections" in schema["properties"]
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["default"] == "json"

    def test_schema_sections_enum(self, tool):
        items = tool.get_tool_schema()["properties"]["sections"]["items"]
        assert set(items["enum"]) == {
            "cache",
            "call_graph",
            "complexity",
            "routes",
            "health",
        }

    def test_annotations_readonly(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["readOnlyHint"] is True
        assert hints["destructiveHint"] is False


class TestValidation:
    def test_valid_no_sections(self, tool):
        assert tool.validate_arguments({}) is True

    def test_valid_subset_sections(self, tool):
        assert tool.validate_arguments({"sections": ["cache", "health"]}) is True

    def test_rejects_unknown_section(self, tool):
        with pytest.raises(ValueError, match="Invalid sections"):
            tool.validate_arguments({"sections": ["cache", "unknown"]})


@pytest.mark.asyncio
class TestExecuteNoCache:
    async def test_no_project_root_returns_info(self, tool):
        result = await tool.execute({"output_format": "json"})
        assert result["success"] is True
        assert result["cache_indexed"] is False

    async def test_cache_empty_section_hint(self, tool_with_root):
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.ensure_indexed",
            return_value=None,
        ):
            result = await tool_with_root.execute(
                {"sections": ["cache"], "output_format": "json"}
            )
        assert result["success"] is True
        assert result["cache"]["status"] == "empty"

    async def test_sections_included_field(self, tool_with_root):
        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.ensure_indexed",
            return_value=None,
        ):
            result = await tool_with_root.execute(
                {"sections": ["cache", "health"], "output_format": "json"}
            )
        assert set(result["sections_included"]) == {"cache", "health"}


@pytest.mark.asyncio
class TestExecuteWithCache:
    async def test_cache_section_populated_when_indexed(self, tool_with_root):
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 42,
            "total_symbols": 1000,
            "fts5_available": True,
            "fts_indexed_symbols": 950,
            "by_language": {"python": 40, "javascript": 2},
        }

        with patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.ensure_indexed",
            return_value=mock_cache,
        ):
            result = await tool_with_root.execute(
                {"sections": ["cache"], "output_format": "json"}
            )

        assert result["cache"]["status"] == "indexed"
        assert result["cache"]["total_files"] == 42
        assert result["cache"]["total_symbols"] == 1000
        assert result["cache_indexed"] is True


class TestCallGraphMetricsSanity:
    """F1 regression: project metrics must not degenerate to 'every function is
    both an entry point AND dead code'. Root cause was a key mismatch —
    all_functions() dicts key the path under 'file', but the metric collector
    read 'file_path', so every function string had an empty path and never
    matched the call-edge keys (real paths), making callers/callees maps useless.
    """

    def _index(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        proj = tmp_path / "pkg"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "__init__.py").write_text("# pkg\n")
        (proj / "a.py").write_text(
            "def helper():\n    return 1\n\ndef caller():\n    return helper()\n"
        )
        (proj / "b.py").write_text("def other():\n    return 2\n")
        cache = ASTCache(str(tmp_path))
        cache.index_project()
        return cache

    def test_dead_code_candidates_never_equals_total(self, tmp_path):
        cache = self._index(tmp_path)
        tool = CodeGraphMetricsTool(str(tmp_path))
        m = tool._collect_call_graph_metrics(cache)
        assert m["status"] == "computed", m
        total = m["total_functions"]
        assert total == 3, m
        # The bug made all three equal to total. A real graph with a call edge
        # (caller -> helper) must classify helper as NON-dead and NON-entry.
        assert m["dead_code_candidates"] < total, (
            f"every function flagged dead ({m['dead_code_candidates']}/{total}) "
            "— F1 key-mismatch regression"
        )
        assert m["entry_points"] < total, m
        assert m["total_call_edges"] == 1, m

    def test_files_with_functions_reflects_real_paths(self, tmp_path):
        cache = self._index(tmp_path)
        tool = CodeGraphMetricsTool(str(tmp_path))
        m = tool._collect_call_graph_metrics(cache)
        # The bug collapsed every function path to "" -> files_with_functions == 1
        # regardless of how many files define functions. a.py and b.py both
        # define functions, so a correct collector reports >= 2 distinct files.
        assert m["files_with_functions"] == 2, (
            f"files_with_functions={m['files_with_functions']} — paths collapsed "
            "to empty string (F1 key-mismatch regression)"
        )


def test_route_metrics_closes_request_owned_detector(tool_with_root):
    """一次性指标采集必须在返回前释放 routes.db 连接。"""
    detector = MagicMock()
    detector.summary.return_value = {
        "total_routes": 1,
        "by_framework": {"flask": 1},
        "by_method": {"GET": 1},
        "file_count": 1,
    }

    with patch(
        "tree_sitter_analyzer.route_detector.RouteDetector",
        return_value=detector,
    ):
        result = tool_with_root._collect_route_metrics()

    assert result["status"] == "computed"
    detector.close.assert_called_once_with()


def test_route_metrics_closes_detector_when_collection_fails(tool_with_root):
    """指标异常路径同样必须释放请求拥有的路由检测器。"""
    detector = MagicMock()
    detector.summary.side_effect = RuntimeError("broken")

    with patch(
        "tree_sitter_analyzer.route_detector.RouteDetector",
        return_value=detector,
    ):
        result = tool_with_root._collect_route_metrics()

    assert result == {"status": "error", "error": "broken"}
    detector.close.assert_called_once_with()
