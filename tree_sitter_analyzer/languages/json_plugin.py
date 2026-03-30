#!/usr/bin/env python3
"""
JSON Language Plugin

JSON-specific parsing and element extraction functionality using tree-sitter-json.
Provides comprehensive support for JSON elements including objects, arrays,
pairs, strings, numbers, booleans, and null values.
"""

import logging
import threading
from typing import TYPE_CHECKING, Any

from ..models import AnalysisResult, Class, CodeElement, Function, Import, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error, log_info, log_warning

if TYPE_CHECKING:
    import tree_sitter

    from ..core.request import AnalysisRequest

logger = logging.getLogger(__name__)

# Graceful degradation for tree-sitter-json
try:
    import tree_sitter
    import tree_sitter_json as ts_json

    JSON_AVAILABLE = True
    # Pre-initialize JSON language at import time to avoid per-test/per-call cold-start costs.
    JSON_LANGUAGE = tree_sitter.Language(ts_json.language())
    JSON_PARSER = tree_sitter.Parser()
    JSON_PARSER.language = JSON_LANGUAGE
    _JSON_PARSER_LOCK = threading.Lock()
except ImportError:
    JSON_AVAILABLE = False
    log_warning("tree-sitter-json not installed, JSON support disabled")


class JSONElement(CodeElement):
    """JSON-specific code element."""

    def __init__(
        self,
        name: str,
        start_line: int,
        end_line: int,
        raw_text: str,
        language: str = "json",
        element_type: str = "json",
        key: str | None = None,
        value: str | None = None,
        value_type: str | None = None,
        nesting_level: int = 0,
        child_count: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize JSONElement.

        Args:
            name: Element name
            start_line: Starting line number
            end_line: Ending line number
            raw_text: Raw text content
            language: Language identifier
            element_type: Type of JSON element
            key: Key for object pairs
            value: Scalar value (None for complex structures)
            value_type: Type of value (string, number, boolean, null, object, array)
            nesting_level: AST-based logical depth
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
        self.nesting_level = nesting_level
        self.child_count = child_count


class JSONElementExtractor(ElementExtractor):
    """JSON-specific element extractor using tree-sitter-json."""

    def __init__(self) -> None:
        """Initialize the JSON element extractor."""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """JSON doesn't have functions, return empty list."""
        return []

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """JSON doesn't have classes, return empty list."""
        return []

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """JSON doesn't have variables, return empty list."""
        return []

    def extract_imports(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Import]:
        """JSON doesn't have imports, return empty list."""
        return []

    def extract_json_elements(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[JSONElement]:
        """Extract all JSON elements from the parsed tree.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Original source code

        Returns:
            List of JSONElement objects
        """
        self.source_code = source_code or ""
        self.content_lines = self.source_code.split("\n")
        self._node_text_cache = {}

        elements: list[JSONElement] = []

        if tree is None or tree.root_node is None:
            return elements

        try:
            # Extract all JSON node types
            self._extract_elements_by_type(tree.root_node, elements)
        except Exception as e:
            log_error(f"Error during JSON element extraction: {e}")

        log_debug(f"Extracted {len(elements)} JSON elements")
        return elements

    def extract_elements(
        self, tree: "tree_sitter.Tree | None", source_code: str
    ) -> list[JSONElement]:
        """Alias for extract_json_elements for compatibility with tests.

        Args:
            tree: Parsed tree-sitter tree
            source_code: Original source code

        Returns:
            List of JSONElement objects
        """
        return self.extract_json_elements(tree, source_code)

    def _get_node_text(self, node: "tree_sitter.Node") -> str:
        """Get text content from a tree-sitter node."""
        try:
            if hasattr(node, "start_byte") and hasattr(node, "end_byte"):
                cache_key = (node.start_byte, node.end_byte)
                if cache_key in self._node_text_cache:
                    return self._node_text_cache[cache_key]

                source_bytes = self.source_code.encode("utf-8")
                node_bytes = source_bytes[node.start_byte : node.end_byte]
                text = node_bytes.decode("utf-8", errors="replace")
                self._node_text_cache[cache_key] = text
                return text
            return ""
        except Exception as e:
            log_debug(f"Failed to extract node text: {e}")
            return ""

    def _calculate_nesting_level(self, node: "tree_sitter.Node") -> int:
        """Calculate AST-based logical nesting level."""
        level = 0
        current = node.parent
        while current is not None:
            if current.type in ("object", "array"):
                level += 1
            current = getattr(current, "parent", None)
            if current is None:
                break
        return level

    def _traverse_nodes(self, node: "tree_sitter.Node") -> "list[tree_sitter.Node]":
        """Traverse all nodes in the tree."""
        nodes = [node]
        for child in node.children:
            nodes.extend(self._traverse_nodes(child))
        return nodes

    def _extract_elements_by_type(
        self, root_node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract all JSON elements by traversing the tree."""
        for node in self._traverse_nodes(root_node):
            node_type = node.type

            # Extract based on node type
            if node_type == "object":
                self._extract_object(node, elements)
            elif node_type == "array":
                self._extract_array(node, elements)
            elif node_type == "pair":
                self._extract_pair(node, elements)
            elif node_type == "string":
                self._extract_string(node, elements)
            elif node_type == "number":
                self._extract_number(node, elements)
            elif node_type == "true":
                self._extract_boolean(node, elements, True)
            elif node_type == "false":
                self._extract_boolean(node, elements, False)
            elif node_type == "null":
                self._extract_null(node, elements)

    def _extract_object(
        self, node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract JSON object."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            # Count pairs in object
            child_count = len([c for c in node.children if c.type == "pair"])

            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name="object",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
                element_type="object",
                value_type="object",
                nesting_level=nesting_level,
                child_count=child_count,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_array(
        self, node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract JSON array."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            # Count items in array (exclude brackets and commas)
            child_count = len(
                [
                    c
                    for c in node.children
                    if c.type not in ("[", "]", ",", "ERROR")
                ]
            )

            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name="array",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
                element_type="array",
                value_type="array",
                nesting_level=nesting_level,
                child_count=child_count,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_pair(
        self, node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract JSON key-value pair."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            key = None
            value = None
            value_type = None

            # Extract key and value from pair
            # In tree-sitter-json, pair has structure: string (key), ":", value
            key_node = None
            value_node = None

            for child in node.children:
                if child.type == "string" and key_node is None:
                    # First string is the key
                    key_node = child
                elif child.type != ":" and child.type != "," and key_node is not None:
                    # After colon, this is the value
                    value_node = child
                    break

            # Extract key text (remove quotes)
            if key_node is not None:
                key_text = self._get_node_text(key_node).strip()
                # Remove surrounding quotes
                if key_text.startswith('"') and key_text.endswith('"'):
                    key = key_text[1:-1]
                else:
                    key = key_text

            # Extract value info
            if value_node is not None:
                value, value_type = self._extract_value_info(value_node)

            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name=key or "pair",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                element_type="pair",
                key=key,
                value=value,
                value_type=value_type,
                nesting_level=nesting_level,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_string(
        self, node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract JSON string."""
        try:
            # Skip strings that are keys in pairs (already handled by pair extraction)
            if node.parent and node.parent.type == "pair":
                # Check if this is the key (first child)
                if node.parent.children and node.parent.children[0] == node:
                    return

            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            # Remove quotes from string value
            value = raw_text.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]

            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name="string",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                element_type="string",
                value=value,
                value_type="string",
                nesting_level=nesting_level,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_number(
        self, node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract JSON number."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            value = raw_text.strip()
            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name="number",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                element_type="number",
                value=value,
                value_type="number",
                nesting_level=nesting_level,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_boolean(
        self, node: "tree_sitter.Node", elements: list[JSONElement], bool_value: bool
    ) -> None:
        """Extract JSON boolean."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            value = "true" if bool_value else "false"
            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name=value,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                element_type=value,
                value=value,
                value_type="boolean",
                nesting_level=nesting_level,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_null(
        self, node: "tree_sitter.Node", elements: list[JSONElement]
    ) -> None:
        """Extract JSON null."""
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            raw_text = self._get_node_text(node)

            nesting_level = self._calculate_nesting_level(node)

            element = JSONElement(
                name="null",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                element_type="null",
                value="null",
                value_type="null",
                nesting_level=nesting_level,
            )
            elements.append(element)
        except Exception:  # nosec B110
            pass

    def _extract_value_info(
        self, node: "tree_sitter.Node | None"
    ) -> tuple[str | None, str | None]:
        """Extract value information from a node.

        Returns:
            Tuple of (value, value_type)
        """
        if node is None:
            return None, None

        node_type = node.type
        text = self._get_node_text(node).strip()

        # Determine value type based on node type
        if node_type == "string":
            # Remove quotes
            if text.startswith('"') and text.endswith('"'):
                return text[1:-1], "string"
            return text, "string"
        elif node_type == "number":
            return text, "number"
        elif node_type == "true":
            return "true", "boolean"
        elif node_type == "false":
            return "false", "boolean"
        elif node_type == "null":
            return "null", "null"
        elif node_type == "object":
            return None, "object"
        elif node_type == "array":
            return None, "array"

        return text, "unknown"


class JSONPlugin(LanguagePlugin):
    """JSON language plugin using tree-sitter-json for true JSON parsing."""

    def __init__(self) -> None:
        """Initialize JSON plugin with extractor."""
        super().__init__()
        self.extractor = JSONElementExtractor()

    def get_language_name(self) -> str:
        """Return the language name."""
        return "json"

    def get_file_extensions(self) -> list[str]:
        """Return supported file extensions."""
        return [".json"]

    def create_extractor(self) -> "JSONElementExtractor":
        """Create and return a JSON element extractor."""
        return JSONElementExtractor()

    def get_tree_sitter_language(self) -> Any:
        """Get tree-sitter language object for JSON."""
        if not JSON_AVAILABLE:
            raise ImportError("tree-sitter-json not installed")
        return JSON_LANGUAGE

    def get_supported_element_types(self) -> list[str]:
        """Return supported element types."""
        return [
            "object",
            "array",
            "pair",
            "string",
            "number",
            "true",
            "false",
            "null",
        ]

    def get_queries(self) -> dict[str, str]:
        """Return JSON-specific tree-sitter queries."""
        # JSON queries can be added later if needed
        return {}

    def execute_query_strategy(
        self, query_key: str | None, language: str
    ) -> str | None:
        """Execute query strategy for JSON."""
        if language != "json":
            return None

        queries = self.get_queries()
        return queries.get(query_key) if query_key else None

    def get_element_categories(self) -> dict[str, list[str]]:
        """Return JSON element categories for query execution."""
        return {
            "structure": ["object", "array"],
            "pairs": ["pair"],
            "scalars": ["string", "number", "true", "false", "null"],
        }

    async def analyze_file(
        self, file_path: str, request: "AnalysisRequest"
    ) -> "AnalysisResult":
        """Analyze JSON file using tree-sitter-json parser.

        Args:
            file_path: Path to the JSON file
            request: Analysis request parameters

        Returns:
            AnalysisResult with extracted elements
        """
        from ..encoding_utils import read_file_safe

        # Check if JSON support is available
        if not JSON_AVAILABLE:
            log_error("tree-sitter-json not available")
            return AnalysisResult(
                file_path=file_path,
                language="json",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message="JSON support not available. Install tree-sitter-json.",
            )

        try:
            # Read file content with encoding detection
            content, encoding = read_file_safe(file_path)

            # Parse the JSON content
            # tree-sitter Parser is not guaranteed to be thread-safe across concurrent calls.
            with _JSON_PARSER_LOCK:
                tree = JSON_PARSER.parse(content.encode("utf-8"))

            # Extract elements using the extractor
            json_extractor = self.create_extractor()
            elements = json_extractor.extract_json_elements(tree, content)

            log_info(f"Extracted {len(elements)} JSON elements from {file_path}")

            return AnalysisResult(
                file_path=file_path,
                language="json",
                line_count=len(content.splitlines()),
                elements=elements,
                node_count=len(elements),
                query_results={},
                source_code=content,
                success=True,
                error_message=None,
            )

        except Exception as e:
            log_error(f"Failed to analyze JSON file {file_path}: {e}")
            return AnalysisResult(
                file_path=file_path,
                language="json",
                line_count=0,
                elements=[],
                node_count=0,
                query_results={},
                source_code="",
                success=False,
                error_message=str(e),
            )
