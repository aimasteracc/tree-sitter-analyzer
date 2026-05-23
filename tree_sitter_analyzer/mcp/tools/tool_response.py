"""Typed envelope for MCP tool responses (ARCH-A5).

Every ``BaseMCPTool.execute()`` returns a JSON-serialisable dict. Before
this module the shape was governed by convention only: ``success`` was
expected to exist, ``error`` *might* exist on failures, payload keys
were tool-specific. External consumers (Claude Code, Cursor, Cline, and
the project's own CLI) end up depending on this implicit shape, which
means any tool quietly changing it breaks downstream parsers.

Goals
-----

* **Document** the response contract that 23 MCP tools already follow.
* **Enforce** the minimum invariants (``success`` is bool; if False,
  ``error`` is a str) via a contract test that introspects every tool.
* **Don't** force every tool to wrap its payload in a ``data`` key —
  back-compat with the current consumers is more valuable than a
  prettier envelope. The TypedDict is intentionally permissive (other
  keys allowed via ``__extra_items__`` in spirit; we just type the
  guaranteed ones).

Usage
-----

A tool's ``execute()`` may still return a plain ``dict[str, Any]``.
The TypedDict is the *recommended* annotation when you want call-site
type-checking, e.g.::

    async def execute(self, args: dict[str, Any]) -> ToolResponse:
        return {"success": True, "payload": {...}}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    # No runtime cost — just for the contract test's introspection.
    pass


#: Canonical verdict vocabulary used across every tsa-landing-eligible
#: tool. Agents branching on verdict expect EXACTLY one of these strings —
#: anything else (CLEAN, LOOKS_GOOD, READY, etc.) silently falls through
#: to default-INFO behavior and turns into a real bug at the agent layer.
CANONICAL_VERDICTS: frozenset[str] = frozenset(
    {
        "SAFE",
        "CAUTION",
        "REVIEW",
        "UNSAFE",
        "INFO",
        "WARN",
        "ERROR",
        "NOT_FOUND",
    }
)


class ToolResponse(TypedDict, total=False):
    """The shape every MCP tool response should follow.

    All keys are optional in the TypedDict sense so partial dicts still
    type-check, but the contract test below makes ``success`` mandatory
    for runtime acceptance.
    """

    success: bool
    """Whether the tool ran end-to-end without raising. Mandatory."""

    verdict: str
    """Canonical agent-facing verdict for branching. MUST be one of the
    strings in :data:`CANONICAL_VERDICTS`. Optional today (the contract
    test only requires it when the key is present and rejects non-canonical
    values), but every landing-surface tool now sets it."""

    error: str
    """Human-readable failure description. MUST be present when
    ``success`` is False; absent when ``success`` is True."""

    mode: str
    """Optional sub-mode label for tools that expose multiple modes
    (e.g. detect_routes has summary/all/lookup/prefix/file)."""

    toon_content: str
    """When the caller asked for TOON output (``output_format='toon'``),
    the TOON-encoded body lands here. The same payload data should be
    present at top level for ``output_format='json'`` callers."""


def validate_tool_response(payload: Any, tool_name: str = "<unknown>") -> None:
    """Raise ``AssertionError`` if ``payload`` doesn't honour the
    ``ToolResponse`` minimum invariants.

    The contract test calls this on every tool's actual response. It is
    deliberately a hard ``AssertionError`` (not ``ValueError``) because
    the only legitimate caller is pytest.
    """
    assert isinstance(payload, dict), (
        f"{tool_name}: ToolResponse must be a dict, got {type(payload).__name__}"
    )
    assert "success" in payload, (
        f"{tool_name}: ToolResponse must include a 'success' key"
    )
    success = payload["success"]
    assert isinstance(success, bool), (
        f"{tool_name}: ToolResponse['success'] must be bool, got "
        f"{type(success).__name__}"
    )
    if not success:
        # Failures MUST surface an error. Successes may omit one entirely.
        assert "error" in payload, (
            f"{tool_name}: ToolResponse with success=False must include 'error'"
        )
        assert isinstance(payload["error"], str), (
            f"{tool_name}: ToolResponse['error'] must be str, got "
            f"{type(payload['error']).__name__}"
        )
    # When ``verdict`` is present it MUST be a canonical value. Tools that
    # emit non-canonical strings (CLEAN, NEEDS_REVIEW, LOOKS_GOOD, READY,
    # ...) cause silent agent miscoordination — pains #9, #93 in the UX log.
    if "verdict" in payload:
        verdict = payload["verdict"]
        assert isinstance(verdict, str), (
            f"{tool_name}: ToolResponse['verdict'] must be str, got "
            f"{type(verdict).__name__}"
        )
        assert verdict in CANONICAL_VERDICTS, (
            f"{tool_name}: ToolResponse['verdict']={verdict!r} is not in "
            f"the canonical set {sorted(CANONICAL_VERDICTS)}"
        )


__all__ = ["CANONICAL_VERDICTS", "ToolResponse", "validate_tool_response"]
