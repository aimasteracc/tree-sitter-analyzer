"""Swift element extractor facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import Class, Function, Import, Variable
from ..plugins.base import ElementExtractor
from ..utils import log_debug
from ._swift_plugin_elements import (
    extract_swift_class,
    extract_swift_function,
    extract_swift_import,
    extract_swift_variable,
)
from ._swift_plugin_nodes import decode_node_text, extract_matching_nodes

if TYPE_CHECKING:
    import tree_sitter

CLASS_NODE_TYPES = {"class_declaration", "protocol_declaration"}
FUNCTION_NODE_TYPES = {
    "function_declaration",
    "init_declaration",
    "protocol_function_declaration",
}
VARIABLE_NODE_TYPES = {"property_declaration", "protocol_property_declaration"}


class SwiftElementExtractor(ElementExtractor):
    """Swift-specific element extractor."""

    def __init__(self) -> None:
        """Initialize the Swift element extractor."""
        super().__init__()
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Swift functions, methods, initializers, and protocol methods."""
        self._prepare_source(source_code)
        functions = extract_matching_nodes(
            tree.root_node,
            FUNCTION_NODE_TYPES,
            lambda node: extract_swift_function(self, node),
        )
        log_debug(f"Extracted {len(functions)} Swift functions")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Swift classes, structs, enums, protocols, and extensions."""
        self._prepare_source(source_code)
        classes = extract_matching_nodes(
            tree.root_node,
            CLASS_NODE_TYPES,
            lambda node: extract_swift_class(self, node),
        )
        log_debug(f"Extracted {len(classes)} Swift type declarations")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Swift let/var property declarations."""
        self._prepare_source(source_code)
        variables = extract_matching_nodes(
            tree.root_node,
            VARIABLE_NODE_TYPES,
            lambda node: extract_swift_variable(self, node),
        )
        log_debug(f"Extracted {len(variables)} Swift variables")
        return variables

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Swift import declarations."""
        self._prepare_source(source_code)
        imports = extract_matching_nodes(
            tree.root_node,
            {"import_declaration"},
            lambda node: extract_swift_import(self, node),
        )
        log_debug(f"Extracted {len(imports)} Swift imports")
        return imports

    def _prepare_source(self, source_code: str) -> None:
        self.source_code = source_code
        self.content_lines = source_code.splitlines()
        self._node_text_cache.clear()

    def get_node_text(self, node: tree_sitter.Node) -> str:
        """Return cached text for a Swift AST node."""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key not in self._node_text_cache:
            self._node_text_cache[cache_key] = decode_node_text(node)
        return self._node_text_cache[cache_key]
