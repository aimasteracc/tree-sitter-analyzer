#!/usr/bin/env python3
"""
Base Element Extractor

Provides concrete base implementation for language-specific element extractors.
Contains common functionality like cache management, node text extraction,
and AST traversal that is shared across all language plugins.

This class sits between the abstract ElementExtractor interface and
the concrete language implementations (JavaElementExtractor, PythonElementExtractor, etc.).

Inheritance hierarchy:
    ElementExtractor (ABC) - Abstract interface
    └── BaseElementExtractor - Common implementation (this class)
        ├── JavaElementExtractor
        ├── PythonElementExtractor
        └── ... other language extractors
"""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from ..utils import log_debug, log_error, log_warning
from .base import ElementExtractor

if TYPE_CHECKING:
    import tree_sitter


class BaseElementExtractor(ElementExtractor):
    """
    Concrete base class providing common implementation for language plugins.

    Provides:
    - Cache management (node text, processed nodes, elements)
    - Generic AST traversal algorithms
    - Node text extraction with encoding support
    - Performance optimization through caching

    Subclasses should:
    - Call super().__init__() in their __init__
    - Override _reset_caches() if they have additional caches
    - Override _get_container_node_types() for language-specific containers
    - Use _initialize_source() at the start of extraction methods

    Example usage in subclass:
        class PythonElementExtractor(BaseElementExtractor):
            def __init__(self):
                super().__init__()
                self._docstring_cache: dict[int, str] = {}  # Python-specific

            def _reset_caches(self):
                super()._reset_caches()
                self._docstring_cache.clear()

            def extract_functions(self, tree, source_code):
                self._initialize_source(source_code)
                # ... extraction logic using self._get_node_text_optimized()
    """

    # Maximum inheritance depth allowed (design constraint)
    _MAX_INHERITANCE_DEPTH = 3

    def __init__(self) -> None:
        """
        Initialize the base element extractor with common caches.

        Sets up:
        - Node text cache: Maps (start_byte, end_byte) -> extracted text
        - Processed nodes: Set of node IDs already processed
        - Element cache: Maps (node_id, element_type) -> extracted element
        - Source code storage: Current file's content
        """
        super().__init__()

        # Performance optimization caches
        # Key: (start_byte, end_byte) for deterministic, reproducible caching
        self._node_text_cache: dict[tuple[int, int], str] = {}

        # Track processed nodes to avoid duplicate extraction
        self._processed_nodes: set[int] = set()

        # Cache extracted elements: (node_id, element_type) -> element
        self._element_cache: dict[tuple[int, str], Any] = {}

        # Source code management
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._file_encoding: str = "utf-8"

    # =========================================================================
    # Cache Management (P0)
    # =========================================================================

    def _reset_caches(self) -> None:
        """
        Reset all performance caches.

        Call this before analyzing a new file to prevent cross-file contamination.
        Subclasses with additional caches should override and call super().

        Example:
            def _reset_caches(self):
                super()._reset_caches()
                self._my_custom_cache.clear()
        """
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()

    def _initialize_source(self, source_code: str, encoding: str = "utf-8") -> None:
        """
        Initialize source code for processing.

        This method should be called at the beginning of each extraction method
        (extract_functions, extract_classes, etc.) to set up the source code
        and reset caches.

        Args:
            source_code: The source code to analyze
            encoding: Character encoding (default: utf-8)

        Example:
            def extract_functions(self, tree, source_code):
                self._initialize_source(source_code)
                # ... extraction logic
        """
        self.source_code = source_code
        self.content_lines = source_code.split("\n") if source_code else []
        self._file_encoding = encoding
        self._reset_caches()

    # =========================================================================
    # Node Text Extraction (P0)
    # =========================================================================

    def _get_node_text_optimized(
        self,
        node: "tree_sitter.Node",
        use_byte_offsets: bool = True,
    ) -> str:
        """
        Extract text from AST node with caching.

        Uses position-based cache keys (start_byte, end_byte) for deterministic
        behavior across test runs.

        Args:
            node: Tree-sitter AST node
            use_byte_offsets: If True, use byte-based extraction (recommended for UTF-8).
                             If False, fall back to line/column-based extraction.

        Returns:
            Extracted text string, or empty string on error

        Performance:
            - First call: O(n) where n is text length
            - Subsequent calls with same node position: O(1) cache lookup
        """
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        text = ""
        try:
            if use_byte_offsets:
                text = self._extract_text_by_bytes(node)
            else:
                text = self._extract_text_by_position(node)

            # If byte extraction returns empty, try position-based fallback
            if not text and use_byte_offsets:
                text = self._extract_text_by_position(node)

        except Exception as e:
            log_error(f"Node text extraction failed: {e}")
            # Try fallback on error
            try:
                text = self._extract_text_by_position(node)
            except Exception:
                text = ""

        self._node_text_cache[cache_key] = text
        return text

    def _extract_text_by_bytes(self, node: "tree_sitter.Node") -> str:
        """
        Extract text using byte offsets (UTF-8 optimized).

        This is the preferred method for UTF-8 encoded files as it handles
        multi-byte characters correctly.

        Args:
            node: Tree-sitter AST node

        Returns:
            Extracted text string
        """
        # Import here to avoid circular imports and for lazy loading
        from ..encoding_utils import extract_text_slice, safe_encode

        content_bytes = safe_encode("\n".join(self.content_lines), self._file_encoding)
        return extract_text_slice(
            content_bytes,
            node.start_byte,
            node.end_byte,
            self._file_encoding,
        )

    def _extract_text_by_position(self, node: "tree_sitter.Node") -> str:
        """
        Extract text using line/column positions (fallback method).

        Use this when byte-based extraction fails or for non-UTF-8 encodings.

        Args:
            node: Tree-sitter AST node

        Returns:
            Extracted text string
        """
        start_point: tuple[int, int] = node.start_point
        end_point: tuple[int, int] = node.end_point

        # Boundary validation
        if not self.content_lines:
            return ""

        if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
            return ""

        if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
            return ""

        # Single line extraction
        if start_point[0] == end_point[0]:
            line = self.content_lines[start_point[0]]
            start_col = max(0, min(start_point[1], len(line)))
            end_col = max(start_col, min(end_point[1], len(line)))
            return line[start_col:end_col]

        # Multi-line extraction
        lines: list[str] = []
        for i in range(start_point[0], end_point[0] + 1):
            if i >= len(self.content_lines):
                break

            line = self.content_lines[i]
            if i == start_point[0]:
                # First line: from start column to end
                start_col = max(0, min(start_point[1], len(line)))
                lines.append(line[start_col:])
            elif i == end_point[0]:
                # Last line: from beginning to end column
                end_col = max(0, min(end_point[1], len(line)))
                lines.append(line[:end_col])
            else:
                # Middle lines: entire line
                lines.append(line)

        return "\n".join(lines)

    # =========================================================================
    # AST Traversal (P1)
    # =========================================================================

    def _get_container_node_types(self) -> set[str]:
        """
        Get node types that may contain target elements.

        Override in subclasses for language-specific containers.
        These are nodes that should be traversed into to find target elements.

        Returns:
            Set of node type strings

        Example override for Java:
            def _get_container_node_types(self):
                return super()._get_container_node_types() | {
                    "class_body",
                    "interface_body",
                    "enum_body",
                }
        """
        return {
            "program",
            "module",
            "block",
            "body",
            "statement_block",
        }

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: Mapping[str, Callable[["tree_sitter.Node"], Any]],
        results: list[Any],
        element_type: str,
        max_depth: int = 50,
    ) -> None:
        """
        Generic iterative AST traversal with element extraction.

        Uses a stack-based approach to avoid recursion limits on deeply
        nested code structures.

        Args:
            root_node: Root node to start traversal (None is handled gracefully)
            extractors: Mapping of node types to extractor functions.
                       Example: {"function_definition": self._extract_function}
            results: List to accumulate extracted elements
            element_type: Type identifier for caching (e.g., "function", "class")
            max_depth: Maximum traversal depth (default: 50)

        Example usage:
            def extract_functions(self, tree, source_code):
                self._initialize_source(source_code)
                results = []
                extractors = {
                    "function_definition": self._extract_function_optimized,
                }
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, results, "function"
                )
                return results
        """
        if not root_node:
            return

        target_node_types = set(extractors.keys())
        container_node_types = self._get_container_node_types()

        # Stack of (node, depth) tuples for iterative DFS
        node_stack: list[tuple[tree_sitter.Node, int]] = [(root_node, 0)]
        processed_count = 0

        while node_stack:
            current_node, depth = node_stack.pop()

            # Depth limit check
            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue

            processed_count += 1
            node_type = current_node.type

            # Early termination: skip irrelevant nodes
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue

            # Process target nodes
            if node_type in target_node_types:
                node_id = id(current_node)

                # Skip already processed nodes
                if node_id in self._processed_nodes:
                    continue

                # Check element cache
                cache_key = (node_id, element_type)
                if cache_key in self._element_cache:
                    element = self._element_cache[cache_key]
                    self._append_element_to_results(element, results)
                    self._processed_nodes.add(node_id)
                    continue

                # Extract and cache
                extractor = extractors.get(node_type)
                if extractor:
                    try:
                        element = extractor(current_node)
                        self._element_cache[cache_key] = element
                        self._append_element_to_results(element, results)
                        self._processed_nodes.add(node_id)
                    except Exception as e:
                        log_error(f"Element extraction failed for {node_type}: {e}")
                        self._processed_nodes.add(node_id)

            # Add children to stack for traversal
            self._push_children_to_stack(current_node, depth, node_stack)

        log_debug(f"Iterative traversal processed {processed_count} nodes")

    def _append_element_to_results(self, element: Any, results: list[Any]) -> None:
        """
        Helper to append element(s) to results list.

        Handles both single elements and lists of elements.

        Args:
            element: Single element or list of elements
            results: Target list to append to
        """
        if element:
            if isinstance(element, list):
                results.extend(element)
            else:
                results.append(element)

    def _push_children_to_stack(
        self,
        node: "tree_sitter.Node",
        depth: int,
        stack: list[tuple["tree_sitter.Node", int]],
    ) -> None:
        """
        Helper to push children to traversal stack.

        Handles Mock objects gracefully for testing purposes.

        Args:
            node: Parent node
            depth: Current traversal depth
            stack: Stack to push children to
        """
        if not node.children:
            return

        try:
            # Reverse children for correct DFS order
            children_list = list(node.children)
            for child in reversed(children_list):
                stack.append((child, depth + 1))
        except TypeError:
            # Fallback for Mock objects that don't support reversed()
            try:
                children_list = list(node.children)
                for child in children_list:
                    stack.append((child, depth + 1))
            except (TypeError, AttributeError):
                # Node has no iterable children
                pass

    # =========================================================================
    # Complexity Calculation (P2)
    # =========================================================================

    def _get_decision_keywords(self) -> set[str]:
        """
        Get language-specific decision keywords for complexity calculation.

        Override in subclasses for language-specific keywords.

        Returns:
            Set of node type strings that represent decision points
        """
        return {
            "if_statement",
            "if_expression",
            "for_statement",
            "for_expression",
            "while_statement",
            "while_expression",
            "case",
            "catch_clause",
            "except_clause",
            "conditional_expression",
            "ternary_expression",
            "and",
            "or",
            "&&",
            "||",
        }

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """
        Calculate cyclomatic complexity for a node.

        Default implementation counts decision points using _get_decision_keywords().
        Override for language-specific complexity rules.

        Args:
            node: AST node (typically a function or method)

        Returns:
            Complexity score (minimum 1)
        """
        complexity = 1  # Base complexity

        decision_keywords = self._get_decision_keywords()

        def count_decisions(n: "tree_sitter.Node") -> int:
            count = 0
            if n.type in decision_keywords:
                count += 1
            for child in n.children:
                count += count_decisions(child)
            return count

        complexity += count_decisions(node)
        return complexity
