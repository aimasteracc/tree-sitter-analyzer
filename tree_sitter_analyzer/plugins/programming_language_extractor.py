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
                        self._processed_nodes.add(node_id)

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
            try:
                children_list = list(node.children)
                for child in children_list:
                    stack.append((child, depth + 1))
            except (TypeError, AttributeError):
                pass  # No children

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
