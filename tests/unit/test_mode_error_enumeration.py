"""RED-first: every MCP inner tool with a ``mode`` argument must raise a
mode-validation error that *enumerates the valid modes*, mirroring the good
pattern in ``call_graph_tool`` / ``test_gap_tool``.

Each tool below previously raised a bare ``ValueError(f"Invalid mode: {mode}")``
or ``ValueError(f"Unknown mode: {mode}")`` that did not tell the caller which
modes are accepted. The valid set is pulled from each tool's own schema enum so
there is a single source of truth.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
from tree_sitter_analyzer.mcp.tools.ast_path_tool import CodeGraphASTPathTool
from tree_sitter_analyzer.mcp.tools.auto_index_tool import CodeGraphAutoIndexTool
from tree_sitter_analyzer.mcp.tools.code_similarity_tool import CodeGraphSimilarityTool
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import CodeGraphImpactTool
from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import CodeGraphSitemapTool
from tree_sitter_analyzer.mcp.tools.complexity_heatmap_tool import (
    CodeGraphComplexityHeatmapTool,
)
from tree_sitter_analyzer.mcp.tools.dead_code_tool import CodeGraphDeadCodeTool
from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
)
from tree_sitter_analyzer.mcp.tools.route_detector_tool import RouteDetectorTool
from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import SemanticClassifyTool

_BOGUS = "__definitely_not_a_real_mode__"


def _schema_modes(tool) -> list[str]:
    return list(tool.get_tool_schema()["properties"]["mode"]["enum"])


def _assert_enumerates(msg: str, tool) -> None:
    assert _BOGUS in msg, f"error should echo the bad mode: {msg}"
    assert "Invalid mode" in msg, f"error should use canonical prefix: {msg}"
    for valid in _schema_modes(tool):
        assert valid in msg, f"Missing '{valid}' in error: {msg}"


# ---------------------------------------------------------------------------
# Tools that validate ``mode`` in ``validate_arguments`` (synchronous path).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_cls",
    [
        CodeGraphIncrementalSyncTool,
        CodeGraphSitemapTool,
        CodeGraphSimilarityTool,
        CodeGraphComplexityHeatmapTool,
        CodeGraphDeadCodeTool,
        CodeGraphAutoIndexTool,
    ],
)
def test_validate_arguments_enumerates_modes(tool_cls):
    tool = tool_cls()
    with pytest.raises(ValueError) as exc_info:
        tool.validate_arguments({"mode": _BOGUS})
    _assert_enumerates(str(exc_info.value), tool)


# ---------------------------------------------------------------------------
# Tools that reject an unknown ``mode`` in ``execute``'s dispatch ``else``.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_diff_execute_enumerates_modes():
    tool = ASTDiffTool(project_root="/tmp/test_project")
    with pytest.raises(ValueError) as exc_info:
        await tool.execute({"mode": _BOGUS, "file_path": "/src/main.py"})
    _assert_enumerates(str(exc_info.value), tool)


@pytest.mark.asyncio
async def test_semantic_classify_execute_enumerates_modes():
    tool = SemanticClassifyTool(project_root="/tmp/test_project")
    with pytest.raises(ValueError) as exc_info:
        await tool.execute({"mode": _BOGUS, "file_path": "/src/main.py"})
    _assert_enumerates(str(exc_info.value), tool)


@pytest.mark.asyncio
async def test_route_detector_execute_enumerates_modes():
    tool = RouteDetectorTool(project_root="/tmp/test_project")
    tool._get_detector = MagicMock(return_value=MagicMock())
    with pytest.raises(ValueError) as exc_info:
        await tool.execute({"mode": _BOGUS})
    _assert_enumerates(str(exc_info.value), tool)


@pytest.mark.asyncio
async def test_codegraph_impact_execute_enumerates_modes():
    tool = CodeGraphImpactTool(project_root="/tmp/test_project")
    tool.get_call_graph = MagicMock(return_value=MagicMock())
    with pytest.raises(ValueError) as exc_info:
        await tool.execute({"mode": _BOGUS})
    _assert_enumerates(str(exc_info.value), tool)


@pytest.mark.asyncio
async def test_ast_path_execute_enumerates_modes():
    tool = CodeGraphASTPathTool(project_root="/tmp/test_project")
    tool.resolve_and_validate_file_path = MagicMock(return_value="/src/main.py")
    tool._get_navigator = MagicMock(return_value=MagicMock())
    with pytest.raises(ValueError) as exc_info:
        await tool.execute({"mode": _BOGUS, "file_path": "/src/main.py"})
    _assert_enumerates(str(exc_info.value), tool)
