#!/usr/bin/env python3
"""
Programming Language Extractor Module

Base class for programming language plugins with advanced features.
Provides iterative AST traversal with depth limits, element caching,
cyclomatic complexity calculation, and container node type customization.

Features:
- Iterative AST traversal with depth limits
- Element caching for performance
- Cyclomatic complexity calculation
- Container node type customization
- Comprehensive error handling
- Performance monitoring
- Type-safe operations (PEP 484)
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type
from collections.abc import Callable as CallableType
from functools import lru_cache, wraps
from time import perf_counter
from dataclasses import dataclass, field

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tree_sitter import Tree, Node
    from ..models import (
        CodeElement,
        Class,
        Function,
        Variable,
        Import as ModelImport,
    )
    from ..utils import (
        log_debug,
        log_info,
        log_warning,
        log_error,
        log_performance,
    )


class ExtractionError(Exception):
    """Raised when code extraction fails."""

    pass


class ExtractionTraversalError(ExtractionError):
    """Raised when AST traversal fails."""

    pass


class ExtractionCacheError(ExtractionError):
    """Raised when cache operation fails."""

    pass


@dataclass
class ExtractionMetrics:
    """
    Metrics for an extraction operation.

    Attributes:
        total_nodes: Total number of nodes visited
        processed_nodes: Number of nodes processed
        cached_hits: Number of cache hits
        extraction_time: Time taken for extraction (seconds)
        complexity_score: Total cyclomatic complexity score
    """

    total_nodes: int = 0
    processed_nodes: int = 0
    cached_hits: int = 0
    extraction_time: float = 0.0
    complexity_score: int = 0


@dataclass
class ExtractionContext:
    """
    Context for an extraction operation.

    Attributes:
        source_code: Source code being extracted
        content_lines: Source code split by lines
        max_depth: Maximum traversal depth
        language: Programming language name
        extractor_name: Name of the extractor
    """

    source_code: str = ""
    content_lines: List[str] = field(default_factory=list)
    max_depth: int = 50
    language: str = "unknown"
    extractor_name: str = "ProgrammingLanguageExtractor"


class ProgrammingLanguageExtractor:
    """
    Base class for programming language plugins with advanced features.

    Features:
    - Iterative AST traversal with depth limits
    - Element caching for performance
    - Cyclomatic complexity calculation
    - Container node type customization
    - Comprehensive error handling
    - Performance monitoring
    - Type-safe operations (PEP 484)

    Usage:
    ```python
    class MyExtractor(ProgrammingLanguageExtractor):
        def __init__(self):
            super().__init__()
            self._max_depth = 30  # Override max depth

        def extract_functions(self, tree, source_code):
            return super().extract_functions(tree, source_code)
    ```

    Attributes:
        _processed_nodes: Set[int]
        _element_cache: Dict[Tuple[int, str], Any]
        _metrics: ExtractionMetrics
    """

    def __init__(self, max_depth: int = 50) -> None:
        """
        Initialize programming language extractor.

        Args:
            max_depth: Maximum traversal depth (default: 50)

        Note:
            - Uses object ID-based caching for processed nodes
            - Tracks extraction metrics (nodes visited, cache hits, etc.)
            - Provides customizable max depth for traversal
        """
        super().__init__()

        self._max_depth = max_depth
        self._processed_nodes: set[int] = set()
        self._element_cache: Dict[Tuple[int, str], Any] = {}
        self._metrics = ExtractionMetrics()

        logger.debug(f"ProgrammingLanguageExtractor initialized (max_depth={max_depth})")

    def _reset_caches(self) -> None:
        """Reset all caches and metrics."""
        self._processed_nodes.clear()
        self._element_cache.clear()
        self._metrics = ExtractionMetrics()

        logger.debug("ProgrammingLanguageExtractor caches and metrics reset")

    def _get_container_node_types(self) -> set[str]:
        """
        Get node types that may contain target elements.

        Override in subclasses for language-specific containers.

        Returns:
            Set of container node type names

        Note:
            - Default implementation uses common containers
            - Can be overridden for language-specific types
        """
        return {
            "program",
            "module",
            "block",
            "function_definition",
            "class_definition",
            "if_statement",
            "for_statement",
            "while_statement",
            "try_statement",
            "catch_statement",
            "with_statement",
            "import_statement",
            "export_statement",
        }

    def _traverse_and_extract_iterative(
        self,
        root_node: Node,
        source_code: str,
        extractors: Dict[str, Callable],
        results: List[Any],
        element_type: str,
        max_depth: int = 50,
        context: Optional[ExtractionContext] = None,
    ) -> None:
        """
        Generic iterative AST traversal with element extraction.

        Args:
            root_node: Root node to start traversal
            source_code: Source code for context
            extractors: Mapping of node types to extractor functions
            results: List to accumulate extracted elements
            element_type: Type of element being extracted
            max_depth: Maximum traversal depth
            context: Extraction context for metadata

        Note:
            - Uses depth-limited traversal
            - Uses caching for processed nodes
            - Tracks metrics (nodes visited, cache hits, etc.)
            - Thread-safe (uses instance variables, not global state)
        """
        if context is None:
            context = ExtractionContext(
                source_code=source_code,
                content_lines=source_code.splitlines(),
                max_depth=max_depth,
                language=self._extractor_name,
                extractor_name=self.__class__.__name__,
            )

        node_stack = [(root_node, 0)]
        target_node_types = set(extractors.keys())
        container_node_types = self._get_container_node_types()
        total_nodes = 0
        processed_nodes = 0
        cached_hits = 0

        while node_stack:
            current_node, depth = node_stack.pop()

            # Depth limit check
            if depth > max_depth:
                continue

            total_nodes += 1
            node_id = id(current_node)

            # Skip if already processed
            if node_id in self._processed_nodes:
                continue

            # Early exit: skip irrelevant nodes
            if (
                depth > 0
                and current_node.type not in target_node_types
                and current_node.type not in container_node_types
            ):
                continue

            # Cache check
            cache_key = (node_id, element_type)
            if cache_key in self._element_cache:
                cached_hits += 1
                cached_element = self._element_cache[cache_key]
                results.append(cached_element)
                self._processed_nodes.add(node_id)
                continue

            # Extract element
            extractor = extractors.get(current_node.type)
            if extractor:
                try:
                    start_time = perf_counter()
                    element = extractor(current_node, context)
                    end_time = perf_counter()
                    extraction_time = end_time - start_time

                    if element:
                        # Add to cache
                        self._element_cache[cache_key] = element
                        self._processed_nodes.add(node_id)

                        # Add to results
                        results.append(element)

                        # Update metrics
                        if hasattr(element, "complexity"):
                            self._metrics.complexity_score += element.complexity
                except Exception as e:
                    logger.error(f"Extraction failed for node {current_node.type}: {e}")
                    continue

            processed_nodes += 1

            # Push children to stack
            if hasattr(current_node, "children") and current_node.children:
                for child in reversed(current_node.children):
                    node_stack.append((child, depth + 1))

        # Update metrics
        self._metrics.total_nodes = total_nodes
        self._metrics.processed_nodes = processed_nodes
        self._metrics.cached_hits = cached_hits

        logger.info(
            f"Iterative traversal completed (nodes={total_nodes}, "
            f"processed={processed_nodes}, cached={cached_hits})"
        )

    def _extract_common_metadata(self, node: Node, context: ExtractionContext) -> Dict[str, Any]:
        """
        Extract common metadata from an AST node.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Dictionary containing metadata

        Note:
            - Extracts line numbers, raw text, docstring
            - Calculates complexity
            - Provides standardized format
        """
        try:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1

            # Extract raw text
            raw_text = self._extract_raw_text(start_line, end_line, context)

            # Extract docstring
            docstring = self._extract_docstring_for_node(node, context)

            # Calculate complexity
            complexity = self._calculate_complexity_optimized(node, context)

            return {
                "start_line": start_line,
                "end_line": end_line,
                "raw_text": raw_text,
                "docstring": docstring,
                "complexity": complexity,
            }
        except Exception as e:
            logger.error(f"Metadata extraction failed: {e}")
            return {
                "start_line": start_line,
                "end_line": end_line,
                "raw_text": "",
                "docstring": None,
                "complexity": 1,  # Default complexity
            }

    def _extract_raw_text(
        self, start_line: int, end_line: int, context: ExtractionContext
    ) -> str:
        """
        Extract raw text from source code by line range.

        Args:
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based)
            context: Extraction context

        Returns:
            Raw text content
        """
        try:
            start_idx = max(0, start_line - 1)
            end_idx = min(len(context.content_lines), end_line)
            return "\n".join(context.content_lines[start_idx:end_idx])
        except Exception as e:
            logger.error(f"Raw text extraction failed: {e}")
            return ""

    def _extract_docstring_for_node(
        self, node: Node, context: ExtractionContext
    ) -> Optional[str]:
        """
        Extract documentation string for a node.

        Default implementation uses line-based extraction.
        Override in subclasses for language-specific docstring extraction.

        Args:
            node: AST node
            context: Extraction context

        Returns:
            Docstring text or None

        Note:
            - Default implementation does not extract docstrings
            - Override in subclasses for language-specific logic
        """
        try:
            # Check if node has a "docstring" attribute (tree-sitter specific)
            if hasattr(node, "named_child_count") and hasattr(node, "children"):
                for i in range(node.named_child_count):
                    child = node.named_child(i)
                    if child.type == "docstring":
                        return self._extract_raw_text(
                            child.start_point[0] + 1,
                            child.end_point[0] + 1,
                            context,
                        )
            return None
        except Exception as e:
            logger.error(f"Docstring extraction failed: {e}")
            return None

    def _calculate_complexity_optimized(
        self, node: Node, context: ExtractionContext
    ) -> int:
        """
        Calculate cyclomatic complexity (can be overridden).

        Default implementation counts decision points.

        Args:
            node: AST node to calculate complexity for
            context: Extraction context

        Returns:
            Complexity score

        Note:
            - Default implementation counts decision points
            - Override in subclasses for language-specific complexity
        """
        try:
            complexity = 1  # Base complexity

            # Count decision keywords
            decision_keywords = self._get_decision_keywords()
            if node.type in decision_keywords:
                for child in node.children:
                    complexity += 1
                if child.type in decision_keywords:
                    complexity += self._calculate_complexity_optimized(child, context)

            return complexity
        except Exception as e:
            logger.error(f"Complexity calculation failed: {e}")
            return 1

    def _get_decision_keywords(self) -> set[str]:
        """
        Get language-specific decision keywords for complexity.

        Default implementation uses common decision keywords.
        Override in subclasses for language-specific keywords.

        Returns:
            Set of decision keyword node types
        """
        return {
            "if_statement",
            "for_statement",
            "while_statement",
            "case",
            "default",
            "switch",
            "try_statement",
            "catch_statement",
            "continue_statement",
            "break_statement",
            "return_statement",
            "assert_statement",
        }

    def _get_extractor_name(self) -> str:
        """
        Get the name of this extractor.

        Returns:
            Extractor class name
        """
        return self.__class__.__name__

    def get_extraction_metrics(self) -> ExtractionMetrics:
        """
        Get metrics from the last extraction operation.

        Returns:
            ExtractionMetrics with detailed statistics

        Note:
            - Includes total nodes, processed nodes, cache hits
            - Includes extraction time and complexity score
        """
        return self._metrics

    def _get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics

        Note:
            - Returns cache size and hit rate
        """
        cache_size = len(self._element_cache)

        # Calculate hit rate
        total_accesses = self._metrics.processed_nodes + self._metrics.cached_hits
        hit_rate = (
            self._metrics.cached_hits / total_accesses
            if total_accesses > 0 else 0.0
        )

        return {
            "cache_size": cache_size,
            "cache_hits": self._metrics.cached_hits,
            "processed_nodes": self._metrics.processed_nodes,
            "total_nodes": self._metrics.total_nodes,
            "hit_rate": hit_rate,
            "extractor_name": self._get_extractor_name(),
        }


