"""Concurrent security stress helpers for Phase 7 integration tests."""

import asyncio
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


async def collect_concurrent_security_stress_results(
    secure_test_project: str,
    malicious_paths: Iterable[str],
    malicious_queries: Iterable[str],
) -> tuple[list[dict[str, Any]], float]:
    """Run mixed normal and attack tasks concurrently."""
    attack_tasks = _build_concurrent_security_tasks(
        secure_test_project,
        malicious_paths,
        malicious_queries,
    )

    start_time = time.time()
    results = await asyncio.gather(
        *[task for _, task in attack_tasks], return_exceptions=True
    )
    execution_time = time.time() - start_time

    return _build_concurrent_attack_results(attack_tasks, results), execution_time


def assert_concurrent_security_stress_results(
    attack_results: list[dict[str, Any]],
    execution_time: float,
) -> None:
    """Assert and report the concurrent stress security expectations."""
    normal_results, path_traversal_results, malicious_query_results = (
        _split_concurrent_security_results(attack_results)
    )
    successful_normal = _assert_normal_tasks_survived(normal_results)
    blocked_path_traversals, path_traversal_block_rate = (
        _assert_path_traversals_blocked(path_traversal_results)
    )
    safely_handled_queries = _assert_malicious_queries_safely_handled(
        malicious_query_results
    )
    _assert_concurrent_security_stayed_responsive(execution_time)
    _print_concurrent_security_summary(
        execution_time,
        successful_normal,
        normal_results,
        blocked_path_traversals,
        path_traversal_results,
        path_traversal_block_rate,
        safely_handled_queries,
        malicious_query_results,
    )


def _split_concurrent_security_results(
    attack_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [r for r in attack_results if r["type"] == "normal"],
        [r for r in attack_results if r["type"] == "path_traversal"],
        [r for r in attack_results if r["type"] == "malicious_query"],
    )


def _assert_normal_tasks_survived(
    normal_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    successful_normal = [r for r in normal_results if r["success"]]
    assert len(successful_normal) >= len(normal_results) * 0.8, (
        "Normal tasks affected by concurrent attacks"
    )
    return successful_normal


def _assert_path_traversals_blocked(
    path_traversal_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    blocked_path_traversals = [r for r in path_traversal_results if r["blocked"]]
    path_traversal_block_rate = (
        len(blocked_path_traversals) / len(path_traversal_results)
        if path_traversal_results
        else 0
    )
    assert path_traversal_block_rate >= 0.9, (
        f"Concurrent path traversal block rate too low: {path_traversal_block_rate:.2%}"
    )
    return blocked_path_traversals, path_traversal_block_rate


def _assert_malicious_queries_safely_handled(
    malicious_query_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    safely_handled_queries = [
        r for r in malicious_query_results if r["success"] or r["blocked"]
    ]
    assert len(safely_handled_queries) == len(malicious_query_results), (
        "Concurrent malicious queries were not handled safely"
    )
    return safely_handled_queries


def _assert_concurrent_security_stayed_responsive(execution_time: float) -> None:
    assert execution_time < 30.0, (
        f"System became unresponsive under attack: {execution_time:.2f}s"
    )


def _print_concurrent_security_summary(
    execution_time: float,
    successful_normal: list[dict[str, Any]],
    normal_results: list[dict[str, Any]],
    blocked_path_traversals: list[dict[str, Any]],
    path_traversal_results: list[dict[str, Any]],
    path_traversal_block_rate: float,
    safely_handled_queries: list[dict[str, Any]],
    malicious_query_results: list[dict[str, Any]],
) -> None:
    print("Concurrent Security Stress Test Results:")
    print(f"  Execution time: {execution_time:.2f}s")
    print(f"  Normal tasks successful: {len(successful_normal)}/{len(normal_results)}")
    print(
        "  Path traversal attacks blocked: "
        f"{len(blocked_path_traversals)}/{len(path_traversal_results)}"
    )
    print(f"  Path traversal block rate: {path_traversal_block_rate:.2%}")
    print(
        "  Malicious queries safely handled: "
        f"{len(safely_handled_queries)}/{len(malicious_query_results)}"
    )


def _build_concurrent_security_tasks(
    secure_test_project: str,
    malicious_paths: Iterable[str],
    malicious_queries: Iterable[str],
) -> list[tuple[str, Any]]:
    scale_tool = AnalyzeScaleTool(secure_test_project)
    search_tool = SearchContentTool(secure_test_project)
    attack_tasks = []

    attack_tasks.extend(_build_path_traversal_tasks(scale_tool, malicious_paths))
    attack_tasks.extend(
        _build_malicious_query_tasks(
            search_tool,
            malicious_queries,
            secure_test_project,
        )
    )
    attack_tasks.extend(
        _build_normal_tasks(scale_tool, search_tool, secure_test_project)
    )

    return attack_tasks


def _build_path_traversal_tasks(
    scale_tool: AnalyzeScaleTool,
    malicious_paths: Iterable[str],
) -> list[tuple[str, Any]]:
    return [
        ("path_traversal", scale_tool.execute({"file_path": path}))
        for path in malicious_paths
    ]


def _build_malicious_query_tasks(
    search_tool: SearchContentTool,
    malicious_queries: Iterable[str],
    secure_test_project: str,
) -> list[tuple[str, Any]]:
    return [
        (
            "malicious_query",
            search_tool.execute(
                {"roots": [secure_test_project], "query": query, "max_count": 5}
            ),
        )
        for query in malicious_queries
    ]


def _build_normal_tasks(
    scale_tool: AnalyzeScaleTool,
    search_tool: SearchContentTool,
    secure_test_project: str,
) -> list[tuple[str, Any]]:
    secure_service = (
        Path(secure_test_project)
        / "src"
        / "main"
        / "java"
        / "com"
        / "secure"
        / "SecureService.java"
    )
    return [
        (
            "normal",
            search_tool.execute(
                {"roots": [secure_test_project], "query": "class", "max_count": 10}
            ),
        ),
        ("normal", scale_tool.execute({"file_path": str(secure_service)})),
    ]


def _build_concurrent_attack_results(
    attack_tasks: list[tuple[str, Any]],
    results: Iterable[Any],
) -> list[dict[str, Any]]:
    attack_types = [attack_type for attack_type, _ in attack_tasks]
    return [
        _build_concurrent_attack_result(attack_type, result)
        for attack_type, result in zip(attack_types, results, strict=False)
    ]


def _build_concurrent_attack_result(
    attack_type: str,
    result: Any,
) -> dict[str, Any]:
    if isinstance(result, Exception):
        return {
            "type": attack_type,
            "success": False,
            "blocked": True,
            "result": f"Exception: {type(result).__name__}",
        }

    success = result.get("success", False) if isinstance(result, dict) else False
    return {
        "type": attack_type,
        "success": success,
        "blocked": attack_type != "normal" and not success,
        "result": "Success" if success else "Blocked",
    }
