#!/usr/bin/env python3
"""
Markup Language Extractor Module

Base class for markup language plugins (HTML, CSS, Markdown, etc.)
with lightweight features and position-based node tracking.

Features:
- Simple recursive node traversal
- Position-based node tracking (memory efficient)
- Shallow nesting depth support
- Comprehensive error handling
- Type-safe operations (PEP 484)
- Performance monitoring
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type, Iterator
from abc import ABC
from time import perf_counter

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tree_sitter import Tree, Node
    from ..models import Class as ModelClass
    from ..utils import log_debug, log_info, log_warning, log_error, log_performance
    from .cached_element_extractor import CachedElementExtractor


class MarkupExtractionError(Exception):
    """Base exception for markup extraction errors."""

    pass


class MarkupTraversalError(MarkupExtractionError):
    """Raised when node traversal fails."""

    pass


class MarkupExtractionWarning(MarkupExtractionError):
    """Raised when extraction encounters potential issues."""

    pass


class MarkupLanguageExtractor(CachedElementExtractor, ABC):
    """
    Base class for markup language plugins with lightweight features.

    Provides lightweight features suitable for markup languages:
    - Simple recursive node traversal
    - Position-based node tracking (memory efficient)
    - Shallow nesting depth support
    - No heavy AST machinery or complexity calculation

    This class is designed for markup languages where:
    - Nesting depth is typically shallow
    - Position-based identification is sufficient
    - Complex traversal algorithms are unnecessary

    Attributes:
        _processed_nodes: Set of processed node positions (start_byte, end_byte)

    Usage:
    ```python
    class MyMarkupExtractor(MarkupLanguageExtractor):
        def extract_classes(self, tree, source_code):
            # Implementation
            return classes
    ```

    """

    def __init__(self) -> None:
        """
        Initialize markup language extractor.

        Note:
            - Sets up position-based node tracking
            - Uses lightweight design suitable for markup languages
            - Inherits caching from CachedElementExtractor
        """
        super().__init__()

        # Position-based node tracking (lightweight, memory efficient)
        # Uses (start_byte, end_byte) as key instead of object ID
        # Sufficient for markup languages where multiple elements at same position
        # are not expected
        self._processed_nodes: set[tuple[int, int]] = set()

    def _reset_caches(self) -> None:
        """
        Reset all caches including markup-specific tracking.

        Note:
            - Clears parent class caches (elements, cache)
            - Clears position-based processed nodes
        """
        super()._reset_caches()
        self._processed_nodes.clear()

    def _traverse_nodes(self, root_node: Optional[Node]) -> Iterator[Node]:
        """
        Simple recursive node traversal (depth-first pre-order).

        Yields all nodes in the tree in depth-first order.
        Suitable for markup languages where complex traversal is not needed.

        Args:
            root_node: Root node to start traversal from.

        Yields:
            Tree-sitter nodes in depth-first search order.

        Note:
            - This is simpler than the iterative approach used in
              ProgrammingLanguageExtractor
            - Uses recursion which is safe for markup languages
              with their typical shallow nesting depth
            - Yields nodes in pre-order (parent before children)

        Example:
            >>> for node in extractor._traverse_nodes(root):
            ...     process_node(node)
        """
        if not root_node:
            return

        # Yield current node first (pre-order traversal)
        yield root_node

        # Recursively traverse children if they exist
        if hasattr(root_node, "children"):
            for child in root_node.children:
                yield from self._traverse_nodes(child)

    def _is_node_processed(self, node: Node) -> bool:
        """
        Check if node has been processed using position-based tracking.

        Args:
            node: Tree-sitter node to check

        Returns:
            True if node at this position has been processed, False otherwise

        Note:
            - Uses (start_byte, end_byte) as tracking key
            - Position-based tracking is sufficient for markup languages
            - More memory-efficient than object ID tracking
        """
        node_key = (node.start_byte, node.end_byte)
        return node_key in self._processed_nodes

    def _mark_node_processed(self, node: Node) -> None:
        """
        Mark node as processed using position-based tracking.

        Args:
            node: Tree-sitter node to mark as processed

        Note:
            - Adds (start_byte, end_byte) to processed set
            - Position-based tracking is memory-efficient
            - Prevents reprocessing of same node
        """
        node_key = (node.start_byte, node.end_byte)
        self._processed_nodes.add(node_key)

    def _extract_common_metadata(self, node: Node, source_code: str) -> Dict[str, Any]:
        """
        Extract common metadata from an AST node.

        Provides a standardized way to extract basic information
        that is common across all element types (functions, classes, etc.).

        Args:
            node: AST node to extract metadata from
            source_code: Source code for context

        Returns:
            Dictionary containing line numbers, raw text, etc.

        Note:
            - Extracts line numbers (1-based)
            - Extracts raw text from source code
            - Adds node type information
        """
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Extract raw text
        if source_code:
            lines = source_code.splitlines()
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            raw_text = "\n".join(lines[start_idx:end_idx])
        else:
            raw_text = ""

        return {
            "start_line": start_line,
            "end_line": end_line,
            "raw_text": raw_text,
            "node_type": node.type,
            "start_byte": node.start_byte,
            "end_byte": node.end_byte,
        }

    # --- Template Method Pattern ---

    def _get_function_handlers(self) -> Dict[str, Callable]:
        """
        Get mapping of node types to function extraction handlers.

        Override in subclasses to define language-specific function node types.

        Default implementation returns empty dict (markup languages typically
        don't have function definitions).

        Returns:
            Dictionary mapping node type names to handler methods

        Note:
            - Default implementation returns empty dict
            - Override for languages that have functions (JS in HTML, etc.)
        """
        return {}

    def _get_class_handlers(self) -> Dict[str, Callable]:
        """
        Get mapping of node types to class extraction handlers.

        Override in subclasses to define language-specific class node types.

        Default implementation returns empty dict (markup languages typically
        don't have class definitions in the traditional sense).

        Returns:
            Dictionary mapping node type names to handler methods

        Note:
            - Default implementation returns empty dict
            - Override for languages that have classes (HTML divs, etc.)
        """
        return {}

    def _get_variable_handlers(self) -> Dict[str, Callable]:
        """
        Get mapping of node types to variable extraction handlers.

        Override in subclasses to define language-specific variable node types.

        Default implementation returns empty dict (variables are not typically
        declared in markup languages).

        Returns:
            Dictionary mapping node type names to handler methods

        Note:
            - Default implementation returns empty dict
            - Override for languages that have variable declarations (CSS vars, etc.)
        """
        return {}

    def _get_import_handlers(self) -> Dict[str, Callable]:
        """
        Get mapping of node types to import extraction handlers.

        Override in subclasses to define language-specific import node types.

        Default implementation returns empty dict (imports are not typically
        explicit in markup languages, except for style imports).

        Returns:
            Dictionary mapping node type names to handler methods

        Note:
            - Default implementation returns empty dict
            - Override for languages that have explicit imports (CSS @import, etc.)
        """
        return {}

    # --- Common Extraction Methods (Template Method Pattern) ---

    def extract_functions(
        self, tree: Tree, source_code: str
    ) -> List[Any]:
        """
        Extract function definitions using template method pattern.

        Default implementation returns empty list (markup languages
        typically don't have function definitions in the traditional sense).

        Override in subclasses for languages that have functions (JS in HTML, etc.).

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code string

        Returns:
            List of extracted Function objects

        Raises:
            MarkupExtractionError: If extraction fails

        Note:
            - Default implementation returns empty list
            - Override for languages that have function definitions
            - Uses handler registry pattern defined in _get_function_handlers
        """
        self._initialize_source(source_code or "")

        functions = []
        handlers = self._get_function_handlers()

        if tree is not None and tree.root_node is not None:
            try:
                for node in self._traverse_nodes(tree.root_node):
                    # Skip if already processed
                    if self._is_node_processed(node):
                        continue

                    # Check for function handler
                    handler = handlers.get(node.type)
                    if handler:
                        try:
                            start_time = perf_counter()
                            function = handler(node, source_code)
                            end_time = perf_counter()
                            extraction_time = end_time - start_time

                            if function:
                                functions.append(function)
                                log_performance(
                                    f"Function extraction time: {extraction_time:.3f}s, "
                                    f"node_type={node.type}"
                                )
                        except Exception as e:
                            log_error(
                                f"Failed to extract function from node {node.type}: {e}"
                            )
                    else:
                        # Not a function node, mark as processed
                        self._mark_node_processed(node)

            except Exception as e:
                log_error(f"Function extraction failed: {e}")

        log_debug(f"Extracted {len(functions)} functions")
        return functions

    def extract_classes(
        self, tree: Tree, source_code: str
    ) -> List[ModelClass]:
        """
        Extract class definitions using template method pattern.

        Default implementation returns empty list (markup languages
        typically don't have class definitions in the traditional sense).

        Override in subclasses for languages that have classes (HTML divs, etc.).

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code string

        Returns:
            List of extracted Class objects

        Raises:
            MarkupExtractionError: If extraction fails

        Note:
            - Default implementation returns empty list
            - Override for languages that have class definitions
            - Uses handler registry pattern defined in _get_class_handlers
        """
        self._initialize_source(source_code or "")

        classes = []
        handlers = self._get_class_handlers()

        if tree is not None and tree.root_node is not None:
            try:
                for node in self._traverse_nodes(tree.root_node):
                    # Skip if already processed
                    if self._is_node_processed(node):
                        continue

                    # Check for class handler
                    handler = handlers.get(node.type)
                    if handler:
                        try:
                            start_time = perf_counter()
                            cls = handler(node, source_code)
                            end_time = perf_counter()
                            extraction_time = end_time - start_time

                            if cls:
                                classes.append(cls)
                                log_performance(
                                    f"Class extraction time: {extraction_time:.3f}s, "
                                    f"node_type={node.type}"
                                )
                        except Exception as e:
                            log_error(
                                f"Failed to extract class from node {node.type}: {e}"
                            )
                    else:
                        # Not a class node, mark as processed
                        self._mark_node_processed(node)

            except Exception as e:
                log_error(f"Class extraction failed: {e}")

        log_debug(f"Extracted {len(classes)} classes")
        return classes

    def extract_variables(
        self, tree: Tree, source_code: str
    ) -> List[Any]:
        """
        Extract variable definitions using template method pattern.

        Default implementation returns empty list (variables are not typically
        declared in markup languages).

        Override in subclasses for languages that have variable declarations
        (CSS variables, LESS variables, etc.).

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code string

        Returns:
            List of extracted Variable objects

        Raises:
            MarkupExtractionError: If extraction fails

        Note:
            - Default implementation returns empty list
            - Override for languages that have variable declarations
            - Uses handler registry pattern defined in _get_variable_handlers
        """
        self._initialize_source(source_code or "")

        variables = []
        handlers = self._get_variable_handlers()

        if tree is not None and tree.root_node is not None:
            try:
                for node in self._traverse_nodes(tree.root_node):
                    # Skip if already processed
                    if self._is_node_processed(node):
                        continue

                    # Check for variable handler
                    handler = handlers.get(node.type)
                    if handler:
                        try:
                            start_time = perf_counter()
                            variable = handler(node, source_code)
                            end_time = perf_counter()
                            extraction_time = end_time - start_time

                            if variable:
                                variables.append(variable)
                                log_performance(
                                    f"Variable extraction time: {extraction_time:.3f}s, "
                                    f"node_type={node.type}"
                                )
                        except Exception as e:
                            log_error(
                                f"Failed to extract variable from node {node.type}: {e}"
                            )
                    else:
                        # Not a variable node, mark as processed
                        self._mark_node_processed(node)

            except Exception as e:
                log_error(f"Variable extraction failed: {e}")

        log_debug(f"Extracted {len(variables)} variables")
        return variables

    def extract_imports(
        self, tree: Tree, source_code: str
    ) -> List[Any]:
        """
        Extract import statements using template method pattern.

        Default implementation returns empty list (imports are not typically
        explicit in markup languages, except for style imports).

        Override in subclasses for languages that have explicit imports
        (CSS @import, JavaScript import, etc.).

        Args:
            tree: Tree-sitter syntax tree
            source_code: Source code string

        Returns:
            List of extracted Import objects

        Raises:
            MarkupExtractionError: If extraction fails

        Note:
            - Default implementation returns empty list
            - Override for languages that have explicit import statements
            - Uses handler registry pattern defined in _get_import_handlers
        """
        self._initialize_source(source_code or "")

        imports = []
        handlers = self._get_import_handlers()

        if tree is not None and tree.root_node is not None:
            try:
                for node in self._traverse_nodes(tree.root_node):
                    # Skip if already processed
                    if self._is_node_processed(node):
                        continue

                    # Check for import handler
                    handler = handlers.get(node.type)
                    if handler:
                        try:
                            start_time = perf_counter()
                            imp = handler(node, source_code)
                            end_time = perf_counter()
                            extraction_time = end_time - start_time

                            if imp:
                                imports.append(imp)
                                log_performance(
                                    f"Import extraction time: {extraction_time:.3f}s, "
                                    f"node_type={node.type}"
                                )
                        except Exception as e:
                            log_error(
                                f"Failed to extract import from node {node.type}: {e}"
                            )
                    else:
                        # Not an import node, mark as processed
                        self._mark_node_processed(node)

            except Exception as e:
                log_error(f"Import extraction failed: {e}")

        log_debug(f"Extracted {len(imports)} imports")
        return imports


# Module-level convenience functions
def create_markup_language_extractor() -> MarkupLanguageExtractor:
    """
    Factory function to create a markup language extractor instance.

    This function creates a new MarkupLanguageExtractor instance
    with lightweight features and position-based node tracking.

    Args:
        None

    Returns:
        Configured MarkupLanguageExtractor instance

    Raises:
        None

    Note:
        - Lightweight design suitable for markup languages
        - Position-based node tracking
        - Simple recursive traversal
        - Recommended for HTML, CSS, Markdown extractors

    Example:
    ```python
    extractor = create_markup_language_extractor()

    classes = extractor.extract_classes(tree, source_code)
    functions = extractor.extract_functions(tree, source_code)
    ```
    """
    return MarkupLanguageExtractor()


# Export for convenience
__all__ = [
    # Exceptions
    "MarkupExtractionError",
    "MarkupTraversalError",
    "MarkupExtractionWarning",

    # Main class
    "MarkupLanguageExtractor",

    # Factory functions
    "create_markup_language_extractor",
]
