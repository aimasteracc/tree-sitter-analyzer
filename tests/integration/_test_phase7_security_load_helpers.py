"""Security-under-load helpers for Phase 7 integration tests."""

import asyncio
import time
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


async def collect_security_under_load_results(
    secure_test_project: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], float, int]:
    """Run mixed security load and classify attack outcomes."""
    concurrent_attacks = _build_security_under_load_tasks(secure_test_project)

    start_time = time.time()
    results = await asyncio.gather(
        *[task for _, task in concurrent_attacks], return_exceptions=True
    )
    execution_time = time.time() - start_time

    successful_attacks, blocked_attacks = _classify_security_under_load_results(
        concurrent_attacks,
        results,
    )
    return successful_attacks, blocked_attacks, execution_time, len(concurrent_attacks)


def _build_security_under_load_tasks(
    secure_test_project: str,
) -> list[tuple[str, Any]]:
    concurrent_attacks = []

    for index in range(10):
        scale_tool = AnalyzeScaleTool(secure_test_project)
        concurrent_attacks.append(
            (
                "path_traversal",
                scale_tool.execute({"file_path": f"../../../etc/passwd{index}"}),
            )
        )

        search_tool = SearchContentTool(secure_test_project)
        search_params = {
            "roots": [secure_test_project],
            "query": f"test{index}",
            "max_count": 5,
        }
        concurrent_attacks.append(("search", search_tool.execute(search_params)))

    return concurrent_attacks


def _classify_security_under_load_results(
    concurrent_attacks: list[tuple[str, Any]],
    results: list[Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    successful_attacks = []
    blocked_attacks = []

    for attack_type, result in zip(
        [attack_type for attack_type, _ in concurrent_attacks],
        results,
        strict=False,
    ):
        _classify_security_under_load_result(
            attack_type,
            result,
            successful_attacks,
            blocked_attacks,
        )

    return successful_attacks, blocked_attacks


def _classify_security_under_load_result(
    attack_type: str,
    result: Any,
    successful_attacks: list[dict[str, str]],
    blocked_attacks: list[dict[str, str]],
) -> None:
    if isinstance(result, Exception):
        blocked_attacks.append({"type": attack_type, "result": "Exception"})
        return

    if not isinstance(result, dict):
        blocked_attacks.append({"type": attack_type, "result": "Blocked"})
        return

    if attack_type != "path_traversal":
        blocked_attacks.append({"type": attack_type, "result": "Normal"})
        return

    if result.get("success") and not ("error" in result or "Error" in str(result)):
        successful_attacks.append({"type": attack_type, "result": "Success"})
        return

    blocked_attacks.append({"type": attack_type, "result": "Blocked"})
