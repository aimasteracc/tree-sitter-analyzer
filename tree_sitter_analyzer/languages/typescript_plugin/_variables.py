"""typescript_plugin mixin — variables."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Variable,
)
from ...utils import log_debug
from ._base import _TypeScriptElementBase


class VariablesMixin(_TypeScriptElementBase):

    def _extract_variable_optimized(self, node: tree_sitter.Node) -> list[Variable]:
        """Extract var declaration variables"""
        return self._extract_variables_from_declaration(node, "var")

    def _extract_variables_from_declaration(
        self, node: tree_sitter.Node, kind: str
    ) -> list[Variable]:
        """Extract variables from declaration node"""
        variables: list[Variable] = []

        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Find variable declarators
            for child in node.children:
                if child.type == "variable_declarator":
                    var_info = self._parse_variable_declarator(
                        child, kind, start_line, end_line
                    )
                    if var_info:
                        variables.append(var_info)

        except Exception as e:
            log_debug(f"Failed to extract variables from declaration: {e}")

        return variables
