"""Shared method stubs for mutability mixins — satisfies mypy strict attr-defined checks."""
from __future__ import annotations

import tree_sitter


class _MutabilityBase:
    """Declares methods provided by other mixins / the composed analyzer."""

    def _extract_identifiers(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        raise NotImplementedError

    def _collect_refs(self, node: tree_sitter.Node, references: set[str]) -> None:
        ...
