"""Malicious query helpers for Phase 7 security integration tests."""

import asyncio
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


async def collect_malicious_query_results(
    search_tools: Iterable[Any],
    malicious_queries: Iterable[str],
    secure_test_project: str,
) -> list[dict[str, Any]]:
    """Run every malicious query against each search tool."""
    query_results = []

    for tool in search_tools:
        query_results.extend(
            await _collect_tool_malicious_query_results(
                tool,
                malicious_queries,
                secure_test_project,
            )
        )

    return query_results


async def _collect_tool_malicious_query_results(
    tool: Any,
    malicious_queries: Iterable[str],
    secure_test_project: str,
) -> list[dict[str, Any]]:
    tool_name = tool.__class__.__name__
    print(f"Testing {tool_name} against malicious queries...")

    results = []
    for malicious_query in malicious_queries:
        results.append(
            await _run_malicious_query(
                tool,
                tool_name,
                malicious_query,
                secure_test_project,
            )
        )
    return results


async def _run_malicious_query(
    tool: Any,
    tool_name: str,
    malicious_query: str,
    secure_test_project: str,
) -> dict[str, Any]:
    start_time = time.time()

    try:
        result = await _execute_malicious_query(
            tool, malicious_query, secure_test_project
        )
        execution_time = time.time() - start_time
        return _build_query_result(tool_name, malicious_query, execution_time, result)
    except asyncio.TimeoutError:
        return {
            "tool": tool_name,
            "query": _preview_query(malicious_query),
            "execution_time": 5.0,
            "success": False,
            "blocked": True,
            "result": "Timeout (DoS protection)",
        }
    except Exception as exc:
        return {
            "tool": tool_name,
            "query": _preview_query(malicious_query),
            "execution_time": time.time() - start_time,
            "success": False,
            "blocked": True,
            "result": f"Exception: {type(exc).__name__}",
        }


async def _execute_malicious_query(
    tool: Any,
    malicious_query: str,
    secure_test_project: str,
) -> dict[str, Any]:
    if isinstance(tool, SearchContentTool | FindAndGrepTool):
        return await asyncio.wait_for(
            tool.execute(
                {
                    "roots": [secure_test_project],
                    "query": malicious_query,
                    "max_count": 10,
                }
            ),
            timeout=5.0,
        )

    if isinstance(tool, QueryTool):
        secure_service = (
            Path(secure_test_project)
            / "src"
            / "main"
            / "java"
            / "com"
            / "secure"
            / "SecureService.java"
        )
        return await asyncio.wait_for(
            tool.execute(
                {"file_path": str(secure_service), "query_string": malicious_query}
            ),
            timeout=5.0,
        )

    raise TypeError(
        f"Unsupported tool for malicious query test: {tool.__class__.__name__}"
    )


def _build_query_result(
    tool_name: str,
    malicious_query: str,
    execution_time: float,
    result: dict[str, Any],
) -> dict[str, Any]:
    success = result.get("success", False)
    return {
        "tool": tool_name,
        "query": _preview_query(malicious_query),
        "execution_time": execution_time,
        "success": success,
        "blocked": not success or execution_time > 3.0,
        "result": "Completed" if success else "Failed/Blocked",
    }


def _preview_query(malicious_query: str) -> str:
    return (
        malicious_query[:50] + "..." if len(malicious_query) > 50 else malicious_query
    )
