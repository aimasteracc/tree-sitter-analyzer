"""Utility methods for the JavaScript extractor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...utils import log_debug
from .._complexity_decisions import count_decision_complexity
from ._jsdoc import clean_jsdoc, extract_jsdoc_for_line
from ._variable import infer_type_from_value

if TYPE_CHECKING:
    import tree_sitter


class JavaScriptUtilityMixin:
    """Small compatibility methods shared by JavaScript extraction helpers."""

    # Search for patterns or elements: _find_parent_class_name
    def _find_parent_class_name(self, node: tree_sitter.Node) -> str | None:
        """Find parent class name for methods/properties."""
        current = node.parent
        while current:
            if current.type in ["class_declaration", "class_expression"]:
                for child in current.children:
                    if child.type == "identifier":
                        return self._get_node_text_optimized(child)
            current = current.parent
        return None

    def _is_react_component(self, node: tree_sitter.Node, class_name: str) -> bool:
        """Check if class is a React component."""
        if self.framework_type != "react":
            return False

        node_text = self._get_node_text_optimized(node)
        return "extends" in node_text and (
            "Component" in node_text or "PureComponent" in node_text
        )

    def _is_exported_class(self, class_name: str) -> bool:
        """Check if class is exported."""
        return any(class_name in export.get("names", []) for export in self.exports)

    def _infer_type_from_value(self, value: str | None) -> str:
        """Infer JavaScript type from value."""
        return infer_type_from_value(value)

    def _get_variable_kind(self, var_data: dict | str) -> str:
        """Get variable declaration kind from variable data or raw text."""
        if isinstance(var_data, dict):
            raw_text = var_data.get("raw_text", "")
        else:
            raw_text = var_data

        if not raw_text:
            return "unknown"

        raw_text = str(raw_text).strip()
        if raw_text.startswith("const"):
            return "const"
        if raw_text.startswith("let"):
            return "let"
        if raw_text.startswith("var"):
            return "var"
        return "unknown"

    # Extract elements from AST: _extract_jsdoc_for_line
    def _extract_jsdoc_for_line(self, target_line: int) -> str | None:
        """Extract JSDoc comment immediately before the specified line."""
        return extract_jsdoc_for_line(
            self.content_lines,
            target_line,
            self._jsdoc_cache,
            self._clean_jsdoc,
        )

    def _clean_jsdoc(self, jsdoc_text: str) -> str:
        """Clean JSDoc text by removing comment markers."""
        return clean_jsdoc(jsdoc_text)

    def _calculate_complexity_optimized(self, node: tree_sitter.Node) -> int:
        """Calculate cyclomatic complexity efficiently."""
        node_id = id(node)
        if node_id in self._complexity_cache:
            return self._complexity_cache[node_id]

        try:
            complexity = count_decision_complexity(node)
        except Exception as e:
            log_debug(f"Failed to calculate complexity: {e}")
            complexity = 1

        self._complexity_cache[node_id] = complexity
        return complexity
