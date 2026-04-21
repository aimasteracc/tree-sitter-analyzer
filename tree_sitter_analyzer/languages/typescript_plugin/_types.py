"""typescript_plugin mixin — types."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Class,
)
from ...utils import log_debug
from ._base import _TypeScriptElementBase


class TypesMixin(_TypeScriptElementBase):

    def _extract_type_alias_optimized(self, node: tree_sitter.Node) -> Class | None:
        """Extract type alias information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract type alias name
            type_name = None
            # generics = []  # Commented out as not used yet

            for child in node.children:
                if child.type == "type_identifier":
                    type_name = child.text.decode("utf8") if child.text else None
                elif child.type == "type_parameters":
                    self._extract_generics(child)

            if not type_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=type_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="type",
                docstring=tsdoc,
                # TypeScript-specific properties
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(type_name),
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract type alias info: {e}")
            return None

    def _extract_enum_optimized(self, node: tree_sitter.Node) -> Class | None:
        """Extract enum information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract enum name
            enum_name = None

            for child in node.children:
                if child.type == "identifier":
                    enum_name = child.text.decode("utf8") if child.text else None

            if not enum_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=enum_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="enum",
                docstring=tsdoc,
                # TypeScript-specific properties
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(enum_name),
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract enum info: {e}")
            return None
