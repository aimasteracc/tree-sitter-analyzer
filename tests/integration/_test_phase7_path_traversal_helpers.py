"""Path traversal helpers for Phase 7 security integration tests."""

from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


async def collect_path_traversal_results(
    tools: Iterable[Any],
    malicious_paths: Iterable[str],
) -> list[dict[str, Any]]:
    """Run path traversal attacks against file-oriented tools."""
    attack_results = []

    for tool in tools:
        tool_name = tool.__class__.__name__
        print(f"Testing {tool_name} against path traversal attacks...")
        attack_results.extend(
            [
                await _run_path_traversal_attack(tool, tool_name, path)
                for path in malicious_paths
            ]
        )

    return attack_results


async def _run_path_traversal_attack(
    tool: Any,
    tool_name: str,
    malicious_path: str,
) -> dict[str, Any]:
    try:
        result = await _execute_path_traversal_attack(tool, malicious_path)
        if result.get("success"):
            return {
                "tool": tool_name,
                "attack_path": malicious_path,
                "blocked": False,
                "result": "SUCCESS - SECURITY BREACH!",
            }
        return {
            "tool": tool_name,
            "attack_path": malicious_path,
            "blocked": True,
            "result": "Blocked successfully",
        }
    except Exception as exc:
        return {
            "tool": tool_name,
            "attack_path": malicious_path,
            "blocked": True,
            "result": f"Exception: {type(exc).__name__}",
        }


async def _execute_path_traversal_attack(
    tool: Any,
    malicious_path: str,
) -> dict[str, Any]:
    if isinstance(
        tool, AnalyzeScaleTool | TableFormatTool | ReadPartialTool | QueryTool
    ):
        return await tool.execute({"file_path": malicious_path})

    raise TypeError(
        f"Unsupported tool for path traversal test: {tool.__class__.__name__}"
    )
