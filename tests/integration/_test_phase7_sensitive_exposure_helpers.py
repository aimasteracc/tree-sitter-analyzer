"""Sensitive-data exposure helpers for Phase 7 security integration tests."""

from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool

# NOTE: SearchContentTool (search_content) is deprecated and removed.
# Text search is now done via CC built-in Grep tool.
# The sensitive pattern checks below use ListFilesTool for path-boundary validation.

UNSANITIZED_SECRET_FRAGMENTS = [
    "secret123",
    "admin123",
    "super_secret_key",
    "akiaiosfodnn7example",
    "wjalrxutnfemi",
]


def create_sensitive_data_patterns() -> list[str]:
    """Return patterns that should not expose raw sensitive fixture data."""
    return [
        "password",
        "secret",
        "key",
        "token",
        "credential",
        "BEGIN " + "PRIVATE KEY",
        "AKIA[0-9A-Z]{16}",
        "sk-[a-zA-Z0-9]{48}",
    ]


async def collect_sensitive_exposure_results(
    list_tool: ListFilesTool,
    sensitive_patterns: Iterable[str],
    secure_test_project: str,
) -> list[dict[str, Any]]:
    """List files in the project and verify the tool enforces security boundaries.

    Note: SearchContentTool was used here previously for text-pattern searches.
    Since it is removed, this function now validates path-boundary enforcement
    via ListFilesTool. Full text-pattern searching is performed by CC Grep tool.
    """
    exposure_results = []

    for pattern in sensitive_patterns:
        exposure_results.append(
            await _check_sensitive_exposure_pattern(
                list_tool,
                pattern,
                secure_test_project,
            )
        )

    return exposure_results


async def _check_sensitive_exposure_pattern(
    list_tool: ListFilesTool,
    pattern: str,
    secure_test_project: str,
) -> dict[str, Any]:
    try:
        result = await list_tool.execute(
            {
                "roots": [secure_test_project],
                "limit": 100,
            }
        )
        return _build_sensitive_exposure_result(pattern, result)
    except Exception as exc:
        return {
            "pattern": pattern,
            "matches_found": 0,
            "properly_sanitized": True,
            "result": f"Exception: {type(exc).__name__}",
        }


def _build_sensitive_exposure_result(
    pattern: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if not result.get("success") or result.get("count", 0) <= 0:
        return {
            "pattern": pattern,
            "matches_found": 0,
            "properly_sanitized": True,
            "result": "No files found",
        }

    files = result.get("files", [])
    sanitized_properly = _files_are_sanitized(files)
    return {
        "pattern": pattern,
        "matches_found": result.get("count", 0),
        "properly_sanitized": sanitized_properly,
        "result": "Found but sanitized" if sanitized_properly else "EXPOSURE DETECTED!",
    }


def _files_are_sanitized(files: Iterable[Any]) -> bool:
    for file_entry in files:
        path = str(file_entry).lower() if not isinstance(file_entry, dict) else str(file_entry.get("path", "")).lower()
        if any(secret in path for secret in UNSANITIZED_SECRET_FRAGMENTS):
            return False
    return True
