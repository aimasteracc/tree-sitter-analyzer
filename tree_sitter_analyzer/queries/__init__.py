#!/usr/bin/env python3
"""
Language-specific Tree-sitter Queries Package.

Provides Tree-sitter queries for various programming languages.

Key Features:
    - Language-specific query definitions
    - Common code element patterns
    - Multi-language support
    - Consistent query interface

Version: 1.10.5
Date: 2026-01-28
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..query_loader import (
        get_query,
        is_language_supported,
        list_queries,
        query_loader,
    )
else:
    try:
        from ..query_loader import (
            get_query,
            is_language_supported,
            list_queries,
            query_loader,
        )
    except ImportError as e:
        import logging

        logging.warning(f"Import fallback triggered in queries.__init__: {e}")

__all__ = ["get_query", "list_queries", "is_language_supported", "query_loader"]
