#!/usr/bin/env python3
"""
YAML Language Plugin

YAML-specific parsing and element extraction functionality using tree-sitter-yaml.
Provides comprehensive support for YAML elements including mappings, sequences,
scalars, anchors, aliases, and comments.
"""

import logging
import threading
from typing import TYPE_CHECKING, Any

from ..models import AnalysisResult, Class, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_warning
from .yaml_helpers import YAMLElement
from .yaml_helpers import (
    analyze_yaml_file as _analyze_yaml_file_standalone,
)
from .yaml_helpers import (
    append_document_element as _append_document_element_standalone,
)
from .yaml_helpers import (
    append_mapping_element as _append_mapping_element_standalone,
)
from .yaml_helpers import (
    calculate_nesting_level as _calc_nesting_standalone,
)
from .yaml_helpers import (
    count_document_children as _count_document_children_standalone,
)
from .yaml_helpers import (
    count_sequence_children as _count_sequence_children_standalone,
)
from .yaml_helpers import (
    extract_sequence_key as _extract_seq_key_standalone,
)
from .yaml_helpers import (
    extract_value_info as _extract_value_standalone,
)
from .yaml_helpers import (
    get_document_index as _get_doc_idx_standalone,
)
from .yaml_helpers import (
    iter_document_nodes as _iter_document_nodes_standalone,
)
from .yaml_helpers import (
    iter_mapping_nodes as _iter_mapping_nodes_standalone,
)
from .yaml_helpers import (
    traverse_nodes as _traverse_standalone,
)

if TYPE_CHECKING:
    import tree_sitter

    from ..core.analysis_engine import AnalysisRequest

logger = logging.getLogger(__name__)

# Graceful degradation for tree-sitter-yaml
try:
    import tree_sitter
    import tree_sitter_yaml as ts_yaml

    YAML_AVAILABLE = True
    # Pre-initialize YAML language at import time to avoid per-test/per-call cold-start costs.
    # This keeps Hypothesis deadline-based property tests stable.
    YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
    YAML_PARSER = tree_sitter.Parser()
    YAML_PARSER.language = YAML_LANGUAGE
    _YAML_PARSER_LOCK = threading.Lock()
except ImportError:
    YAML_AVAILABLE = False
    log_warning("tree-sitter-yaml not installed, YAML support disabled")


