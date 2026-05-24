"""Focused helpers for Phase 7 end-to-end test workflows."""

import asyncio
import time
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


async def run_performance_under_load(enterprise_project: str) -> None:
    """Run the concurrent tool load scenario."""
    tools = [
        AnalyzeScaleTool(enterprise_project),
        TableFormatTool(enterprise_project),
        SearchContentTool(enterprise_project),
        ListFilesTool(enterprise_project),
    ]
    concurrent_tasks = _build_performance_tasks(enterprise_project, tools)

    start_time = time.time()
    results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
    execution_time = time.time() - start_time

    _assert_performance_results(results, execution_time)


def _build_performance_tasks(
    enterprise_project: str,
    tools: list[Any],
) -> list[Any]:
    tasks = []
    for _i in range(3):
        tasks.extend(
            task
            for tool in tools
            if (task := _performance_task_for_tool(tool, enterprise_project))
        )
    return tasks


def _performance_task_for_tool(tool: Any, enterprise_project: str) -> Any | None:
    readme_path = str(Path(enterprise_project) / "README.md")

    if isinstance(tool, AnalyzeScaleTool):
        return tool.execute({"file_path": readme_path})
    if isinstance(tool, TableFormatTool):
        return tool.execute({"file_path": readme_path, "format_type": "compact"})
    if isinstance(tool, SearchContentTool):
        return tool.execute(
            {
                "roots": [enterprise_project],
                "query": "test",
                "max_count": 3,
            }
        )
    if isinstance(tool, ListFilesTool):
        return tool.execute({"roots": [enterprise_project], "limit": 5})
    return None


def _assert_performance_results(results: list[Any], execution_time: float) -> None:
    successful_results = [
        result
        for result in results
        if isinstance(result, dict) and result.get("success")
    ]

    success_rate = len(successful_results) / len(results)
    assert success_rate >= 0.5, f"成功率が低すぎます: {success_rate:.2f}"
    assert execution_time < 60.0, f"並行実行時間が長すぎます: {execution_time:.2f}秒"

    print(
        f"並行実行結果: {len(successful_results)}/{len(results)} 成功, {execution_time:.2f}秒"
    )
