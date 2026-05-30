"""Shared query accessor factories for language query modules.

Each language query module defines ALL_QUERIES and calls make_query_accessors()
to generate the standard get_query / get_all_queries / list_queries interface
expected by query_loader.py.
"""

from __future__ import annotations

from typing import Any


def make_query_accessors(
    all_queries: dict[str, Any],
) -> tuple[Any, Any, Any]:
    """Return (get_query, get_all_queries, list_queries) bound to *all_queries*."""

    def get_query(name: str) -> str:
        """Get a specific query by name."""
        if name in all_queries:
            return str(all_queries[name]["query"])
        raise ValueError(
            f"Query '{name}' not found. Available queries: {list(all_queries.keys())}"
        )

    def get_all_queries() -> dict[str, Any]:
        """Get all available queries."""
        return all_queries

    def list_queries() -> list[str]:
        """List all available query names."""
        return list(all_queries.keys())

    return get_query, get_all_queries, list_queries