class YAMLElementExtractor(ElementExtractor):
    """YAML-specific element extractor using tree-sitter-yaml."""

    def __init__(self) -> None:
        """Initialize the YAML element extractor."""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._current_document_index: int = 0

    # Extract elements from AST: extract_functions
    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """YAML doesn't have functions, return empty list."""
        return []

    # Extract elements from AST: extract_classes
    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """YAML doesn't have classes, return empty list."""
        return []

    # Extract elements from AST: extract_variables
    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """YAML doesn't have variables, return empty list."""
        return []

    # Extract elements from AST: extract_imports
    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """YAML doesn't have imports, return empty list."""
        return []

    # Extract elements from AST: extract_yaml_elements
    def extract_yaml_elements(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[YAMLElement]:
        """Extract all YAML elements from the parsed tree.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Original source code

        Returns:
            List of YAMLElement objects
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._current_document_index = 0

        elements: list[YAMLElement] = []

        if tree is None or tree.root_node is None:
            return elements

        try:
            # Extract documents first to set document indices
            self._extract_documents(tree.root_node, elements)
            # Extract mappings
            self._extract_mappings(tree.root_node, elements)
            # Extract sequences
            self._extract_sequences(tree.root_node, elements)
            # Extract anchors and aliases
            self._extract_anchors(tree.root_node, elements)
            self._extract_aliases(tree.root_node, elements)
            # Extract comments
            self._extract_comments(tree.root_node, elements)
        except Exception as e:
            log_error(f"Error during YAML element extraction: {e}")

        log_debug(f"Extracted {len(elements)} YAML elements")
        return elements

    # Extract elements from AST: extract_elements
    def extract_elements(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[YAMLElement]:
        """Alias for extract_yaml_elements for compatibility with tests.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Original source code

        Returns:
            List of YAMLElement objects
        """
        return self.extract_yaml_elements(tree, source_code)

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """Get text content from a tree-sitter node."""
        try:
            if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
                source_bytes = self.source_code.encode("utf-8")
                node_bytes = source_bytes[node.start_byte : node.end_byte]
                return node_bytes.decode("utf-8", errors="replace")
            return ""
        except Exception as e:
            log_debug(f"Failed to extract node text: {e}")
            return ""

    def _calculate_nesting_level(self, node: "tree_sitter.Node") -> int:
        """Calculate AST-based logical nesting level."""
        return _calc_nesting_standalone(node)

    def _get_document_index(self, node: "tree_sitter.Node") -> int:
        """Get document index for a node."""
        return _get_doc_idx_standalone(node)

    def _traverse_nodes(self, node: "tree_sitter.Node") -> "list[tree_sitter.Node]":
        """Traverse all nodes in the tree."""
        return _traverse_standalone(node)

    def _count_document_children(self, document_node: "tree_sitter.Node") -> int:
        """Count meaningful children in a document (top-level mappings).

        This counts the number of top-level key-value pairs in the document,
        which is more meaningful than counting AST nodes.
        """
        return _count_document_children_standalone(document_node)

    # Extract elements from AST: _extract_documents
    def _extract_documents(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML documents."""
        document_nodes = _iter_document_nodes_standalone(
            self._traverse_nodes(root_node)
        )
        for node in document_nodes:
            _append_document_element_standalone(
                elements,
                node,
                self._get_node_text,
                self._get_document_index,
            )

    # Extract elements from AST: _extract_mappings
    def _extract_mappings(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML mappings (key-value pairs)."""
        mapping_nodes = _iter_mapping_nodes_standalone(self._traverse_nodes(root_node))
        for node in mapping_nodes:
            _append_mapping_element_standalone(
                elements,
                node,
                self._get_node_text,
                self._get_document_index,
                self._calculate_nesting_level,
            )

    # Extract elements from AST: _extract_value_info
    def _extract_value_info(
        self, node: "tree_sitter.Node | None"
    ) -> tuple[str | None, str | None, int | None]:
        """Extract value information from a node."""
        return _extract_value_standalone(node, self._get_node_text)

    def _is_number(self, text: str) -> bool:
        """Check if text represents a number."""
        from .yaml_helpers import is_number

        return is_number(text)

    # Extract elements from AST: _extract_sequences
    def _extract_sequences(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML sequences (lists)."""
        for node in self._traverse_nodes(root_node):
            if node.type in ("block_sequence", "flow_sequence"):
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)
                    child_count = _count_sequence_children_standalone(node)

                    nesting_level = self._calculate_nesting_level(node)
                    doc_index = self._get_document_index(node)

                    key = _extract_seq_key_standalone(node, self._get_node_text)

                    element = YAMLElement(
                        name="sequence",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text[:200] + "..."
                        if len(raw_text) > 200
                        else raw_text,
                        element_type="sequence",
                        key=key,
                        value_type="sequence",
                        nesting_level=nesting_level,
                        document_index=doc_index,
                        child_count=child_count,
                    )
                    elements.append(element)
                except Exception:  # nosec B110
                    pass

    # Extract elements from AST: _extract_anchors
    def _extract_anchors(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML anchors (&name)."""
        for node in self._traverse_nodes(root_node):
            if node.type == "anchor":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)
                    anchor_name = raw_text.lstrip("&").strip()

                    nesting_level = self._calculate_nesting_level(node)
                    doc_index = self._get_document_index(node)

                    element = YAMLElement(
                        name=f"&{anchor_name}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="anchor",
                        anchor_name=anchor_name,
                        nesting_level=nesting_level,
                        document_index=doc_index,
                    )
                    elements.append(element)
                except Exception:  # nosec B110
                    pass

    # Extract elements from AST: _extract_aliases
    def _extract_aliases(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML aliases (*name)."""
        for node in self._traverse_nodes(root_node):
            if node.type == "alias":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)
                    alias_target = raw_text.lstrip("*").strip()

                    nesting_level = self._calculate_nesting_level(node)
                    doc_index = self._get_document_index(node)

                    element = YAMLElement(
                        name=f"*{alias_target}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="alias",
                        alias_target=alias_target,
                        nesting_level=nesting_level,
                        document_index=doc_index,
                    )
                    elements.append(element)
                except Exception:  # nosec B110
                    pass

    # Extract elements from AST: _extract_comments
    def _extract_comments(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML comments."""
        for node in self._traverse_nodes(root_node):
            if node.type == "comment":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)
                    comment_text = raw_text.lstrip("#").strip()

                    doc_index = self._get_document_index(node)

                    element = YAMLElement(
                        name=comment_text[:50] + "..."
                        if len(comment_text) > 50
                        else comment_text,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="comment",
                        value=comment_text,
                        value_type="comment",
                        document_index=doc_index,
                        nesting_level=0,
                    )
                    elements.append(element)
                except Exception:  # nosec B110
                    pass


class YAMLPlugin(LanguagePlugin):
    """YAML language plugin using tree-sitter-yaml for true YAML parsing."""

    def __init__(self) -> None:
        """Initialize YAML plugin with extractor."""
        super().__init__()
        self.extractor = YAMLElementExtractor()

    def get_language_name(self) -> str:
        """Return the language name."""
        return "yaml"

    def get_file_extensions(self) -> list[str]:
        """Return supported file extensions."""
        return [".yaml", ".yml"]

    # Extract elements from AST: create_extractor
    def create_extractor(self) -> "YAMLElementExtractor":
        """Create and return a YAML element extractor."""
        return YAMLElementExtractor()

    def get_tree_sitter_language(self) -> Any:
        """Get tree-sitter language object for YAML."""
        if not YAML_AVAILABLE:
            raise ImportError("tree-sitter-yaml not installed")
        return YAML_LANGUAGE

    def get_supported_element_types(self) -> list[str]:
        """Return supported element types."""
        return [
            "mapping",
            "sequence",
            "scalar",
            "anchor",
            "alias",
            "comment",
            "document",
        ]

    def get_queries(self) -> dict[str, str]:
        """Return YAML-specific tree-sitter queries."""
        from ..queries.yaml import YAML_QUERIES

        return YAML_QUERIES

    # Main entry point - dispatches to handler: execute_query_strategy
    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for YAML."""
        if language != "yaml":
            return None

        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """Return YAML element categories for query execution."""
        return {
            "structure": ["document", "block_mapping", "block_sequence"],
            "mappings": ["block_mapping_pair", "flow_pair"],
            "sequences": ["block_sequence", "flow_sequence"],
            "scalars": [
                "plain_scalar",
                "double_quote_scalar",
                "single_quote_scalar",
                "block_scalar",
            ],
            "references": ["anchor", "alias"],
            "metadata": ["comment", "tag"],
        }

    # Analyze source code structure: analyze_file
    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze YAML file using tree-sitter-yaml parser.

        Args:
            file_path: Path to the YAML file
            request: Analysis request parameters

        Returns:
            AnalysisResult with extracted elements
        """
        return _analyze_yaml_file_standalone(
            file_path=file_path,
            create_extractor=self.create_extractor,
            yaml_available=YAML_AVAILABLE,
            parser=globals().get("YAML_PARSER"),
            parser_lock=globals().get("_YAML_PARSER_LOCK"),
        )
