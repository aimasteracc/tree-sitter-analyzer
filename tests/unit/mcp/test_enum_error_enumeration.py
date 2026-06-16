"""Contract: every enum-mode rejection enumerates the valid values (#690).

Background (#690): facade actions that reject a ``mode`` value used to raise a
bare ``ValueError("Invalid mode: <got>")`` — the agent saw the bad value but
never the legal set, so it could not self-correct, and ``recovery_hint`` fell
back to generic boilerplate ("Review the error message and adjust your
request.") that pointed at a message with nothing to review.

This test pins the fix as a mechanical invariant on two surfaces:

1. **Inner tool ``validate_arguments``** — a bad ``mode`` raises a ``ValueError``
   whose message carries the canonical ``"Valid values: ..."`` enumeration and
   actually lists the real valid modes. A regression to a bare raise goes red.
2. **The real ``handle_call_tool`` boundary** (the #690 headline repro,
   ``viz action=similarity mode=<bad>``) — the final envelope's ``error`` lists
   the valid values AND ``recovery_hint`` is the canonical enum hint, not the
   boilerplate. Asserted through the boundary (not ``execute``) per the audit
   lesson that ``execute``-level tests miss facade arg-projection seams.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool
from tree_sitter_analyzer.mcp.tools.auto_index_tool import CodeGraphAutoIndexTool
from tree_sitter_analyzer.mcp.tools.code_similarity_tool import CodeGraphSimilarityTool
from tree_sitter_analyzer.mcp.tools.decision_journal_tool import DecisionJournalTool
from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
)

# (tool class, set of modes that MUST appear in the enumerated error).
# These are the tools whose bare ``Invalid mode: X`` raises were routed through
# ``invalid_enum_error`` in this change. ``fts_search`` is intentionally absent
# from ASTCacheTool's enumerated guidance (deprecated alias, J1).
_ENUM_TOOLS: list[tuple[type, set[str]]] = [
    (CodeGraphSimilarityTool, {"all", "structural", "textual"}),
    (CodeGraphIncrementalSyncTool, {"sync", "changes", "status"}),
    (CodeGraphAutoIndexTool, {"status", "warm", "reset"}),
    (ASTCacheTool, {"index", "lookup", "search", "stats"}),
    (DecisionJournalTool, {"record", "get", "search", "supersede"}),
]


@pytest.mark.parametrize("tool_cls, expected_modes", _ENUM_TOOLS)
def test_invalid_mode_enumerates_valid_values(
    tool_cls: type, expected_modes: set[str], tmp_path
) -> None:
    """A bad ``mode`` raises a ValueError that lists the valid modes (#690)."""
    tool = tool_cls(str(tmp_path))
    with pytest.raises(ValueError) as exc_info:
        tool.validate_arguments({"mode": "definitely-not-a-real-mode"})
    message = str(exc_info.value)
    # Canonical enumeration marker — guards against a regression to a bare raise.
    assert "Valid values:" in message, (
        f"{tool_cls.__name__} enum error lacks the canonical 'Valid values:' "
        f"enumeration: {message!r}"
    )
    # The actual legal modes must be discoverable in the message.
    for mode in expected_modes:
        assert mode in message, (
            f"{tool_cls.__name__} enum error omits valid mode {mode!r}: {message!r}"
        )
    # The bad value is still echoed so the agent knows what was rejected.
    assert "definitely-not-a-real-mode" in message


def _capture_call_tool_handler(server: TreeSitterAnalyzerMCPServer):
    """Capture the ``handle_call_tool`` closure registered by ``create_server``."""
    with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True):
        with patch("tree_sitter_analyzer.mcp.server.Server") as mock_server_class:
            mock_server = Mock()
            captured: dict = {}

            def capture_decorator(name):
                def decorator(func):
                    captured[name] = func
                    return func

                return decorator

            mock_server.call_tool.return_value = capture_decorator("call_tool")
            mock_server_class.return_value = mock_server
            server.create_server()
            return captured["call_tool"]


def test_boundary_enum_error_lists_values_and_canonical_hint(tmp_path) -> None:
    """#690 headline repro through the real boundary: viz action=similarity with
    an invalid mode ships an envelope that enumerates valid modes AND carries the
    canonical enum recovery_hint (not the generic boilerplate)."""
    src = tmp_path / "x.py"
    src.write_text("def f():\n    return 1\n")
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)

    res = asyncio.run(
        handler(
            "viz",
            {"action": "similarity", "mode": "summary"},
        )
    )
    body = json.loads(res[0].text)

    assert body.get("success") is False
    error = body.get("error", "")
    assert "Valid values:" in error, f"boundary error not enumerated: {error!r}"
    for mode in ("all", "structural", "textual"):
        assert mode in error, f"boundary error omits {mode!r}: {error!r}"
    # #690 second half: recovery_hint must NOT be the dead-end boilerplate.
    hint = body.get("recovery_hint", "")
    assert "lists the valid values" in hint, (
        f"recovery_hint is not the canonical enum hint: {hint!r}"
    )
    assert hint != "Review the error message and adjust your request."
