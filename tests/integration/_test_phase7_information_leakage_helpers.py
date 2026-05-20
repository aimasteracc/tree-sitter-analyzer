"""Information leakage helpers for Phase 7 security integration tests."""

from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

SENSITIVE_ERROR_FRAGMENTS = [
    "passwd",
    "shadow",
    "sam",
    "config",
    "system32",
    "administrator",
    "root",
    "admin",
    "/etc/",
    "c:\\windows",
]

SENSITIVE_EXCEPTION_FRAGMENTS = [
    "passwd",
    "shadow",
    "sam",
    "config",
    "system32",
]

SENSITIVE_PATH_FRAGMENTS = [
    "/etc/passwd",
    "C:\\Windows\\System32",
    "/etc/shadow",
]


def create_information_leakage_test_cases(
    secure_test_project: str,
) -> list[dict[str, Any]]:
    """Return tool calls that should not leak sensitive path details."""
    return [
        {
            "tool": AnalyzeScaleTool(secure_test_project),
            "params": {"file_path": "/etc/passwd"},
            "description": "System file access",
        },
        {
            "tool": ReadPartialTool(secure_test_project),
            "params": {
                "file_path": "C:\\Windows\\System32\\config\\SAM",
                "start_line": 1,
            },
            "description": "Windows system file access",
        },
        {
            "tool": SearchContentTool(secure_test_project),
            "params": {"roots": ["/etc"], "query": "password"},
            "description": "System directory search",
        },
    ]


async def collect_information_leakage_results(
    error_test_cases: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute error cases and summarize leakage safety."""
    return [
        await _collect_information_leakage_result(test_case)
        for test_case in error_test_cases
    ]


async def _collect_information_leakage_result(
    test_case: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await test_case["tool"].execute(test_case["params"])
        return _build_result_leakage_summary(test_case["description"], result)
    except Exception as exc:
        return _build_exception_leakage_summary(test_case["description"], exc)


def _build_result_leakage_summary(
    description: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    error_message = result.get("error", "")
    sensitive_info_leaked = _contains_any(
        error_message.lower(),
        SENSITIVE_ERROR_FRAGMENTS,
    )
    path_info_leaked = _contains_any(error_message, SENSITIVE_PATH_FRAGMENTS)
    return {
        "description": description,
        "sensitive_info_leaked": sensitive_info_leaked,
        "path_info_leaked": path_info_leaked,
        "error_message": _truncate_error_message(error_message),
        "safe": not (sensitive_info_leaked or path_info_leaked),
    }


def _build_exception_leakage_summary(
    description: str,
    exc: Exception,
) -> dict[str, Any]:
    error_message = str(exc)
    sensitive_info_leaked = _contains_any(
        error_message.lower(),
        SENSITIVE_EXCEPTION_FRAGMENTS,
    )
    return {
        "description": description,
        "sensitive_info_leaked": sensitive_info_leaked,
        "path_info_leaked": False,
        "error_message": _truncate_error_message(error_message),
        "safe": not sensitive_info_leaked,
    }


def _contains_any(value: str, fragments: Iterable[str]) -> bool:
    return any(fragment in value for fragment in fragments)


def _truncate_error_message(error_message: str) -> str:
    return error_message[:100] + "..." if len(error_message) > 100 else error_message