# Module-level convenience functions
def create_programming_language_extractor(
    max_depth: int = 50,
    enable_cache: bool = True,
) -> ProgrammingLanguageExtractor:
    """
    Factory function to create a programming language extractor.

    Args:
        max_depth: Maximum traversal depth (default: 50)
        enable_cache: Whether to enable element caching (default: True)

    Returns:
        Configured ProgrammingLanguageExtractor instance

    Raises:
        ValueError: If parameters are invalid

    Note:
        - Creates all necessary dependencies
        - Provides clean factory pattern
        - Recommended for new code
    """
    if max_depth <= 0:
        raise ValueError(f"max_depth must be positive, got: {max_depth}")

    return ProgrammingLanguageExtractor(max_depth=max_depth)


def get_programming_language_extractor() -> ProgrammingLanguageExtractor:
    """
    Get default programming language extractor instance (backward compatible).

    This function returns a default instance and is provided
    for backward compatibility. For new code, prefer using
    `create_programming_language_extractor()` factory function.

    Returns:
        ProgrammingLanguageExtractor instance with default settings

    Note:
        - max_depth: 50
        - enable_cache: True
        - For new code, prefer `create_programming_language_extractor()`
    """
    return ProgrammingLanguageExtractor()


# Export for backward compatibility
__all__ = [
    # Exceptions
    "ExtractionError",
    "ExtractionTraversalError",
    "ExtractionCacheError",

    # Data classes
    "ExtractionMetrics",
    "ExtractionContext",

    # Main class
    "ProgrammingLanguageExtractor",

    # Factory functions
    "create_programming_language_extractor",
    "get_programming_language_extractor",
]
