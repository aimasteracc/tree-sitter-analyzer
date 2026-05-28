"""Shared helper functions for codegraph_query_tool test modules."""

from __future__ import annotations

from unittest.mock import patch

from tree_sitter_analyzer.codegraph_query_backend import (
    CodeGraphQueryBackend as SharedCodeGraphQueryBackend,
)
from tree_sitter_analyzer.symbol_resolver import DefinitionLocation


def _make_def(
    file: str = "main.py",
    name: str = "run",
    kind: str = "function",
    line: int = 1,
    end_line: int = 2,
    language: str = "python",
) -> DefinitionLocation:
    return DefinitionLocation(
        file=file,
        name=name,
        kind=kind,
        line=line,
        end_line=end_line,
        language=language,
    )


def _patch_resolver_with(defs_per_token: dict[str, list[DefinitionLocation]]):
    class FakeBackend:
        def __init__(self, cache):
            self._real_backend = SharedCodeGraphQueryBackend(cache)

        def resolve_definitions(self, token: str) -> list[dict[str, object]]:
            return [
                definition.to_dict() for definition in defs_per_token.get(token, [])
            ]

        def semantic_symbols(self, token: str, *, limit: int):
            return [
                definition.to_dict() for definition in defs_per_token.get(token, [])
            ][:limit]

        def relation_entries(self, **kwargs):
            return self._real_backend.relation_entries(**kwargs)

    return patch(
        "tree_sitter_analyzer.mcp.tools.codegraph_query_tool.CodeGraphQueryBackend",
        FakeBackend,
    )
