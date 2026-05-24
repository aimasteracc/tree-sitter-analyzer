"""Security policy helpers for Phase 7 security integration tests."""

from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


def create_security_policy_test_cases() -> list[dict[str, Any]]:
    """Return common path-policy cases shared across MCP tools."""
    return [
        {
            "name": "path_traversal",
            "test_data": "../../../etc/passwd",
            "expected_blocked": True,
        },
        {
            "name": "null_byte",
            "test_data": "test\x00.txt",
            "expected_blocked": True,
        },
        {
            "name": "absolute_path",
            "test_data": "/etc/passwd",
            "expected_blocked": True,
        },
        {
            "name": "windows_path",
            "test_data": "C:\\Windows\\System32\\config\\SAM",
            "expected_blocked": True,
        },
    ]


async def collect_security_policy_results(
    tools: Iterable[Any],
    test_cases: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run path-policy cases across tools and report consistency."""
    policy_results = []

    for tool in tools:
        tool_name = tool.__class__.__name__
        for test_case in test_cases:
            policy_results.append(
                await _run_security_policy_case(tool, tool_name, test_case)
            )

    return policy_results


def assert_security_policy_consistency_results(
    policy_results: list[dict[str, Any]],
) -> None:
    """Assert and report security policy consistency across tools."""
    inconsistent_results = [r for r in policy_results if not r["consistent"]]
    total_tests = len(policy_results)
    consistency_rate = (
        (total_tests - len(inconsistent_results)) / total_tests
        if total_tests > 0
        else 0
    )

    print("Security Policy Consistency Results:")
    print(f"  Total tests: {total_tests}")
    print(f"  Consistent: {total_tests - len(inconsistent_results)}")
    print(f"  Inconsistent: {len(inconsistent_results)}")
    print(f"  Consistency rate: {consistency_rate:.2%}")
    _print_inconsistent_security_policy_results(inconsistent_results)

    assert consistency_rate >= 0.80, (
        f"Security policy consistency too low: {consistency_rate:.2%}"
    )


def _print_inconsistent_security_policy_results(
    inconsistent_results: list[dict[str, Any]],
) -> None:
    if not inconsistent_results:
        return

    print("  Inconsistent results:")
    for result in inconsistent_results:
        print(f"    {result['tool']} - {result['test_case']}: {result['result']}")


async def _run_security_policy_case(
    tool: Any,
    tool_name: str,
    test_case: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await _execute_security_policy_case(tool, test_case["test_data"])
        blocked = (
            not result.get("success", False)
            or "error" in result
            or "Error" in str(result)
        )
        return _build_security_policy_result(tool_name, test_case, blocked)
    except Exception as exc:
        return _build_security_policy_result(
            tool_name,
            test_case,
            blocked=True,
            result_label=f"Exception: {type(exc).__name__}",
        )


async def _execute_security_policy_case(
    tool: Any,
    test_data: str,
) -> dict[str, Any]:
    if isinstance(
        tool, AnalyzeScaleTool | TableFormatTool | ReadPartialTool | QueryTool
    ):
        return await tool.execute({"file_path": test_data})

    if isinstance(tool, ListFilesTool):
        return await tool.execute({"roots": [test_data]})

    if isinstance(tool, SearchContentTool | FindAndGrepTool):
        return await tool.execute({"roots": [test_data], "query": "test"})

    raise TypeError(
        f"Unsupported tool for policy consistency test: {tool.__class__.__name__}"
    )


def _build_security_policy_result(
    tool_name: str,
    test_case: dict[str, Any],
    blocked: bool,
    result_label: str | None = None,
) -> dict[str, Any]:
    expected_blocked = test_case["expected_blocked"]
    consistent = blocked == expected_blocked
    return {
        "tool": tool_name,
        "test_case": test_case["name"],
        "blocked": blocked,
        "expected_blocked": expected_blocked,
        "consistent": consistent,
        "result": result_label or ("Consistent" if consistent else "INCONSISTENT!"),
    }
