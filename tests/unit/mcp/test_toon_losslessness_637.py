"""Issue #637 — TOON losslessness invariant at the handle_call_tool boundary.

Rule-11 deliverable: the claim "TOON carries the same information as JSON"
must be an executable invariant, not prose.  This test drives the REAL
``handle_call_tool`` closure (NOT ``tool.execute`` — the boundary-order
trap from RFC-0012) with ``nav action=callers`` and asserts STRUCTURALLY
that every key present in ANY row of any list-of-dicts in the JSON payload
appears in the TOON response.  No field-name denylist/allowlist — past
TOON fixes that patched symptom lists were 假修复 (fake fixes).

The scenario mirrors the real offender: the first caller row is a "ghost"
without ``body`` while later rows carry one.  Pre-fix, the table header
was built from the ghost row's keys and every ``body`` vanished.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


def _capture_call_tool_handler(server: TreeSitterAnalyzerMCPServer):
    """Capture the ``handle_call_tool`` closure registered by ``create_server``.

    Mirrors ``test_nav_impact_boundary.py`` / ``test_toon_compact_only.py``.
    """
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


_CALLERS = [
    # Ghost first row — NO body (the real-offender shape from #637).
    {"name": "ghost_caller", "file": "src/ghost.py", "line": 1, "language": "python"},
    {"name": "caller_two", "file": "src/two.py", "line": 20, "language": "python"},
    {"name": "caller_three", "file": "src/three.py", "line": 30, "language": "python"},
]

_BODIES = {
    # Multiline body exercises quoted-escape; the marker token itself has no
    # TOON special characters so it must survive escaping verbatim.
    "caller_two": "def caller_two():\n    return target()  # BODY2_MARKER_xyzzy",
    "caller_three": "BODY3_MARKER_xyzzy",
}


def _fake_inline_neighbor_bodies(
    project_root: str, cache: Any, neighbors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deterministic stand-in for symbol_body_inline.inline_neighbor_bodies:
    attach bodies to rows 2-3, leave the ghost row coordinate-only."""
    out = []
    for record in neighbors:
        new_record = dict(record)
        body = _BODIES.get(record.get("name", ""))
        if body is not None:
            new_record["body"] = body
        out.append(new_record)
    return out


def _iter_row_dicts(node: Any):
    """Yield every dict that appears inside any list, at any depth."""
    if isinstance(node, dict):
        for value in node.values():
            yield from _iter_row_dicts(value)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                yield item
            yield from _iter_row_dicts(item)


async def _call(handler, output_format: str) -> dict[str, Any]:
    mock_graph = MagicMock()
    mock_graph.callers_of.return_value = [dict(c) for c in _CALLERS]
    with (
        patch(
            "tree_sitter_analyzer.mcp.tools.callers_tool"
            ".CodeGraphCallersTool._try_get_cache",
            return_value=None,
        ),
        patch(
            "tree_sitter_analyzer.mcp.tools.callers_tool"
            ".CodeGraphCallersTool._get_call_graph",
            return_value=mock_graph,
        ),
        patch(
            "tree_sitter_analyzer.mcp.tools.symbol_body_inline.inline_neighbor_bodies",
            side_effect=_fake_inline_neighbor_bodies,
        ),
    ):
        raw = await handler(
            "nav",
            {
                "action": "callers",
                "function_name": "target_fn",
                "output_format": output_format,
            },
        )
    return json.loads(raw[0].text)


class TestToonLosslessnessInvariant:
    """Structural ⊇ invariant: TOON output covers the JSON payload."""

    @pytest.mark.asyncio
    async def test_heterogeneous_rows_lossless_through_boundary(self, tmp_path) -> None:
        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        handler = _capture_call_tool_handler(server)

        json_body = await _call(handler, "json")
        toon_body = await _call(handler, "toon")

        # --- Scenario self-check: the JSON payload IS heterogeneous. -------
        assert json_body["success"] is True
        rows = json_body["callers"]
        assert [("body" in r) for r in rows] == [False, True, True]

        # --- The invariant (structural, no field-name list): every key of
        # every row dict anywhere in the JSON payload appears in the TOON
        # response text. ----------------------------------------------------
        assert toon_body["format"] == "toon"
        toon_text = toon_body["toon_content"]
        all_row_keys: set[str] = set()
        for row in _iter_row_dicts(json_body):
            all_row_keys.update(row.keys())
        missing = sorted(k for k in all_row_keys if k not in toon_text)
        assert missing == []

        # --- Value-level spot pins: the bodies (the data that vanished in
        # #637) are recoverable from toon_content, exactly once each. -------
        assert toon_text.count("BODY2_MARKER_xyzzy") == 1
        assert toon_text.count("BODY3_MARKER_xyzzy") == 1
        assert toon_text.count("ghost_caller") == 1

        # --- Header pin: union schema in first-seen order (ghost row keys +
        # enrichment keys + body appended by the inliner). -------------------
        expected_header = (
            "[3]{name,file,line,language,callee_resolution,callee_resolved_file,body}:"
        )
        assert toon_text.count(expected_header) == 1
