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
    assert "codegraph_context" in instructions
    assert "codegraph_symbol_search" in instructions
    assert "codegraph_navigate" in instructions
