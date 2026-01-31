#!/usr/bin/env python3
"""
MCP Tool Formatters.

Result formatting for MCP tools.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer.mcp.tools.formatters.search_formatter import (
        SearchResultFormatter,
    )
else:
    try:
        from tree_sitter_analyzer.mcp.tools.formatters.search_formatter import (
            SearchResultFormatter,
        )
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in mcp.tools.formatters: {e}")

__all__ = [
    "SearchResultFormatter",
]
