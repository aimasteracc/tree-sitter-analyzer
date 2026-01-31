#!/usr/bin/env python3
"""
MCP Tool Validators.

Validation logic for MCP tool arguments.

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer.mcp.tools.validators.search_validator import (
        SearchArgumentValidator,
    )
else:
    try:
        from tree_sitter_analyzer.mcp.tools.validators.search_validator import (
            SearchArgumentValidator,
        )
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in mcp.tools.validators: {e}")

__all__ = [
    "SearchArgumentValidator",
]
