"""typescript_plugin mixin — classes."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

import re

from ...models import (
    Class,
)
from ...utils import log_debug
from ._base import _TypeScriptElementBase


class ClassesMixin(_TypeScriptElementBase):

    def _extract_class_optimized(self, node: tree_sitter.Node) -> Class | None:
        """Extract class information with detailed metadata"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract class name
            class_name = None
            superclass = None
            interfaces = []
            # generics = []  # Commented out as not used yet
            is_abstract = node.type == "abstract_class_declaration"

            for child in node.children:
                if child.type == "type_identifier":
                    class_name = child.text.decode("utf8") if child.text else None
                elif child.type == "class_heritage":
                    # Extract extends and implements clauses
                    heritage_text = self._get_node_text_optimized(child)
                    extends_match = re.search(r"extends\s+(\w+)", heritage_text)
                    if extends_match:
                        superclass = extends_match.group(1)

                    implements_matches = re.findall(
                        r"implements\s+([\w,\s]+)", heritage_text
                    )
                    if implements_matches:
                        interfaces = [
                            iface.strip() for iface in implements_matches[0].split(",")
                        ]
                elif child.type == "type_parameters":
                    self._extract_generics(child)

            if not class_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Check if it's a framework component
            is_component = self._is_framework_component(node, class_name)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="abstract_class" if is_abstract else "class",
                superclass=superclass,
                interfaces=interfaces,
                docstring=tsdoc,
                # TypeScript-specific properties
                is_react_component=is_component,
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(class_name),
                is_abstract=is_abstract,
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract class info: {e}")
            return None

    def _extract_interface_optimized(self, node: tree_sitter.Node) -> Class | None:
        """Extract interface information"""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract interface name
            interface_name = None
            extends_interfaces = []
            # generics = []  # Commented out as not used yet

            for child in node.children:
                if child.type == "type_identifier":
                    interface_name = child.text.decode("utf8") if child.text else None
                elif child.type == "extends_clause":
                    # Extract extends clause for interfaces
                    extends_text = self._get_node_text_optimized(child)
                    extends_matches = re.findall(r"extends\s+([\w,\s]+)", extends_text)
                    if extends_matches:
                        extends_interfaces = [
                            iface.strip() for iface in extends_matches[0].split(",")
                        ]
                elif child.type == "type_parameters":
                    self._extract_generics(child)

            if not interface_name:
                return None

            # Extract TSDoc
            tsdoc = self._extract_tsdoc_for_line(start_line)

            # Extract raw text
            raw_text = self._get_node_text_optimized(node)

            return Class(
                name=interface_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="typescript",
                class_type="interface",
                interfaces=extends_interfaces,
                docstring=tsdoc,
                # TypeScript-specific properties
                framework_type=self.framework_type,
                is_exported=self._is_exported_class(interface_name),
                # TypeScript-specific properties handled above
            )
        except Exception as e:
            log_debug(f"Failed to extract interface info: {e}")
            return None
