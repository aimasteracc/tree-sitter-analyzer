"""Tests: MCP tools must accept numeric params delivered as strings.

The MCP boundary can deliver integers as strings (e.g. "200" instead of 200).
Each tool must coerce the param to int before using it in comparisons/slices.
RED-first: each test was written first (they crashed with TypeError/ValueError),
then the int() coercion was added in the tool.

Per CLAUDE.md LOCKED rule: assertion counts are exact pins, never >= / >.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ast_cache_tool — mode=index max_files as string
# ---------------------------------------------------------------------------


class TestAstCacheIndexMaxFilesCoercion:
    """ast_cache_tool.py:435 — max_files passed to cache.index_project()."""

    @pytest.mark.asyncio
    async def test_mode_index_max_files_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(project_root="/fake/root")

        fake_result = {
            "indexed": 0,
            "files_indexed": 0,
            "errors": [],
            "skipped": 0,
            "truncated_by_max_files": False,
        }
        fake_stats = {"total_symbols": 0}

        with patch.object(tool, "_get_cache") as mock_cache_factory:
            mock_cache = MagicMock()
            mock_cache.index_project.return_value = fake_result
            mock_cache.get_stats.return_value = fake_stats
            mock_cache_factory.return_value = mock_cache

            resp = await tool.execute(
                {
                    "mode": "index",
                    "max_files": "50",  # string — must not crash
                }
            )

        # Tool should succeed, not raise TypeError
        assert resp.get("success") is True
        # index_project was called with max_files as int
        called_kwargs = mock_cache.index_project.call_args
        assert called_kwargs is not None
        actual_max = called_kwargs.kwargs.get("max_files")
        assert actual_max == 50  # exact pin: coerced from "50"
        assert isinstance(actual_max, int)


# ---------------------------------------------------------------------------
# ast_cache_tool — mode=sync max_files as string
# ---------------------------------------------------------------------------


class TestAstCacheSyncMaxFilesCoercion:
    """ast_cache_tool.py:598 — max_files passed to sync_engine.sync()."""

    @pytest.mark.asyncio
    async def test_mode_sync_max_files_string_does_not_crash(
        self, tmp_path: Any
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(project_root=str(tmp_path))

        fake_sync_result = MagicMock()
        fake_sync_result.to_dict.return_value = {
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "scanned": 0,
            "considered": 0,
        }

        with patch.object(tool, "_get_sync") as mock_sync_factory:
            mock_sync = MagicMock()
            mock_sync.sync.return_value = fake_sync_result
            mock_sync_factory.return_value = mock_sync

            resp = await tool.execute(
                {
                    "mode": "sync",
                    "max_files": "100",  # string — must not crash
                }
            )

        assert resp.get("success") is True
        called_kwargs = mock_sync.sync.call_args
        actual_max = called_kwargs.kwargs.get("max_files")
        assert actual_max == 100  # exact pin
        assert isinstance(actual_max, int)


# ---------------------------------------------------------------------------
# ast_path_tool — mode=outline max_depth as string
# ---------------------------------------------------------------------------


class TestAstPathMaxDepthCoercion:
    """ast_path_tool.py:114 — max_depth passed to nav.outline()."""

    @pytest.mark.asyncio
    async def test_mode_outline_max_depth_string_does_not_crash(
        self, tmp_path: Any
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_path_tool import CodeGraphASTPathTool

        src = tmp_path / "foo.py"
        src.write_text("def foo(): pass\n")
        tool = CodeGraphASTPathTool(project_root=str(tmp_path))

        fake_outline = MagicMock()
        fake_outline.to_dict.return_value = {"items": []}
        fake_outline.items = []

        with patch.object(tool, "_get_navigator") as mock_nav_factory:
            mock_nav = MagicMock()
            mock_nav.outline.return_value = fake_outline
            mock_nav_factory.return_value = mock_nav

            resp = await tool.execute(
                {
                    "mode": "outline",
                    "file_path": str(src),
                    "max_depth": "4",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True
        called_kwargs = mock_nav.outline.call_args
        actual_depth = called_kwargs.kwargs.get("max_depth")
        assert actual_depth == 4  # exact pin
        assert isinstance(actual_depth, int)


# ---------------------------------------------------------------------------
# class_hierarchy_tool — max_depth as string
# ---------------------------------------------------------------------------


class TestClassHierarchyMaxDepthCoercion:
    """class_hierarchy_tool.py:175 — max_depth passed to hierarchy.subclasses_of()."""

    @pytest.mark.asyncio
    async def test_max_depth_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import (
            ClassHierarchyTool,
        )

        tool = ClassHierarchyTool(project_root="/fake/root")

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.class_hierarchy_tool.is_index_rebuilding",
                return_value=False,
            ),
            patch.object(tool, "_get_hierarchy") as mock_hier_factory,
        ):
            mock_hier = MagicMock()
            mock_hier.subclasses_of.return_value = []
            mock_hier.class_stats.return_value = {}
            mock_hier_factory.return_value = mock_hier

            resp = await tool.execute(
                {
                    "mode": "subclasses",
                    "class_name": "Base",
                    "max_depth": "7",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True
        called_kwargs = mock_hier.subclasses_of.call_args
        actual_depth = called_kwargs.kwargs.get("max_depth")
        assert actual_depth == 7  # exact pin
        assert isinstance(actual_depth, int)


# ---------------------------------------------------------------------------
# codegraph_sitemap_tool — max_files as string
# ---------------------------------------------------------------------------


class TestCodegraphSitemapMaxFilesCoercion:
    """codegraph_sitemap_tool.py:152 — max_files used in arithmetic/slice."""

    @pytest.mark.asyncio
    async def test_max_files_string_does_not_crash(self, tmp_path: Any) -> None:
        from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
            CodeGraphSitemapTool,
        )

        tool = CodeGraphSitemapTool(project_root=str(tmp_path))

        # Patch both _get_cache (to avoid DB creation) and _load_indexed_files
        with (
            patch.object(tool, "_get_cache", return_value=MagicMock()),
            patch.object(tool, "_load_indexed_files", return_value=[]),
        ):
            resp = await tool.execute(
                {
                    "mode": "full",
                    "max_files": "10",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True


# ---------------------------------------------------------------------------
# dependency_matrix_tool — top_k as string
# ---------------------------------------------------------------------------


class TestDependencyMatrixTopKCoercion:
    """dependency_matrix_tool.py:141 — top_k used in coupling_pairs[:top_k]."""

    @pytest.mark.asyncio
    async def test_top_k_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.dependency_matrix_tool import (
            CodeGraphDependencyMatrixTool,
        )

        tool = CodeGraphDependencyMatrixTool(project_root="/fake/root")

        with patch.object(tool, "_get_matrix") as mock_dm_factory:
            mock_dm = MagicMock()
            mock_dm.most_coupled.return_value = []
            mock_dm_factory.return_value = mock_dm

            resp = await tool.execute(
                {
                    "mode": "hotspots",
                    "top_k": "5",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True
        called_kwargs = mock_dm.most_coupled.call_args
        actual_top_k = called_kwargs.kwargs.get("top_k")
        assert actual_top_k == 5  # exact pin
        assert isinstance(actual_top_k, int)


# ---------------------------------------------------------------------------
# full_index_tool — max_files as string
# ---------------------------------------------------------------------------


class TestFullIndexMaxFilesCoercion:
    """full_index_tool.py:118 — max_files passed to cache.index_project()."""

    @pytest.mark.asyncio
    async def test_max_files_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool(project_root="/fake/root")

        fake_ast_result = {
            "success": True,
            "files_indexed": 0,
            "indexed": 0,
            "errors": [],
        }

        with (
            patch.object(tool, "_phase_ast_cache", return_value=fake_ast_result),
            patch.object(tool, "_phase_synapse", return_value={"success": True}),
        ):
            resp = await tool.execute(
                {
                    "mode": "incremental",
                    "max_files": "500",  # string — must not crash
                    "output_format": "json",
                }
            )

        # No TypeError crash; result is a dict
        assert isinstance(resp, dict)


# ---------------------------------------------------------------------------
# import_graph_tool — blast_radius mode max_depth as string
# ---------------------------------------------------------------------------


class TestImportGraphMaxDepthCoercion:
    """import_graph_tool.py:181 — max_depth passed to graph.blast_radius()."""

    @pytest.mark.asyncio
    async def test_blast_radius_max_depth_string_does_not_crash(
        self, tmp_path: Any
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.import_graph_tool import (
            CodeGraphImportGraphTool,
        )

        src = tmp_path / "foo.py"
        src.write_text("import os\n")
        tool = CodeGraphImportGraphTool(project_root=str(tmp_path))

        with patch.object(tool, "_get_graph") as mock_graph_factory:
            mock_graph = MagicMock()
            mock_graph.blast_radius.return_value = {
                "affected_files": [],
                "depth": 0,
            }
            mock_graph_factory.return_value = mock_graph

            resp = await tool.execute(
                {
                    "mode": "blast_radius",
                    "file_path": str(src),
                    "max_depth": "3",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True
        called_kwargs = mock_graph.blast_radius.call_args
        actual_depth = called_kwargs.kwargs.get("max_depth")
        assert actual_depth == 3  # exact pin
        assert isinstance(actual_depth, int)


# ---------------------------------------------------------------------------
# project_overview_tool — max_depth as string
# ---------------------------------------------------------------------------


class TestProjectOverviewMaxDepthCoercion:
    """project_overview_tool.py:192,205 — validate rejects str; coerce first."""

    @pytest.mark.asyncio
    async def test_max_depth_string_does_not_crash(self, tmp_path: Any) -> None:
        from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
            ProjectOverviewTool,
        )

        tool = ProjectOverviewTool(project_root=str(tmp_path))

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.project_overview_tool._scan_project",
                return_value={},
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.project_overview_tool._build_result",
                return_value={"success": True},
            ),
        ):
            resp = await tool.execute(
                {
                    "max_depth": "3",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True


# ---------------------------------------------------------------------------
# test_gap_tool — max_files and max_gaps as strings
# ---------------------------------------------------------------------------


class TestTestGapMaxFilesMaxGapsCoercion:
    """test_gap_tool.py:123,124 — both max_files and max_gaps must be coerced."""

    @pytest.mark.asyncio
    async def test_max_files_and_max_gaps_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.test_gap_tool import CodeGraphTestGapTool

        tool = CodeGraphTestGapTool(project_root="/fake/root")

        fake_result = MagicMock()
        fake_result.gap_count = 0
        fake_result.gaps = []
        fake_result.total_files = 0
        fake_result.files_with_gaps = 0
        fake_result.coverage_percentage = 100.0

        with patch(
            "tree_sitter_analyzer.mcp.tools.test_gap_tool.analyze_coverage_gaps",
            return_value=fake_result,
        ) as mock_analyze:
            resp = await tool.execute(
                {
                    "mode": "gaps",
                    "max_files": "200",  # string
                    "max_gaps": "25",  # string
                    "output_format": "json",
                }
            )

        assert resp.get("success") is True
        called_kwargs = mock_analyze.call_args
        actual_max_files = called_kwargs.kwargs.get("max_files")
        actual_max_gaps = called_kwargs.kwargs.get("max_gaps")
        assert actual_max_files == 200  # exact pin
        assert actual_max_gaps == 25  # exact pin
        assert isinstance(actual_max_files, int)
        assert isinstance(actual_max_gaps, int)


# ---------------------------------------------------------------------------
# trace_impact_tool — max_results as string
# ---------------------------------------------------------------------------


class TestTraceImpactMaxResultsCoercion:
    """trace_impact_tool.py:891 — max_results used in len()>= and [:] slices."""

    @pytest.mark.asyncio
    async def test_max_results_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

        tool = TraceImpactTool(project_root="/fake/root")

        with (
            patch.object(
                tool,
                "_resolve_search_roots",
                return_value=["/fake/root"],
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.trace_impact_tool.build_rg_command",
                return_value=["rg", "--json", "my_func"],
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.trace_impact_tool.run_command_capture",
                return_value=(1, b"", b""),  # rc=1 → zero matches (NOT_FOUND path)
            ),
        ):
            resp = await tool.execute(
                {
                    "symbol": "my_func",
                    "max_results": "300",  # string — must not crash
                    "output_format": "json",
                }
            )

        # Tool returns NOT_FOUND or success, not a TypeError
        assert isinstance(resp, dict)
        assert "TypeError" not in str(resp.get("error", ""))


# ---------------------------------------------------------------------------
# unreachable_code_tool — max_files as string
# ---------------------------------------------------------------------------


class TestUnreachableCodeMaxFilesCoercion:
    """unreachable_code_tool.py:138 — max_files passed to analyze_project_unreachable."""

    @pytest.mark.asyncio
    async def test_max_files_string_does_not_crash(self) -> None:
        from tree_sitter_analyzer.mcp.tools.unreachable_code_tool import (
            UnreachableCodeTool,
        )

        tool = UnreachableCodeTool(project_root="/fake/root")

        with patch(
            "tree_sitter_analyzer.mcp.tools.unreachable_code_tool.analyze_project_unreachable",
            return_value=[],
        ) as mock_analyze:
            resp = await tool.execute(
                {
                    "mode": "project",
                    "max_files": "75",  # string — must not crash
                    "output_format": "json",
                }
            )

        assert "error" not in resp or resp.get("error") is None
        called_kwargs = mock_analyze.call_args
        actual_max = called_kwargs.kwargs.get("max_files")
        assert actual_max == 75  # exact pin
        assert isinstance(actual_max, int)
