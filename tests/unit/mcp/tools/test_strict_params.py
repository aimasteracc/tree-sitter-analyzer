"""Tests for strict parameter enforcement in MCP tools.

F5 (round-16b): unknown top-level parameters must be rejected with a
did-you-mean hint. The enforcement logic lives in two places:

1. ``mcp/utils/schema_strictness.py`` — the ``enforce_strict_params``
   function (the pure logic, tested independently in test_validators.py).
2. ``BaseMCPTool.__init_subclass__`` — wraps every subclass's ``execute``
   coroutine once, calling ``_guard_strict_parameters`` before dispatch.

These tests verify the end-to-end behavior: that an unknown argument
passed to a concrete tool's ``execute()`` raises ``ValueError`` with the
expected hint, and that known arguments pass through unobstructed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool


# ---------------------------------------------------------------------------
# Minimal concrete tool — only one known parameter: ``file_path``
# ---------------------------------------------------------------------------

class _StrictTool(BaseMCPTool):
    """Minimal concrete subclass with a single declared parameter."""

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
            },
        }

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "strict_tool",
            "inputSchema": self.get_tool_schema(),
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "verdict": "INFO", "file_path": arguments.get("file_path")}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


class TestStrictParamsViaBaseTool:
    """__init_subclass__ wraps execute; unknown params are rejected."""

    def test_known_param_passes_through(self) -> None:
        tool = _StrictTool()
        result = _run(tool.execute({"file_path": "foo.py"}))
        assert result["success"] is True

    def test_unknown_param_raises_value_error(self) -> None:
        tool = _StrictTool()
        with pytest.raises(ValueError, match="unknown parameter"):
            _run(tool.execute({"typo_param": "foo.py"}))

    def test_did_you_mean_hint_for_close_match(self) -> None:
        tool = _StrictTool()
        with pytest.raises(ValueError, match="file_path"):
            # ``file_paths`` is close to ``file_path`` — hint should surface
            _run(tool.execute({"file_paths": "foo.py"}))

    def test_output_format_is_universal_param_and_passes(self) -> None:
        # ``output_format`` is in ``_UNIVERSAL_ENVELOPE_PARAMS`` — always allowed.
        tool = _StrictTool()
        result = _run(tool.execute({"file_path": "foo.py", "output_format": "json"}))
        assert result["success"] is True

    def test_empty_arguments_passes(self) -> None:
        tool = _StrictTool()
        result = _run(tool.execute({}))
        assert result["success"] is True

    def test_execute_wrapper_is_idempotent(self) -> None:
        """Subclassing _StrictTool must not double-wrap execute."""
        class _DerivedTool(_StrictTool):
            pass

        tool = _DerivedTool()
        result = _run(tool.execute({"file_path": "bar.py"}))
        assert result["success"] is True


class TestStrictParamsOptOut:
    """additionalProperties=True lets a tool accept arbitrary keys."""

    def test_additional_properties_true_skips_strict_check(self) -> None:
        class _FlexTool(BaseMCPTool):
            def get_tool_schema(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                    "additionalProperties": True,
                }

            def get_tool_definition(self) -> dict[str, Any]:
                return {"name": "flex_tool", "inputSchema": self.get_tool_schema()}

            async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
                return {"success": True, "verdict": "INFO"}

            def validate_arguments(self, arguments: dict[str, Any]) -> bool:
                return True

        tool = _FlexTool()
        # No ValueError — the tool opted out of strict mode.
        result = _run(tool.execute({"file_path": "foo.py", "unknown_extra": "x"}))
        assert result["success"] is True
