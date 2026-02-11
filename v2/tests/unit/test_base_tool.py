"""
Parameterized tests for BaseTool utility methods.

Tests cover:
- _detect_language_from_path: Language detection from file extensions
- _error: Standard error response creation
- _validate_path_safe: Path traversal protection
- validate_arguments: JSON schema argument validation
- get_tool_definition: Standard tool definition format
"""

import pytest
from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


# ── Concrete BaseTool for testing ──

class _DummyTool(BaseTool):
    """Minimal concrete BaseTool for testing abstract base."""

    def get_name(self) -> str:
        return "dummy_tool"

    def get_description(self) -> str:
        return "A dummy tool for testing"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file"},
                "count": {"type": "integer", "description": "A count"},
                "verbose": {"type": "boolean", "description": "Verbose flag"},
            },
            "required": ["file_path"],
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True}


# ── Language detection tests (parameterized) ──


@pytest.mark.parametrize(
    "file_path, expected",
    [
        ("test.py", "python"),
        ("module.pyw", "python"),
        ("Main.java", "java"),
        ("app.ts", "typescript"),
        ("component.tsx", "typescript"),
        ("index.js", "javascript"),
        ("app.jsx", "javascript"),
        (None, "python"),
        ("unknown.xyz", "python"),
        ("README.md", "python"),
        ("", "python"),
    ],
    ids=[
        "python-.py",
        "python-.pyw",
        "java-.java",
        "typescript-.ts",
        "typescript-.tsx",
        "javascript-.js",
        "javascript-.jsx",
        "none-default",
        "unknown-default",
        "markdown-default",
        "empty-default",
    ],
)
def test_detect_language_from_path(file_path: str | None, expected: str) -> None:
    """Language detection should map file extensions correctly."""
    assert BaseTool._detect_language_from_path(file_path) == expected


@pytest.mark.parametrize(
    "file_path, default, expected",
    [
        ("test.py", "java", "python"),
        ("unknown.xyz", "java", "java"),
        (None, "typescript", "typescript"),
    ],
    ids=["override-ignored", "fallback-used", "none-fallback"],
)
def test_detect_language_custom_default(
    file_path: str | None, default: str, expected: str
) -> None:
    """Custom default should be used when detection fails."""
    assert BaseTool._detect_language_from_path(file_path, default=default) == expected


# ── Error helper tests (parameterized) ──


@pytest.mark.parametrize(
    "message, code",
    [
        ("File not found", "FILE_NOT_FOUND"),
        ("Invalid argument", "INVALID_ARGUMENT"),
        ("Security violation", "SECURITY_VIOLATION"),
        ("Internal error", "INTERNAL_ERROR"),
    ],
)
def test_error_helper(message: str, code: str) -> None:
    """_error should produce consistent error dict structure."""
    result = BaseTool._error(message, error_code=code)
    assert result["success"] is False
    assert result["error"] == message
    assert result["error_code"] == code


# ── Path validation tests (parameterized) ──


@pytest.mark.parametrize(
    "path, should_pass",
    [
        ("src/main.py", True),
        ("../etc/passwd", False),
        ("src/../../../etc/shadow", False),
        ("normal/file.txt", True),
    ],
    ids=["normal-path", "parent-traversal", "deep-traversal", "simple-file"],
)
def test_validate_path_safe_no_root(path: str, should_pass: bool) -> None:
    """Path validation without project_root should catch '..' patterns."""
    result = BaseTool._validate_path_safe(path)
    if should_pass:
        assert result is None
    else:
        assert result is not None
        assert result["error_code"] == "SECURITY_VIOLATION"


def test_validate_path_safe_inside_root(tmp_path: Any) -> None:
    """Absolute path inside project root should pass."""
    file_path = str(tmp_path / "src" / "main.py")
    result = BaseTool._validate_path_safe(file_path, project_root=str(tmp_path))
    assert result is None


def test_validate_path_safe_outside_root(tmp_path: Any) -> None:
    """Absolute path outside project root should fail."""
    import os
    outside = os.path.abspath(os.sep)  # Root of filesystem
    result = BaseTool._validate_path_safe(
        os.path.join(outside, "etc", "passwd"),
        project_root=str(tmp_path),
    )
    assert result is not None
    assert result["error_code"] == "SECURITY_VIOLATION"


# ── Argument validation tests (parameterized) ──


@pytest.mark.parametrize(
    "args, expected_error_count",
    [
        ({"file_path": "test.py"}, 0),
        ({"file_path": "test.py", "count": 5}, 0),
        ({}, 1),  # Missing required 'file_path'
        ({"count": 5}, 1),  # Missing required 'file_path'
        ({"file_path": 123}, 1),  # Wrong type for 'file_path'
        ({"file_path": "test.py", "count": "not_int"}, 1),  # Wrong type for 'count'
        ({"file_path": "test.py", "verbose": "not_bool"}, 1),  # Wrong type for 'verbose'
        ({"file_path": "test.py", "extra_field": 42}, 0),  # Extra fields are OK
    ],
    ids=[
        "valid-minimal",
        "valid-with-optional",
        "missing-required",
        "missing-required-with-optional",
        "wrong-type-string",
        "wrong-type-integer",
        "wrong-type-boolean",
        "extra-fields-ok",
    ],
)
def test_validate_arguments(args: dict[str, Any], expected_error_count: int) -> None:
    """validate_arguments should enforce required fields and types."""
    tool = _DummyTool()
    errors = tool.validate_arguments(args)
    assert len(errors) == expected_error_count


# ── get_tool_definition tests ──


def test_get_tool_definition_structure() -> None:
    """get_tool_definition should return standard MCP format."""
    tool = _DummyTool()
    defn = tool.get_tool_definition()
    assert defn["name"] == "dummy_tool"
    assert "description" in defn
    assert "inputSchema" in defn
    assert defn["inputSchema"]["type"] == "object"
    assert "file_path" in defn["inputSchema"]["properties"]


# ── Type checking tests (parameterized) ──


@pytest.mark.parametrize(
    "value, expected_type, result",
    [
        ("hello", "string", True),
        (42, "integer", True),
        (3.14, "number", True),
        (42, "number", True),
        (True, "boolean", True),
        ([1, 2], "array", True),
        ({"a": 1}, "object", True),
        ("hello", "integer", False),
        (42, "string", False),
        (None, "unknown_type", True),  # Unknown types are accepted
    ],
    ids=[
        "string-ok",
        "integer-ok",
        "float-number-ok",
        "int-number-ok",
        "boolean-ok",
        "array-ok",
        "object-ok",
        "string-not-integer",
        "integer-not-string",
        "unknown-type-accepted",
    ],
)
def test_check_type(value: Any, expected_type: str, result: bool) -> None:
    """_check_type should validate JSON schema types correctly."""
    assert BaseTool._check_type(value, expected_type) == result
