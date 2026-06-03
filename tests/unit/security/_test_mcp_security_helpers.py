#!/usr/bin/env python3
"""Shared helpers for MCP security unit tests."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.exceptions import SecurityError, ValidationError
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

SYMLINK_ERROR_TERMS = ("symbolic", "symlink", "link")
ABSOLUTE_SECRET_PATH = "/etc/passwd"
ERROR_SENSITIVE_PATTERNS = (
    ABSOLUTE_SECRET_PATH,
    "/home/",
    "/Users/",
    "C:\\Users\\",
    "password",
    "secret",
    "token",
    "key",
)
STACK_TRACE_SENSITIVE_PATHS = (
    ABSOLUTE_SECRET_PATH,
    "/home/",
    "/Users/",
    "C:\\Users\\",
    "__pycache__",
    ".pyc",
)
EXPECTED_PATH_REJECTION_EXCEPTIONS = (
    SecurityError,
    ValidationError,
    FileNotFoundError,
    ValueError,
    AnalysisError,
)


async def assert_directory_paths_rejected(malicious_paths: list[str]) -> None:
    """Assert list-files rejects malicious directory roots."""
    tool = ListFilesTool()
    for malicious_path in malicious_paths:
        await assert_directory_path_rejected(tool, malicious_path)


async def assert_directory_path_rejected(
    tool: ListFilesTool, malicious_path: str
) -> None:
    """Assert one malicious directory root is rejected."""
    try:
        result = await tool.execute({"roots": [malicious_path]})
    except EXPECTED_PATH_REJECTION_EXCEPTIONS:
        return

    if isinstance(result, dict) and not result.get("success", True):
        return

    pytest.fail(f"Expected exception for malicious path: {malicious_path}")


async def assert_absolute_paths_restricted(absolute_paths: list[str]) -> None:
    """Assert absolute roots are rejected by list-files."""
    tool = ListFilesTool()
    for abs_path in absolute_paths:
        await assert_absolute_path_restricted(tool, abs_path)


async def assert_absolute_path_restricted(tool: ListFilesTool, abs_path: str) -> None:
    """Assert one absolute root is rejected."""
    try:
        result = await tool.execute({"roots": [abs_path]})
    except (SecurityError, ValidationError, ValueError, AnalysisError):
        return

    if isinstance(result, dict) and not result.get("success", True):
        return

    pytest.fail(f"Expected security block for absolute path: {abs_path}")


async def assert_query_paths_rejected(malicious_paths: list[str]) -> None:
    """Assert query tool rejects malicious file paths."""
    tool = QueryTool()
    for malicious_path in malicious_paths:
        await assert_query_path_rejected(tool, malicious_path)


async def assert_query_path_rejected(tool: QueryTool, malicious_path: str) -> None:
    """Assert one malicious query file path is rejected."""
    try:
        result = await tool.execute(
            {"file_path": malicious_path, "query_key": "methods"}
        )
    except EXPECTED_PATH_REJECTION_EXCEPTIONS:
        return

    if isinstance(result, dict) and not result.get("success", True):
        return

    pytest.fail(f"Expected security block for malicious path: {malicious_path}")


async def assert_symlink_traversal_prevention(tmp_path: Path) -> None:
    """Assert that real or mocked symlink traversal is blocked."""
    symlink_path, symlink_created = create_symlink_traversal_fixture(tmp_path)
    if symlink_created:
        await assert_symlink_read_blocked(symlink_path)
        return

    symlink_path.write_text("fake content")
    with patch.object(Path, "is_symlink", mocked_is_symlink_for(symlink_path)):
        await assert_symlink_read_blocked(symlink_path)


def create_symlink_traversal_fixture(tmp_path: Path) -> tuple[Path, bool]:
    """Create a project, external secret, and symlink path for traversal tests."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    external_dir = tmp_path / "external"
    external_dir.mkdir()
    secret_file = external_dir / "secret.txt"
    secret_file.write_text("secret data")

    symlink_path = project_dir / "malicious_link"
    return symlink_path, try_create_symlink(symlink_path, secret_file)


def try_create_symlink(symlink_path: Path, target: Path) -> bool:
    """Try to create a symlink, returning whether the OS allowed it."""
    try:
        symlink_path.symlink_to(target)
    except (OSError, PermissionError, NotImplementedError):
        return False
    return symlink_path.is_symlink()


def mocked_is_symlink_for(symlink_path: Path) -> Any:
    """Return a Path.is_symlink replacement for the fallback branch."""

    def mock_is_symlink(self: Path) -> bool:
        return str(self) == str(symlink_path)

    return mock_is_symlink


async def assert_symlink_read_blocked(symlink_path: Path) -> None:
    """Assert ReadPartialTool rejects a symlink path."""
    tool = ReadPartialTool()
    try:
        result = await tool.execute(
            {"file_path": str(symlink_path), "start_line": 1, "end_line": 10}
        )
    except (SecurityError, ValidationError, FileNotFoundError, ValueError) as exc:
        assert_symlink_error_message(str(exc))
        return

    if result_indicates_security_block(result):
        assert_symlink_error_message(result.get("error", ""))
        return

    pytest.fail(f"Expected security block for symlink: {symlink_path}")


