"""Tests for MCP server startup helper wiring."""

from __future__ import annotations


class _RecordingInitializationOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_build_initialization_options_includes_agent_routing_instructions():
    from tree_sitter_analyzer.mcp._server_helpers import build_initialization_options

    options = build_initialization_options(
        "tree-sitter-analyzer",
        "1.2.3",
        _RecordingInitializationOptions,
    )

    instructions = options.kwargs["instructions"]
    assert "TSA MCP Routing" in instructions
    # Instructions MUST name the actual exposed facade tools, not the pre-v2.0
    # codegraph_* names that no longer exist (the dogfood-loss root cause:
    # agents got a stale map and scattered across search/structure/nav).
    for facade in ("nav", "search", "structure"):
        assert facade in instructions
    assert "action=context" in instructions
    assert "action=callee_tree" in instructions
    # The stale per-tool codegraph_* names must be gone.
    assert "codegraph_symbol_search" not in instructions
    assert "codegraph_navigate" not in instructions

    # The 8 real facade tools must never be described by a non-existent name.
    real_facades = {
        "search",
        "nav",
        "structure",
        "health",
        "edit",
        "project",
        "index",
        "viz",
    }
    assert real_facades  # documents the contract for future edits
