"""
MCP Server entry point for tree-sitter-analyzer v2.

This module serves as the entry point when running:
    python -m tree_sitter_analyzer_v2.mcp.server
"""

from tree_sitter_analyzer_v2.mcp.server import main_sync

if __name__ == "__main__":
    main_sync()
