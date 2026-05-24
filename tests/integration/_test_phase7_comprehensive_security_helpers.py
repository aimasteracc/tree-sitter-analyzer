"""Comprehensive security validation helpers for Phase 7 integration tests."""

import asyncio
import time
from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

PATH_TRAVERSAL_CHECKS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\config\\sam",
]

NORMAL_QUERY_CHECKS = [
    "test.*test",
    "simple_query",
    "normal",
]


async def collect_comprehensive_security_checks(
    secure_test_project: str,
) -> list[dict[str, Any]]:
    """Run the mixed checks used by the comprehensive security test."""
    scale_tool = AnalyzeScaleTool(secure_test_project)
    search_tool = SearchContentTool(secure_test_project)

    security_checks = []
    security_checks.extend(
        await _collect_path_traversal_checks(scale_tool, PATH_TRAVERSAL_CHECKS)
    )
    security_checks.extend(
        await _collect_normal_query_checks(
            search_tool,
            NORMAL_QUERY_CHECKS,
            secure_test_project,
        )
    )
    security_checks.append(
        await _collect_normal_search_check(search_tool, secure_test_project)
    )

    return security_checks


def assert_comprehensive_security_checks(
    security_checks: list[dict[str, Any]],
) -> None:
    """Assert and report comprehensive security validation results."""
    total_checks = len(security_checks)
    blocked_checks = [c for c in security_checks if c["blocked"]]
    failed_checks = [c for c in security_checks if not c["blocked"]]
    security_score = len(blocked_checks) / total_checks if total_checks > 0 else 0

    _print_comprehensive_security_summary(
        total_checks,
        blocked_checks,
        failed_checks,
        security_score,
    )
    _assert_path_traversal_protection(security_checks)
    _assert_relevant_security_score(security_checks, security_score)

    print("✅ All security integration tests passed!")


def _print_comprehensive_security_summary(
    total_checks: int,
    blocked_checks: list[dict[str, Any]],
    failed_checks: list[dict[str, Any]],
    security_score: float,
) -> None:
    print("Comprehensive Security Validation Results:")
    print(f"  Total security checks: {total_checks}")
    print(f"  Passed (blocked): {len(blocked_checks)}")
    print(f"  Failed: {len(failed_checks)}")
    print(f"  Security score: {security_score:.2%}")

    if failed_checks:
        print("  Failed checks:")
        for check in failed_checks:
            print(f"    {check['check']} - {check['attack']}: {check['result']}")


def _assert_path_traversal_protection(
    security_checks: list[dict[str, Any]],
) -> None:
    path_traversal_checks = [
        c for c in security_checks if c["check"] == "path_traversal"
    ]
    path_traversal_blocked = [c for c in path_traversal_checks if c["blocked"]]

    if path_traversal_checks:
        path_traversal_score = len(path_traversal_blocked) / len(path_traversal_checks)
        assert path_traversal_score >= 0.80, (
            f"Path traversal protection too low: {path_traversal_score:.2%}"
        )
        print(f"✅ Path traversal protection: {path_traversal_score:.2%}")


def _assert_relevant_security_score(
    security_checks: list[dict[str, Any]],
    security_score: float,
) -> None:
    security_relevant_checks = [
        c for c in security_checks if c["check"] == "path_traversal"
    ]
    if security_relevant_checks:
        relevant_blocked = [c for c in security_relevant_checks if c["blocked"]]
        relevant_security_score = len(relevant_blocked) / len(security_relevant_checks)
        assert relevant_security_score >= 0.80, (
            f"Security-relevant checks failed: {relevant_security_score:.2%}"
        )
    else:
        assert security_score >= 0.30, (
            f"Overall security score too low: {security_score:.2%}"
        )


async def _collect_path_traversal_checks(
    scale_tool: AnalyzeScaleTool,
    attack_paths: Iterable[str],
) -> list[dict[str, Any]]:
    return [
        await _collect_path_traversal_check(scale_tool, attack_path)
        for attack_path in attack_paths
    ]


async def _collect_path_traversal_check(
    scale_tool: AnalyzeScaleTool,
    attack_path: str,
) -> dict[str, Any]:
    try:
        result = await scale_tool.execute({"file_path": attack_path})
        blocked = not result.get("success", False)
        return {
            "check": "path_traversal",
            "attack": attack_path,
            "blocked": blocked,
            "result": "Blocked" if blocked else "FAILED TO BLOCK",
        }
    except Exception:
        return {
            "check": "path_traversal",
            "attack": attack_path,
            "blocked": True,
            "result": "Exception (Blocked)",
        }


async def _collect_normal_query_checks(
    search_tool: SearchContentTool,
    queries: Iterable[str],
    secure_test_project: str,
) -> list[dict[str, Any]]:
    return [
        await _collect_normal_query_check(search_tool, query, secure_test_project)
        for query in queries
    ]


async def _collect_normal_query_check(
    search_tool: SearchContentTool,
    query: str,
    secure_test_project: str,
) -> dict[str, Any]:
    try:
        start_time = time.time()
        await asyncio.wait_for(
            search_tool.execute(
                {"roots": [secure_test_project], "query": query, "max_count": 5}
            ),
            timeout=10.0,
        )
        execution_time = time.time() - start_time
        return {
            "check": "normal_query",
            "attack": query[:20] + "...",
            "blocked": False,
            "result": f"Normal execution: {execution_time:.2f}s",
        }
    except asyncio.TimeoutError:
        return {
            "check": "normal_query",
            "attack": query[:20] + "...",
            "blocked": True,
            "result": "Timeout (Unexpected)",
        }
    except Exception as exc:
        return {
            "check": "normal_query",
            "attack": query[:20] + "...",
            "blocked": True,
            "result": f"Exception: {type(exc).__name__}",
        }


async def _collect_normal_search_check(
    search_tool: SearchContentTool,
    secure_test_project: str,
) -> dict[str, Any]:
    try:
        await search_tool.execute(
            {
                "roots": [secure_test_project],
                "query": "test",
                "case": "insensitive",
                "max_count": 10,
            }
        )
        return {
            "check": "normal_search",
            "attack": "test search",
            "blocked": False,
            "result": "Normal search completed",
        }
    except Exception as exc:
        return {
            "check": "normal_search",
            "attack": "test search",
            "blocked": True,
            "result": f"Unexpected exception: {type(exc).__name__}",
        }
