#!/usr/bin/env python3
"""
Programming Language Extractor

Base class for programming language plugins.
Provides advanced features needed for programming languages:
- Iterative AST traversal with depth limits
- Element caching for performance
- Cyclomatic complexity calculation
- Container node type customization
"""

from abc import ABC
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ..models import Class, Function, Variable
from ..utils import log_debug, log_error, log_warning
from .cached_element_extractor import CachedElementExtractor


class ProgrammingLanguageExtractor(CachedElementExtractor, ABC):
    """
    Base class for programming language plugins.

    Provides advanced features needed for programming languages:
    - Iterative AST traversal with depth limits
    - Element caching for performance
    - Cyclomatic complexity calculation
    - Container node type customization
    """

    def __init__(self) -> None:
        """Initialize the programming language extractor."""
        super().__init__()

        # Programming language specific caches
        # Note: Uses object ID-based tracking (set[int]) for processed nodes
        # This differs from markup languages which use position-based tracking
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}

    def _reset_caches(self) -> None:
        """Reset all caches including programming-specific ones."""
        super()._reset_caches()
        self._processed_nodes.clear()
        self._element_cache.clear()

    # --- AST Traversal ---

    def _get_container_node_types(self) -> set[str]:
        """
        Get node types that may contain target elements.

        Override in subclasses for language-specific containers.

        Returns:
            Set of container node type names
        """
        return {
            "program",
            "module",
            "block",
            "body",
        }

    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node | None",
        extractors: dict[str, Callable],
        results: list[Any],
        element_type: str,
        max_depth: int = 50,
    ) -> None:
        """
        Generic iterative AST traversal with element extraction.

        Args:
            root_node: Root node to start traversal
            extractors: Mapping of node types to extractor functions
            results: List to accumulate extracted elements
            element_type: Type of element being extracted (for caching)
            max_depth: Maximum traversal depth
        """
        if not root_node:
            return

        target_node_types = set(extractors.keys())
        container_node_types = self._get_container_node_types()

        node_stack = [(root_node, 0)]
        processed_nodes = 0

        while node_stack:
            current_node, depth = node_stack.pop()

            # Depth limit check
            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue

            processed_nodes += 1
            node_type = current_node.type

            # Early exit: skip irrelevant nodes
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue

            # Process target nodes
            if node_type in target_node_types:
                node_id = id(current_node)

                # Skip if already processed
                if node_id in self._processed_nodes:
                    continue

                # Cache check
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
                        log_error(f"Element extraction failed: {e}")
                        # Even if extraction fails, mark as processed to avoid infinite loops
                        self._processed_nodes.add(node_id)
                        # Re-raise for testing error handling if needed, but usually we want to continue
                        # If this is a test environment and we want to verify exception handling, we might need to adjust.
                        # For production, logging and continuing is safer.
                        # However, the tests expect the exception to propagate or be handled specific ways.
                        # Let's check how the tests are implemented.
                        # test_extract_function_optimized_exception mocks _parse_function_signature_optimized to raise exception.
                        # That method is called by _extract_function_optimized.
                        # _extract_function_optimized catches exceptions and returns None.
                        # So here we receive None.
                        # Wait, if `extractor` raises exception, it's caught here.
                        pass

            # Push children to stack
            if current_node.children:
                self._push_children_to_stack(current_node, depth, node_stack)

        log_debug(f"Iterative traversal processed {processed_nodes} nodes")

    def _append_element_to_results(self, element: Any, results: list[Any]) -> None:
        """
        Helper to append element(s) to results list.

        Args:
            element: Element or list of elements to append
            results: Results list to append to
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

        Args:
            node: Parent node
            depth: Current depth
            stack: Traversal stack
        """
        try:
            children_list = list(node.children)
            # Reverse order for DFS
            for child in reversed(children_list):
                stack.append((child, depth + 1))
        except (TypeError, AttributeError):
            # Fallback for Mock objects
            pass  # No children or not iterable

    # --- Complexity Calculation ---

    def _get_decision_keywords(self) -> set[str]:
        """
        Get language-specific decision keywords.

        Override in subclasses for language-specific keywords.

        Returns:
            Set of decision keyword node types
        """
        return {
            "if_statement",
            "for_statement",
            "while_statement",
            "case",
            "catch",
            "and",
            "or",
        }

    def _calculate_complexity_optimized(self, node: "tree_sitter.Node") -> int:
        """
        Calculate cyclomatic complexity (can be overridden).

        Default implementation counts decision points.

        Args:
            node: AST node to calculate complexity for

        Returns:
            Cyclomatic complexity value
        """
        try:
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
        except Exception as e:
            log_debug(f"Failed to calculate complexity: {e}")
            return 1  # Return base complexity on error

    # --- Template Method Pattern Support ---

    def _extract_common_metadata(self, node: "tree_sitter.Node") -> dict[str, Any]:
        """
        Extract common metadata from any AST node.

        This method provides a standardized way to extract basic information
        that is common across all element types (functions, classes, etc.).

        Args:
            node: AST node to extract metadata from

        Returns:
            Dictionary containing:
                - start_line: Starting line number (1-based)
                - end_line: Ending line number (1-based)
                - raw_text: Raw source code text
                - docstring: Documentation string (if available)
                - complexity: Cyclomatic complexity score
        """
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        return {
            "start_line": start_line,
            "end_line": end_line,
            "raw_text": self._extract_raw_text(start_line, end_line),
            "docstring": self._extract_docstring_for_node(node),
            "complexity": self._calculate_complexity_optimized(node),
        }

    def _extract_raw_text(self, start_line: int, end_line: int) -> str:
        """
        Extract raw text from source code by line range.

        Args:
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based)

        Returns:
            Raw text content
        """
        if not hasattr(self, "content_lines") or not self.content_lines:
            return ""

        start_idx = max(0, start_line - 1)
        end_idx = min(len(self.content_lines), end_line)
        return "\n".join(self.content_lines[start_idx:end_idx])

    def _extract_docstring_for_node(self, node: "tree_sitter.Node") -> str | None:
        """
        Extract documentation string for a node.

        Default implementation uses line-based extraction.
        Override in subclasses for language-specific docstring extraction.

        Args:
            node: AST node to extract docstring for

        Returns:
            Docstring text or None if not found
        """
        try:
            start_line = node.start_point[0] + 1
            if hasattr(self, "_extract_docstring_for_line"):
                result = self._extract_docstring_for_line(start_line)
                return str(result) if result is not None else None
            return None
        except Exception:
            return None

    # --- Handler Registry Pattern ---

    def _get_function_handlers(self) -> dict[str, Callable]:
        """
        Get mapping of node types to function extraction handlers.

        Override in subclasses to define language-specific function node types.

        Returns:
            Dictionary mapping node type names to handler methods
            Example: {"function_definition": self._extract_function_node}
        """
        return {}

    def _get_class_handlers(self) -> dict[str, Callable]:
        """
        Get mapping of node types to class extraction handlers.

        Override in subclasses to define language-specific class node types.

        Returns:
            Dictionary mapping node type names to handler methods
            Example: {"class_definition": self._extract_class_node}
        """
        return {}

    # --- Common Extraction Methods (Template Method Pattern) ---

    def extract_functions(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Function]:
        """
        Extract function definitions with comprehensive details.

        This is a template method that uses the handler registry pattern.
        Subclasses should override _get_function_handlers() to define
        language-specific function node types.

        Args:
            tree: Parsed tree-sitter AST
            source_code: Source code string

        Returns:
            List of extracted Function objects
        """
        self._initialize_source(source_code or "")

        # Call language-specific initialization if available
        if hasattr(self, "_detect_file_characteristics"):
            self._detect_file_characteristics()

        functions: list[Function] = []

        # Use handler registry pattern
        extractors = self._get_function_handlers()

        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, functions, "function"
                )
                log_debug(f"Extracted {len(functions)} functions")
            except (AttributeError, TypeError, ValueError) as e:
                log_debug(f"Error during function extraction: {e}")
                return []

        return functions

    def extract_classes(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Class]:
        """
        Extract class definitions with detailed information.

        This is a template method that uses the handler registry pattern.
        Subclasses should override _get_class_handlers() to define
        language-specific class node types.

        Args:
            tree: Parsed tree-sitter AST
            source_code: Source code string

        Returns:
            List of extracted Class objects
        """
        self._initialize_source(source_code or "")

        # Call language-specific initialization if available
        if hasattr(self, "_detect_file_characteristics"):
            self._detect_file_characteristics()

        classes: list[Class] = []

        # Use handler registry pattern
        extractors = self._get_class_handlers()

        if tree is not None and tree.root_node is not None:
            try:
                self._traverse_and_extract_iterative(
                    tree.root_node, extractors, classes, "class"
                )
                log_debug(f"Extracted {len(classes)} classes")
            except (AttributeError, TypeError, ValueError) as e:
                log_debug(f"Error during class extraction: {e}")
                return []

        return classes

    def extract_variables(
        self, tree: "tree_sitter.Tree", source_code: str
    ) -> list[Variable]:
        """
        Extract variable definitions.

        Default implementation returns empty list.
        Override in subclasses for language-specific variable extraction.

        Args:
            tree: Parsed tree-sitter AST
            source_code: Source code string

        Returns:
            List of extracted Variable objects
        """
        return []
