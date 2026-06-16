"""RFC-0012 Phase 1: opt-in ``compact_only`` TOON compaction.

Covers the formatter helpers (``reduce_to_control_surface`` +
``apply_toon_format_to_response(compact_only=...)``) and — crucially — the MCP
boundary behavior: the compact reduction MUST survive
``ensure_canonical_success_envelope`` (which re-adds ``agent_summary`` /
``summary_line``), so it is asserted through the real ``handle_call_tool``
boundary, not just ``tool.execute()``.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
from tree_sitter_analyzer.mcp.utils.format_helper import (
    TOON_CONTROL_SURFACE,
    apply_toon_format_to_response,
    reduce_to_control_surface,
)

# ---------------------------------------------------------------------------
# Formatter unit tests
# ---------------------------------------------------------------------------

_METADATA_HEAVY = {
    "success": True,
    "verdict": "SAFE",
    "summary_line": "file is healthy",
    "agent_summary": {"verdict": "SAFE", "summary_line": "file is healthy"},
    "queue_ledger": {"scoped_changed_count": 1},
    "file_path": "src/x.py",
    "grade": "A",
    "metrics": {"loc": 100, "complexity": 3},
}


class TestReduceToControlSurface:
    def test_keeps_only_control_surface_on_toon(self) -> None:
        toon = {"format": "toon", "toon_content": "blob", **_METADATA_HEAVY}
        out = reduce_to_control_surface(toon)
        assert set(out) <= TOON_CONTROL_SURFACE
        assert out["toon_content"] == "blob"
        assert out["success"] is True
        assert out["verdict"] == "SAFE"
        assert out["summary_line"] == "file is healthy"
        assert "agent_summary" not in out
        assert "queue_ledger" not in out
        assert "metrics" not in out

    def test_noop_on_non_toon(self) -> None:
        d = {"success": True, "agent_summary": {"a": 1}}
        assert reduce_to_control_surface(d) == d

    def test_idempotent(self) -> None:
        toon = {"format": "toon", "toon_content": "blob", **_METADATA_HEAVY}
        once = reduce_to_control_surface(toon)
        assert reduce_to_control_surface(once) == once


class TestApplyToonCompactOnly:
    def test_default_is_unchanged_byte_parity(self) -> None:
        legacy = apply_toon_format_to_response(dict(_METADATA_HEAVY), "toon")
        # default compact_only=False must equal the explicit-False call
        assert (
            apply_toon_format_to_response(
                dict(_METADATA_HEAVY), "toon", compact_only=False
            )
            == legacy
        )
        # RFC-0012 Phase 2: agent_summary is in TOON_DICT_PASSTHROUGH — kept.
        assert "agent_summary" in legacy
        # queue_ledger is a non-empty dict NOT in TOON_DICT_PASSTHROUGH — now
        # stripped by the value-kind rule (it was pinning the old bug).
        assert "queue_ledger" not in legacy

    def test_compact_only_drops_duplicated_metadata(self) -> None:
        legacy = apply_toon_format_to_response(dict(_METADATA_HEAVY), "toon")
        compact = apply_toon_format_to_response(
            dict(_METADATA_HEAVY), "toon", compact_only=True
        )
        assert set(compact) <= TOON_CONTROL_SURFACE
        assert compact["toon_content"] == legacy["toon_content"]
        # the headline win: compact is smaller than the duplicating legacy shape
        assert len(json.dumps(compact)) < len(json.dumps(legacy))

    def test_compact_only_is_noop_for_json(self) -> None:
        out = apply_toon_format_to_response(
            dict(_METADATA_HEAVY), "json", compact_only=True
        )
        # json path returns the dict untouched (no toon_content, no reduction)
        assert "agent_summary" in out
        assert "toon_content" not in out


# ---------------------------------------------------------------------------
# MCP boundary e2e — the Codex-P2 regression guard
# ---------------------------------------------------------------------------


def _capture_call_tool_handler(server: TreeSitterAnalyzerMCPServer):
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


# Walks the full MCP tool surface through handle_call_tool + canonical-envelope
# validation; ~15-19s on the Windows full-matrix under xdist+build load. Real
# work, not a perf regression — exempt from the per-test budget.
@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_boundary_compact_only_survives_canonical_envelope(tmp_path) -> None:
    """Through the FULL handle_call_tool boundary: a file_health call with
    compact_only=true + toon must ship ONLY the control surface — the canonical
    success post-hook must NOT re-inflate agent_summary back onto the wire."""
    src = tmp_path / "x.py"
    src.write_text("def f():\n    return 1\n")
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)

    compact_res = await handler(
        "check_file_health",
        {"file_path": str(src), "output_format": "toon", "compact_only": True},
    )
    compact = json.loads(compact_res[0].text)
    assert compact.get("format") == "toon"
    assert "toon_content" in compact
    assert set(compact) <= TOON_CONTROL_SURFACE, (
        f"compact response leaked non-control keys: {set(compact) - TOON_CONTROL_SURFACE}"
    )
    # the re-inflation guard: agent_summary must be gone post-boundary
    assert "agent_summary" not in compact

    # and the legacy (no compact_only) call DOES carry the re-added envelope
    legacy_res = await handler(
        "check_file_health",
        {"file_path": str(src), "output_format": "toon"},
    )
    legacy = json.loads(legacy_res[0].text)
    assert "agent_summary" in legacy
    assert len(legacy_res[0].text) > len(compact_res[0].text)


# Same full-surface boundary walk as above; ~16s on Windows full-matrix load.
@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_boundary_default_unaffected(tmp_path) -> None:
    """Without compact_only the boundary leaves the response shape as-is."""
    src = tmp_path / "y.py"
    src.write_text("def g():\n    return 2\n")
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)
    res = await handler(
        "check_file_health", {"file_path": str(src), "output_format": "toon"}
    )
    body = json.loads(res[0].text)
    assert body.get("format") == "toon"
    # legacy keeps the duplicated metadata surface
    assert "agent_summary" in body


@pytest.mark.asyncio
async def test_boundary_compact_only_second_tool(tmp_path) -> None:
    """The boundary reduction is generic — exercise a second decision tool
    (safe_to_edit) to prove it is not file_health-specific."""
    src = tmp_path / "z.py"
    src.write_text("def h():\n    return 3\n")
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)
    res = await handler(
        "safe_to_edit",
        {"file_path": str(src), "output_format": "toon", "compact_only": True},
    )
    body = json.loads(res[0].text)
    assert body.get("format") == "toon"
    assert set(body) <= TOON_CONTROL_SURFACE
    assert "agent_summary" not in body


@pytest.mark.asyncio
async def test_boundary_compact_only_error_envelope_keeps_hint(tmp_path) -> None:
    """An ERROR response under compact_only must still carry the recovery
    surface (error / error_type / hint) — the sharpest review-nit edge."""
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)
    # change_impact PR mode with a malformed URL returns a success=False,
    # format=toon envelope carrying a ``hint``.
    res = await handler(
        "analyze_change_impact",
        {"pr_url": "not-a-real-url", "output_format": "toon", "compact_only": True},
    )
    body = json.loads(res[0].text)
    assert body.get("success") is False
    assert set(body) <= TOON_CONTROL_SURFACE
    # the recovery affordances survive compaction
    assert "error" in body
    assert "hint" in body


@pytest.mark.asyncio
async def test_boundary_compact_only_legacy_keeps_deprecation(tmp_path) -> None:
    """Codex P2 #393: a LEGACY tool name (e.g. check_file_health) routed through
    dispatch_legacy injects ``deprecation`` AFTER the facade built toon_content.
    Compaction must NOT drop that in-band migration warning — agents that cannot
    read server stderr rely on it.

    (check_file_health / safe_to_edit / analyze_change_impact are legacy names in
    facade_map.LEGACY_TOOL_MAP.)
    """
    src = tmp_path / "leg.py"
    src.write_text("def m():\n    return 5\n")
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)
    res = await handler(
        "check_file_health",
        {"file_path": str(src), "output_format": "toon", "compact_only": True},
    )
    body = json.loads(res[0].text)
    assert set(body) <= TOON_CONTROL_SURFACE
    assert "deprecation" in body, (
        "legacy migration warning was dropped by compact reduction"
    )


@pytest.mark.asyncio
async def test_boundary_reduction_is_idempotent(tmp_path) -> None:
    """Reducing an already-compact response at the boundary is a no-op — guards
    against the execute-level reduction + the boundary reduction disagreeing."""
    src = tmp_path / "i.py"
    src.write_text("def k():\n    return 4\n")
    server = TreeSitterAnalyzerMCPServer(str(tmp_path))
    handler = _capture_call_tool_handler(server)
    # execute already compacts (execute-level forwarding); the boundary then
    # re-applies — the two must agree.
    res = await handler(
        "check_file_health",
        {"file_path": str(src), "output_format": "toon", "compact_only": True},
    )
    body = json.loads(res[0].text)
    assert reduce_to_control_surface(dict(body)) == body


# ---------------------------------------------------------------------------
# Execute-level early-return compaction (coverage of the syntax-error branch,
# where execute() forwards compact_only before the main scoring path).
# ---------------------------------------------------------------------------

_BROKEN_PY = "def f(:\n    return\n"  # tree-sitter parse error → syntax_response


def test_execute_compact_only_on_syntax_error_path_file_health(tmp_path) -> None:
    """file_health's syntax-error early return must honor compact_only too."""
    src = tmp_path / "broken.py"
    src.write_text(_BROKEN_PY)
    res = asyncio.run(
        FileHealthTool(str(tmp_path)).execute(
            {"file_path": str(src), "output_format": "toon", "compact_only": True}
        )
    )
    assert res.get("format") == "toon"
    assert set(res) <= TOON_CONTROL_SURFACE
    assert res.get("verdict") == "ERROR"  # syntax_error envelope


def test_execute_compact_only_on_syntax_error_path_safe_to_edit(tmp_path) -> None:
    """safe_to_edit's syntax-error early return must honor compact_only too."""
    src = tmp_path / "broken2.py"
    src.write_text(_BROKEN_PY)
    res = asyncio.run(
        SafeToEditTool(str(tmp_path)).execute(
            {"file_path": str(src), "output_format": "toon", "compact_only": True}
        )
    )
    assert res.get("format") == "toon"
    assert set(res) <= TOON_CONTROL_SURFACE
    assert res.get("verdict") == "ERROR"
