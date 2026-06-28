#!/usr/bin/env python3
"""
JSON Language Plugin

JSON-specific parsing and element extraction functionality using tree-sitter-json.
Provides comprehensive support for JSON elements including objects, arrays,
pairs, strings, numbers, booleans, and null values.
"""

from __future__ import annotations

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
        super().__init__(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language=language,
            **kwargs,
        )
        self.element_type = element_type
        # Mirror element_type in .type so formatters using e.get("type") also work.
        self.type = element_type
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
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """JSON doesn't have functions, return empty list."""
        return []

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """JSON doesn't have classes, return empty list."""
        return []

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """JSON doesn't have variables, return empty list."""
        return []

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """JSON doesn't have imports, return empty list."""
        return []

    def extract_json_elements(
        self, tree: tree_sitter.Tree | None, source_code: str
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
        self, tree: tree_sitter.Tree | None, source_code: str
    ) -> dict[str, list[Any]]:
        """Return JSON elements grouped under the ``json_elements`` key.

        The signature matches ``ElementExtractor.extract_elements`` (LSP),
        while the actual collected elements live under a JSON-specific key
        so downstream consumers can branch on it. Callers that want the
        bare list should call :py:meth:`extract_json_elements` directly.
        """
        return {"json_elements": list(self.extract_json_elements(tree, source_code))}

    def _get_node_text(self, node: tree_sitter.Node) -> str:
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

    def _calculate_nesting_level(self, node: tree_sitter.Node) -> int:
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

    def _traverse_nodes(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """Traverse all nodes in the tree."""
        nodes = [node]
        for child in node.children:
            nodes.extend(self._traverse_nodes(child))
        return nodes

    def _extract_elements_by_type(
        self, root_node: tree_sitter.Node, elements: list[JSONElement]
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

    def _make_element(
        self,
        node: tree_sitter.Node,
        name: str,
        element_type: str,
        *,
        value: str | None = None,
        value_type: str | None = None,
        key: str | None = None,
        child_count: int | None = None,
        truncate_text: bool = False,
    ) -> JSONElement:
        """Build a JSONElement from a node (shared helper to reduce repetition)."""
        raw_text = self._get_node_text(node)
        if truncate_text and len(raw_text) > 200:
            raw_text = raw_text[:200] + "..."
        return JSONElement(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            element_type=element_type,
            key=key,
            value=value,
            value_type=value_type or element_type,
            nesting_level=self._calculate_nesting_level(node),
            child_count=child_count,
        )

    def _extract_object(
        self, node: tree_sitter.Node, elements: list[JSONElement]
    ) -> None:
        """Extract JSON object."""
        try:
            child_count = sum(1 for c in node.children if c.type == "pair")
            elements.append(
                self._make_element(
                    node,
                    "object",
                    "object",
                    child_count=child_count,
                    truncate_text=True,
                )
            )
        except Exception:  # nosec B110
            pass

    def _extract_array(
        self, node: tree_sitter.Node, elements: list[JSONElement]
    ) -> None:
        """Extract JSON array."""
        try:
            child_count = sum(
                1 for c in node.children if c.type not in ("[", "]", ",", "ERROR")
            )
            elements.append(
                self._make_element(
                    node, "array", "array", child_count=child_count, truncate_text=True
                )
            )
        except Exception:  # nosec B110
            pass

    def _extract_pair(
        self, node: tree_sitter.Node, elements: list[JSONElement]
    ) -> None:
        """Extract JSON key-value pair (tree-sitter structure: string, ':', value)."""
        try:
            key_node = value_node = None
            for child in node.children:
                if child.type == "string" and key_node is None:
                    key_node = child
                elif child.type not in (":", ",") and key_node is not None:
                    value_node = child
                    break
            key = None
            if key_node is not None:
                kt = self._get_node_text(key_node).strip()
                key = kt[1:-1] if kt.startswith('"') and kt.endswith('"') else kt
            value, value_type = self._extract_value_info(value_node)
            elements.append(
                self._make_element(
                    node,
                    key or "pair",
                    "pair",
                    key=key,
                    value=value,
                    value_type=value_type,
                )
            )
        except Exception:  # nosec B110
            pass

    def _extract_string(
        self, node: tree_sitter.Node, elements: list[JSONElement]
    ) -> None:
        """Extract JSON string (skip pair keys — handled by _extract_pair)."""
        try:
            if node.parent and node.parent.type == "pair":
                if node.parent.children and node.parent.children[0] == node:
                    return
            raw_text = self._get_node_text(node)
            value = raw_text.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elements.append(self._make_element(node, "string", "string", value=value))
        except Exception:  # nosec B110
            pass

    def _extract_number(
        self, node: tree_sitter.Node, elements: list[JSONElement]
    ) -> None:
        """Extract JSON number."""
        try:
            value = self._get_node_text(node).strip()
            elements.append(self._make_element(node, "number", "number", value=value))
        except Exception:  # nosec B110
            pass

    def _extract_boolean(
        self, node: tree_sitter.Node, elements: list[JSONElement], bool_value: bool
    ) -> None:
        """Extract JSON boolean."""
        try:
            value = "true" if bool_value else "false"
            elements.append(
                self._make_element(
                    node, value, value, value=value, value_type="boolean"
                )
            )
        except Exception:  # nosec B110
            pass

    def _extract_null(
        self, node: tree_sitter.Node, elements: list[JSONElement]
    ) -> None:
        """Extract JSON null."""
        try:
            elements.append(self._make_element(node, "null", "null", value="null"))
        except Exception:  # nosec B110
            pass

    def _extract_value_info(
        self, node: tree_sitter.Node | None
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

    def create_extractor(self) -> JSONElementExtractor:
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

    def extract_elements(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> dict[str, list]:
        """Unified extraction entry point — delegates to the extractor."""
        return self.create_extractor().extract_elements(tree, source_code)

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze JSON file using tree-sitter-json parser."""
        from ..encoding_utils import read_file_safe

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
            content, _encoding = read_file_safe(file_path)
            # tree-sitter Parser is not thread-safe across concurrent calls.
            with _JSON_PARSER_LOCK:
                tree = JSON_PARSER.parse(content.encode("utf-8"))
            elements = self.create_extractor().extract_json_elements(tree, content)
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
