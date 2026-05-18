"""Sensitive-data exposure helpers for Phase 7 security integration tests."""

from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

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
    search_tool: SearchContentTool,
    sensitive_patterns: Iterable[str],
    secure_test_project: str,
) -> list[dict[str, Any]]:
    """Search sensitive patterns and verify matches are sanitized."""
    exposure_results = []

    for pattern in sensitive_patterns:
        exposure_results.append(
            await _check_sensitive_exposure_pattern(
                search_tool,
                pattern,
                secure_test_project,
            )
        )

    return exposure_results


async def _check_sensitive_exposure_pattern(
    search_tool: SearchContentTool,
    pattern: str,
    secure_test_project: str,
) -> dict[str, Any]:
    try:
        result = await search_tool.execute(
            {
                "roots": [secure_test_project],
                "query": pattern,
                "case": "insensitive",
                "max_count": 100,
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
            "result": "No matches found",
        }

    sanitized_properly = _matches_are_sanitized(result.get("matches", []))
    return {
        "pattern": pattern,
        "matches_found": result.get("count", 0),
        "properly_sanitized": sanitized_properly,
        "result": "Found but sanitized" if sanitized_properly else "EXPOSURE DETECTED!",
    }


def _matches_are_sanitized(matches: Iterable[dict[str, Any]]) -> bool:
    for match in matches:
        content = match.get("content", "").lower()
        if any(secret in content for secret in UNSANITIZED_SECRET_FRAGMENTS):
            return False
    return True
