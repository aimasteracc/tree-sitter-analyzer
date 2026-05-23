"""Verify ``BaseMCPTool.get_output_schema`` returns the canonical envelope.

PL-C: the canonical ``outputSchema`` is the contract every MCP tool
inherits from :class:`BaseMCPTool`. These tests pin the required envelope
fields (``success`` + ``verdict``), the enum constraint on ``verdict``
(must equal the canonical vocabulary), and the open-payload posture
(``additionalProperties=True``) that lets tool subclasses layer their
own response fields without overriding the schema.

If any of these tests fail, the agent-facing contract has drifted —
clients that validate responses against the schema will start rejecting
otherwise well-formed envelopes.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.mcp.tools.base_tool import (
    _LEGAL_VERDICTS,
    BaseMCPTool,
)


class _StubTool(BaseMCPTool):
    """Minimal concrete subclass for instantiation.

    Every abstract method gets a no-op implementation. The
    ``__init_subclass__`` hook still wraps ``execute`` for strict-param
    enforcement, but with an empty ``inputSchema`` no parameter is
    rejected — the wrapper is a transparent passthrough here.
    """

    def get_tool_definition(self) -> dict[str, Any]:
        return {}

    def get_tool_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {}

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True


def test_output_schema_has_required_envelope_fields():
    """Top-level shape: object with success+verdict required, enum tied to canon."""
    schema = _StubTool().get_output_schema()
    assert schema["type"] == "object"
    assert "success" in schema["properties"]
    assert "verdict" in schema["properties"]
    # The verdict enum MUST equal the canonical vocabulary. Sorting makes
    # the assertion stable regardless of how the underlying frozenset
    # orders its members at iteration time.
    assert schema["properties"]["verdict"]["enum"] == sorted(_LEGAL_VERDICTS)
    assert "success" in schema["required"]
    assert "verdict" in schema["required"]


def test_output_schema_allows_payload_extension():
    """``additionalProperties=True`` so tools can attach arbitrary payloads.

    Tightening this to ``False`` would force every PR that adds a new
    payload field to also touch the base schema — that's exactly the
    coupling we're trying to avoid by putting the envelope here.
    """
    schema = _StubTool().get_output_schema()
    assert schema["additionalProperties"] is True


def test_output_schema_agent_summary_mirrors_verdict_enum():
    """Nested agent_summary.verdict must also use the canonical vocabulary.

    M10 / mirror_summary_line keeps top-level and agent_summary verdicts
    in sync at runtime; the schema's enum must mirror that contract or
    a validator could accept ``agent_summary.verdict="garbage"`` while
    runtime canonicalisation forces it back to INFO.
    """
    schema = _StubTool().get_output_schema()
    agent_summary = schema["properties"]["agent_summary"]
    assert agent_summary["type"] == "object"
    assert agent_summary["properties"]["verdict"]["enum"] == sorted(_LEGAL_VERDICTS)
