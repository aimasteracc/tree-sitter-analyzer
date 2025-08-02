#!/usr/bin/env python3
"""
Language-specific Tree-sitter queries package.

This package provides Tree-sitter queries for various programming languages.
Each language has its own module with predefined queries for common code elements.

Supported languages:
- Java
- JavaScript
- Python
- TypeScript

Usage:
    from tree_sitter_analyzer.queries import get_query, list_queries

    # Get a specific query
    query = get_query('java', 'classes')

    # List all queries for a language
    queries = list_queries('python')
"""

from ..query_loader import get_query, is_language_supported, list_queries, query_loader

__all__ = ["get_query", "list_queries", "is_language_supported", "query_loader"]
