"""#1808/#1809: every MCP failure carries an ``error`` and a machine code.

``ensure_failure_identity`` runs at the ``BaseMCPTool.execute`` boundary and
inside the MCP server's error envelope, so a tool that returns a bare
``{"success": False}`` still answers with both fields, and a tool that set
them keeps its own values.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
    ensure_canonical_error_envelope,
    ensure_failure_identity,
)
from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.tool_response import envelope_violations


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"message": "cache is empty"}, "cache is empty"),
        ({"errors": ["ambiguous rename"]}, "ambiguous rename"),
        (
            {"errors": [{"error": "a"}, {"error": "b"}]},
            "2 errors; first: a",
        ),
        ({"summary_line": "x: not published"}, "x: not published"),
        ({"agent_summary": {"summary_line": "x: inner"}}, "x: inner"),
        ({"status": "timeout"}, "demo failed with status 'timeout'"),
        ({}, "demo failed without reporting an error message"),
    ],
)
def test_missing_error_is_derived_from_the_response(
    response: dict[str, Any], error: str
) -> None:
    result = ensure_failure_identity({"success": False, **response}, "demo")

    assert result["error"] == error
    assert isinstance(result["error_type"], str) and result["error_type"]
    assert envelope_violations(result) == []


def test_errors_list_without_text_falls_through() -> None:
    result = ensure_failure_identity(
        {"success": False, "errors": [3], "status": "failed"}, "demo"
    )

    assert result["error"] == "demo failed with status 'failed'"


def test_error_type_is_classified_from_the_message() -> None:
    result = ensure_failure_identity(
        {"success": False, "error": "Project root not set."}, "demo"
    )

    assert result["error_type"] == "project_not_set"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            "COMBINED_SCORE_UNAVAILABLE: activation pending",
            "COMBINED_SCORE_UNAVAILABLE",
        ),
        ("QUERY_EMBEDDING_DIMENSION_MISMATCH", "QUERY_EMBEDDING_DIMENSION_MISMATCH"),
    ],
)
def test_a_leading_code_becomes_the_error_code(error: str, code: str) -> None:
    result = ensure_failure_identity({"success": False, "error": error}, "demo")

    assert result["error_code"] == code
    assert "error_type" not in result


@pytest.mark.parametrize("error", ["ERROR happened", "Sync failed: X_Y", "AB: x"])
def test_prose_is_not_mistaken_for_a_code(error: str) -> None:
    result = ensure_failure_identity({"success": False, "error": error}, "demo")

    assert "error_code" not in result
    assert result["error_type"]


def test_empty_cache_is_an_index_not_ready_failure() -> None:
    result = ensure_failure_identity(
        {"success": False, "error": "AST cache is empty. Run ast_cache first."},
        "demo",
    )

    assert result["error_type"] == "index_not_ready"


def test_query_syntax_errors_are_validation_failures() -> None:
    result = ensure_failure_identity(
        {"success": False, "error": "Hyphae syntax error: unexpected ')'"}, "demo"
    )

    assert result["error_type"] == "validation"


@pytest.mark.parametrize("key", ["error_code", "error_type"])
def test_producer_values_are_kept(key: str) -> None:
    response = {"success": False, "error": "boom", key: "PRODUCER_CODE"}

    result = ensure_failure_identity(dict(response), "demo")

    assert result == response


@pytest.mark.parametrize(
    "response", [{"success": True}, {"error": "x"}, ["success", False], None]
)
def test_non_failures_are_untouched(response: Any) -> None:
    expected = response if not isinstance(response, dict) else dict(response)

    assert ensure_failure_identity(response, "demo") == expected


def test_mcp_error_envelope_now_always_has_error() -> None:
    result = ensure_canonical_error_envelope("demo", {"success": False})

    assert result["error"] == "demo failed without reporting an error message"
    assert result["error_type"] == "internal"
    assert result["verdict"] == "ERROR"


class _BareFailureTool(BaseMCPTool):
    """A tool whose failure names neither an error nor a code."""

    def get_tool_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    def get_tool_definition(self) -> dict[str, Any]:
        return {"name": "bare_failure", "inputSchema": self.get_tool_schema()}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": False, "status": "error"}


class _NamelessTool(_BareFailureTool):
    def get_tool_definition(self) -> dict[str, Any]:
        raise RuntimeError("no definition")

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": False}


@pytest.mark.tool_response_unchecked(reason="the tool under test is a test double")
def test_execute_boundary_fills_the_failure_identity() -> None:
    result = asyncio.run(_BareFailureTool().execute({}))

    assert result["error"] == "bare_failure failed with status 'error'"
    assert result["error_type"] == "internal"


@pytest.mark.tool_response_unchecked(reason="the tool under test is a test double")
def test_execute_boundary_falls_back_to_the_class_name() -> None:
    result = asyncio.run(_NamelessTool().execute({}))

    assert result["error"] == (
        "_NamelessTool failed without reporting an error message"
    )
