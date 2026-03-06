#!/usr/bin/env python3
"""
YAML Language Plugin

YAML-specific parsing and element extraction functionality using tree-sitter-yaml.
Provides comprehensive support for YAML elements including mappings, sequences,
scalars, anchors, aliases, and comments.
"""

import logging
import threading
from typing import TYPE_CHECKING, Any, cast

from ..models import AnalysisResult, Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info, log_warning

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

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """YAML doesn't have functions, return empty list."""
        return []

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """YAML doesn't have classes, return empty list."""
        return []

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """YAML doesn't have variables, return empty list."""
        return []

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """YAML doesn't have imports, return empty list."""
        return []

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
        level = 0
        current = node.parent
        while current is not None:
            if current.type in (
                "block_mapping",
                "block_sequence",
                "flow_mapping",
                "flow_sequence",
            ):
                level += 1
            current = getattr(current, "parent", None)
            if current is None:
                break
        return level

    def _get_document_index(self, node: "tree_sitter.Node") -> int:
        """Get document index for a node."""
        current = node
        while current is not None:
            if current.type == "document":
                # Count preceding document siblings
                index = 0
                sibling = current.prev_sibling
                while sibling is not None:
                    if sibling.type == "document":
                        index += 1
                    sibling = sibling.prev_sibling
                return index
            # Use Any type to avoid assignment mismatches on parent
            current = cast(Any, getattr(current, "parent", None))
            if current is None:
                break
        return 0

    def _traverse_nodes(self, node: "tree_sitter.Node") -> "list[tree_sitter.Node]":
        """Traverse all nodes in the tree."""
        nodes = [node]
        for child in node.children:
            nodes.extend(self._traverse_nodes(child))
        return nodes

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

    def _extract_mappings(
        self, root_node: "tree_sitter.Node", elements: list[YAMLElement]
    ) -> None:
        """Extract YAML mappings (key-value pairs).

        Note: Mappings with sequence or mapping values are not extracted here,
        as the sequence/mapping elements themselves will carry the key.
        """
        for node in self._traverse_nodes(root_node):
            if node.type in ("block_mapping_pair", "flow_pair"):
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = self._get_node_text(node)

                    # Extract key and value
                    key = None
                    value = None
                    value_type = None
                    child_count = None
                    anchor_name = None

                    # Find key and value nodes
                    # In tree-sitter-yaml, block_mapping_pair has structure:
                    # flow_node (key), ':', flow_node (value)
                    key_node = None
                    value_node = None
                    found_colon = False

                    for child in node.children:
                        if child.type == ":":
                            found_colon = True
                        elif child.type in ("flow_node", "block_node"):
                            if not found_colon:
                                # This is the key
                                key_node = child
                            else:
                                # This is the value
                                value_node = child
                                # Check for anchor in value node
                                for subchild in child.children:
                                    if subchild.type == "anchor":
                                        anchor_text = self._get_node_text(subchild)
                                        anchor_name = anchor_text.lstrip("&").strip()
                        elif child.type == "key":
                            # Key is wrapped in a "key" node
                            if child.children:
                                key_node = child.children[0]
                            else:
                                key_node = child
                        elif child.type == "value":
                            # Value is wrapped in a "value" node
                            if child.children:
                                value_node = child.children[0]
                            else:
                                value_node = child
                            # Check for anchor in value
                            for subchild in child.children:
                                if subchild.type == "anchor":
                                    anchor_text = self._get_node_text(subchild)
                                    anchor_name = anchor_text.lstrip("&").strip()
                        elif child.type == "anchor":
                            # Anchor at mapping level
                            anchor_text = self._get_node_text(child)
                            anchor_name = anchor_text.lstrip("&").strip()

                    # Extract key text - drill down through flow_node/block_node
                    if key_node is not None:
                        # Drill down to get the actual scalar
                        current = key_node
                        while (
                            current
                            and current.type in ("flow_node", "block_node")
                            and current.children
                        ):
                            current = current.children[0]
                        if current:
                            key = self._get_node_text(current).strip()

                    # Extract value info - drill down through flow_node/block_node
                    if value_node is not None:
                        # Drill down to get the actual value node
                        current = value_node
                        while (
                            current
                            and current.type in ("flow_node", "block_node")
                            and current.children
                        ):
                            current = current.children[0]
                        if current:
                            value, value_type, child_count = self._extract_value_info(
                                current
                            )

                    # Always create mapping element for the key-value pair
                    # Even if value is sequence or mapping, the key itself is important structural information

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

    def _extract_value_info(
        self, node: "tree_sitter.Node | None"
    ) -> tuple[str | None, str | None, int | None]:
        """Extract value information from a node.

        Returns:
            Tuple of (value, value_type, child_count)
        """
        if node is None:
            return None, None, None

        node_type = node.type
        text = self._get_node_text(node).strip()

        # Scalar types
        if node_type in ("plain_scalar", "double_quote_scalar", "single_quote_scalar"):
            # Determine scalar type
            if text.lower() in ("true", "false", "yes", "no", "on", "off"):
                return text, "boolean", None
            elif text.lower() in ("null", "~", ""):
                return text if text else None, "null", None
            elif self._is_number(text):
                # Return "number" for both integer and float to match test expectations
                return text, "number", None
            else:
                return text, "string", None
        elif node_type == "block_scalar":
            return text, "string", None
        elif node_type in ("block_mapping", "flow_mapping"):
            child_count = len(
                [
                    c
                    for c in node.children
                    if c.type in ("block_mapping_pair", "flow_pair")
                ]
            )
            return None, "mapping", child_count
        elif node_type in ("block_sequence", "flow_sequence"):
            child_count = len(
                [c for c in node.children if c.type in ("block_sequence_item",)]
                or node.children
            )
            return None, "sequence", child_count
        elif node_type == "alias":
            alias_name = text.lstrip("*")
            return f"*{alias_name}", "alias", None

        return text, "unknown", None

    def _is_number(self, text: str) -> bool:
        """Check if text represents a number."""
        try:
            float(text)
            return True
        except ValueError:
            return False

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

                    # Count items
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

                    # Try to find the key for this sequence by checking parent mapping
                    key = None
                    parent = node.parent
                    while parent is not None:
                        if parent.type in ("block_mapping_pair", "flow_pair"):
                            # Find the key node in the parent mapping
                            for child in parent.children:
                                if child.type in ("flow_node", "block_node"):
                                    # Check if this is the key (before colon)
                                    found_colon = False
                                    for sibling in parent.children:
                                        if sibling.type == ":":
                                            found_colon = True
                                            break
                                    if (
                                        not found_colon
                                        or child.start_byte
                                        < parent.children[1].start_byte
                                    ):
                                        # This is the key
                                        current = child
                                        while (
                                            current
                                            and current.type
                                            in ("flow_node", "block_node")
                                            and current.children
                                        ):
                                            current = current.children[0]
                                        if current:
                                            key = self._get_node_text(current).strip()
                                            break
                            break
                        parent = getattr(parent, "parent", None)

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