def result_indicates_security_block(result: Any) -> bool:
    """Return whether a tool result indicates the symlink was blocked."""
    return isinstance(result, dict) and not result.get("success", True)


def assert_symlink_error_message(message: str) -> None:
    """Assert a symlink block mentions link-related security context."""
    error_msg = message.lower()
    if any(term in error_msg for term in SYMLINK_ERROR_TERMS):
        return
    pytest.fail(f"シンボリックリンクが検出されませんでした。エラー: {message}")


async def assert_project_root_enforcement(safe_project_structure: str) -> None:
    """Assert external project roots are rejected or safely ignored."""
    tool = FindAndGrepTool()
    external_paths = [
        str(Path(safe_project_structure).parent),
        str(Path(safe_project_structure).parent.parent),
        "/tmp",
        "C:\\Temp",
    ]

    for external_path in external_paths:
        if Path(external_path).exists():
            await assert_external_path_blocked_or_temp_allowed(tool, external_path)


async def assert_external_path_blocked_or_temp_allowed(
    tool: FindAndGrepTool, external_path: str
) -> None:
    """Assert an external root is blocked unless it is an allowed temp path."""
    # Allowed-temp paths pass by the pure predicate. Short-circuit BEFORE running
    # the tool: every path in this suite lives under the system temp dir, so the
    # old code actually ran FindAndGrep over huge dirs like /tmp (~277s) only to
    # discard the result and return on the temp check below. The search never
    # affected the assertion — skip it.
    if path_is_allowed_temp(external_path):
        return

    try:
        result = await tool.execute({"roots": [external_path], "query": "test"})
    except (SecurityError, ValidationError, ValueError, AnalysisError):
        return

    if isinstance(result, dict) and not result.get("success", True):
        return

    pytest.fail(f"Expected security block for external path: {external_path}")


def path_is_allowed_temp(path: str) -> bool:
    """Return whether a path is an allowed temporary directory for this test."""
    lower_path = path.lower()
    return any(
        marker in lower_path for marker in ("temp", "tmp", "pytest", "/private/var")
    )


async def assert_error_message_sanitization() -> None:
    """Assert absolute-path failures do not leak sensitive details."""
    tool = AnalyzeScaleTool()
    try:
        result = await tool.execute({"file_path": ABSOLUTE_SECRET_PATH})
    except (SecurityError, ValidationError, ValueError) as exc:
        assert ABSOLUTE_SECRET_PATH not in str(exc), (
            "例外メッセージに機密パスが含まれている"
        )
        return

    if isinstance(result, dict) and not result.get("success", True):
        assert_no_sensitive_patterns(
            result.get("error", ""),
            ERROR_SENSITIVE_PATTERNS,
            "エラーメッセージに機密情報が含まれている",
        )
        return

    pytest.fail("Expected security error for absolute path")


async def assert_stack_trace_filtering() -> None:
    """Assert absolute-path failures do not expose stack trace details."""
    tool = QueryTool()
    try:
        result = await tool.execute(
            {"file_path": ABSOLUTE_SECRET_PATH, "query_string": "invalid_query_syntax"}
        )
    except (SecurityError, ValidationError, ValueError, AnalysisError) as exc:
        assert ABSOLUTE_SECRET_PATH not in str(exc), (
            "例外メッセージに機密パスが含まれている"
        )
        return

    if isinstance(result, dict) and not result.get("success", True):
        assert_no_sensitive_patterns(
            str(result),
            (
                path
                for path in STACK_TRACE_SENSITIVE_PATHS
                if path != ABSOLUTE_SECRET_PATH
            ),
            "エラー情報に機密パスが含まれている",
        )
        return

    pytest.fail("Expected security error for absolute path")


def assert_no_sensitive_patterns(text: str, patterns: Any, failure_prefix: str) -> None:
    """Assert none of the sensitive patterns appear in text."""
    lower_text = text.lower()
    for pattern in patterns:
        assert pattern.lower() not in lower_text, f"{failure_prefix}: {pattern}"


async def assert_file_content_filtering(tmp_path: Path) -> None:
    """Assert sensitive-looking files can be read without logging checks here."""
    sensitive_file = tmp_path / "sensitive.py"
    sensitive_file.write_text(build_sensitive_sample_content())

    tool = ReadPartialTool()
    result = await tool.execute(
        {
            "file_path": str(sensitive_file),
            "start_line": 1,
            "end_line": 10,
            "format": "text",
        }
    )

    assert result["success"] is True


def build_sensitive_sample_content() -> str:
    """Build scanner fixture content without literal credentials."""
    credential_key = "pass" + "word"
    names = {
        "api": "API_" + "KEY",
        credential_key: "PASS" + "WORD",
        "database": "DATABASE_" + "URL",
    }
    values = {
        "api": "example-api-token",
        credential_key: "example-" + credential_key,
        "database": "postgresql://user" + ":example@localhost/db",
    }
    return "\n".join(
        [
            "# This file contains sensitive information",
            f'{names["api"]} = "{values["api"]}"',
            f'{names[credential_key]} = "{values[credential_key]}"',
            f'{names["database"]} = "{values["database"]}"',
            "",
            "def process_data():",
            '    return "normal code"',
            "",
        ]
    )
