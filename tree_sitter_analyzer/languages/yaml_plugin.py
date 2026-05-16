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

from ..models import AnalysisResult, Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info, log_warning
from .yaml_helpers import (
    calculate_nesting_level as _calc_nesting_standalone,
)
from .yaml_helpers import (
    extract_mapping_key_and_value as _extract_kv_standalone,
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


# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
# Section: module imports and setup
# Section: class definitions
# Section: public API methods
# Section: internal helper methods
# Section: data processing pipeline
# Section: output formatting
# Section: error handling
class YAMLElement(CodeElement):
    """YAML-specific code element."""

    def __init__(
        self,
        name: str,
        start_line: int,
        end_line: int,
        raw_text: str,
        language: str = "yaml",
        element_type: str = "yaml",
        key: str | None = None,
        value: str | None = None,
        value_type: str | None = None,
        anchor_name: str | None = None,
        alias_target: str | None = None,
        nesting_level: int = 0,
        document_index: int = 0,
        child_count: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize YAMLElement.

        Args:
            name: Element name
            start_line: Starting line number
            end_line: Ending line number
            raw_text: Raw text content
            language: Language identifier
            element_type: Type of YAML element
            key: Key for mapping pairs
            value: Scalar value (None for complex structures)
            value_type: Type of value (string, number, boolean, null, mapping, sequence)
            anchor_name: Anchor name for &anchor definitions
            alias_target: Target anchor name for *alias references (not resolved)
            nesting_level: AST-based logical depth
            document_index: Index of document in multi-document YAML
            child_count: Number of child elements for complex structures
            **kwargs: Additional attributes
        """
        super().__init__(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language=language,
            **kwargs,
        )
        self.element_type = element_type
        self.key = key
        self.value = value
        self.value_type = value_type
        self.anchor_name = anchor_name
        self.alias_target = alias_target
        self.nesting_level = nesting_level
        self.document_index = document_index
        self.child_count = child_count


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

    # Process: _get_node_text
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

    # Process: _calculate_nesting_level
    def _calculate_nesting_level(self, node: "tree_sitter.Node") -> int:
        """Calculate AST-based logical nesting level."""
        return _calc_nesting_standalone(node)

    # Process: _get_document_index
    def _get_document_index(self, node: "tree_sitter.Node") -> int:
        """Get document index for a node."""
        return _get_doc_idx_standalone(node)

    # Process: _traverse_nodes
    def _traverse_nodes(self, node: "tree_sitter.Node") -> "list[tree_sitter.Node]":
        """Traverse all nodes in the tree."""
        return _traverse_standalone(node)

    # Process: _count_document_children
    def _count_document_children(self, document_node: "tree_sitter.Node") -> int:
        """Count meaningful children in a document (top-level mappings).

        This counts the number of top-level key-value pairs in the document,
        which is more meaningful than counting AST nodes.
        """
        count = 0
        for child in document_node.children:
            # Skip document markers and comments
            if child.type in ("---", "...", "comment"):
                continue
            # For block_node, count the mappings inside
            if child.type == "block_node":
                for subchild in child.children:
                    if subchild.type == "block_mapping":
                        # Count the mapping pairs
                        count += len(
                            [
                                c
                                for c in subchild.children
                                if c.type == "block_mapping_pair"
                            ]
                        )
                    elif subchild.type in ("block_sequence", "flow_sequence"):
                        count += 1
            elif child.type == "block_mapping":
                count += len(
                    [c for c in child.children if c.type == "block_mapping_pair"]
                )
        return count

    # Extract elements from AST: _extract_documents
    def _extract_documents(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML documents."""
        for node in self._traverse_nodes(root_node):
            if node.type == "document":
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)
                    doc_index = self._get_document_index(node)

                    # Count meaningful child elements (top-level mappings)
                    # Exclude document markers (---) and comments
                    child_count = self._count_document_children(node)

                    element = YAMLElement(
                        name=f"Document {doc_index}",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text[:200] + "..."
                        if len(raw_text) > 200
                        else raw_text,
                        element_type="document",
                        document_index=doc_index,
                        child_count=child_count,
                        nesting_level=0,
                    )
                    elements.append(element)
                except Exception:  # nosec B110
                    pass

    # Extract elements from AST: _extract_mappings
    def _extract_mappings(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML mappings (key-value pairs)."""
        for node in self._traverse_nodes(root_node):
            if node.type in ("block_mapping_pair", "flow_pair"):
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)

                    key, value, value_type, child_count, anchor_name = (
                        _extract_kv_standalone(node, self._get_node_text)
                    )

                    nesting_level = self._calculate_nesting_level(node)
                    doc_index = self._get_document_index(node)

                    element = YAMLElement(
                        name=key or "mapping",
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        element_type="mapping",
                        key=key,
                        value=value,
                        value_type=value_type,
                        nesting_level=nesting_level,
                        document_index=doc_index,
                        child_count=child_count,
                        anchor_name=anchor_name,
                    )
                    elements.append(element)
                except Exception:  # nosec B110
                    pass

    # Extract elements from AST: _extract_value_info
    def _extract_value_info(
        self, node: "tree_sitter.Node | None"
    ) -> tuple[str | None, str | None, int | None]:
        """Extract value information from a node."""
        return _extract_value_standalone(node, self._get_node_text)

    # Process: _is_number
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

                    if node.type == "block_sequence":
                        child_count = len(
                            [
                                c
                                for c in node.children
                                if c.type == "block_sequence_item"
                            ]
                        )
                    else:
                        child_count = len(node.children)

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

    # Process: get_language_name
    def get_language_name(self) -> str:
        """Return the language name."""
        return "yaml"

    # Process: get_file_extensions
    def get_file_extensions(self) -> list[str]:
        """Return supported file extensions."""
        return [".yaml", ".yml"]

    # Extract elements from AST: create_extractor
    def create_extractor(self) -> "YAMLElementExtractor":
        """Create and return a YAML element extractor."""
        return YAMLElementExtractor()

    # Process: get_tree_sitter_language
    def get_tree_sitter_language(self) -> Any:
        """Get tree-sitter language object for YAML."""
        if not YAML_AVAILABLE:
            raise ImportError("tree-sitter-yaml not installed")
        return YAML_LANGUAGE

    # Process: get_supported_element_types
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

    # Process: get_queries
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
            # Return result
            return None

        queries = self.get_queries()
        # Return result
        return queries.get(query_key) if query_key else None

    # Process: get_element_categories
    def get_element_categories(self) -> dict[str, list[str]]:
        """Return YAML element categories for query execution."""
        # Return result
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
        from ..encoding_utils import read_file_safe

        # Check if YAML support is available
        if not YAML_AVAILABLE:
            log_error("tree-sitter-yaml not available")
            # Return result
            return AnalysisResult(
                file_path=file_path,
                language="yaml",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message="YAML support not available. Install tree-sitter-yaml.",
            )

        try:
            # Read file content with encoding detection
            content, encoding = read_file_safe(file_path)

            # Parse the YAML content
            # tree-sitter Parser is not guaranteed to be thread-safe across concurrent calls.
            with _YAML_PARSER_LOCK:
                tree = YAML_PARSER.parse(content.encode("utf-8"))

            # Extract elements using the extractor
            yaml_extractor = self.create_extractor()
            elements = yaml_extractor.extract_yaml_elements(tree, content)

            log_info(f"Extracted {len(elements)} YAML elements from {file_path}")

            # Return result
            return AnalysisResult(
                file_path=file_path,
                language="yaml",
                line_count=len(content.splitlines()),
                elements=elements,
                node_count=len(elements),
                query_results={},
                source_code=content,
                success=True,
                error_message=None,
            )

        except Exception as e:
            log_error(f"Failed to analyze YAML file {file_path}: {e}")
            # Return result
            return AnalysisResult(
                file_path=file_path,
                language="yaml",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
