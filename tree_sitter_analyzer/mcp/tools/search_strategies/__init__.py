#!/usr/bin/env python3
"""
Search Strategies.

Strategy pattern for search modes.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer.mcp.tools.search_strategies.base import (
        SearchContext,
        SearchStrategy,
    )
else:
    try:
        from tree_sitter_analyzer.mcp.tools.search_strategies.base import (
            SearchContext,
            SearchStrategy,
        )
    except ImportError as e:
        import logging

        logging.warning(
            f"Import fallback triggered in mcp.tools.search_strategies: {e}"
        )

__all__ = [
    "SearchContext",
    "SearchStrategy",
]
