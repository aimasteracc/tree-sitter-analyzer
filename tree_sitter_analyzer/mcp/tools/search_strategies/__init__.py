"""Search strategies for SearchContentTool.

This package contains the strategy pattern implementation for different
search modes in SearchContentTool.
"""

from tree_sitter_analyzer.mcp.tools.search_strategies.base import (
    SearchContext,
    SearchStrategy,
)

__all__ = [
    "SearchContext",
    "SearchStrategy",
]
