"""Markup language base extractor with lightweight features.

This module provides a base class for markup language plugins (HTML, CSS, Markdown, etc.)
with simple recursive traversal and position-based tracking.
"""

from abc import ABC
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from .cached_element_extractor import CachedElementExtractor


class MarkupLanguageExtractor(CachedElementExtractor, ABC):
    """Base class for markup language plugins.

    Provides lightweight features suitable for markup languages:
    - Simple recursive node traversal
    - Position-based processing tracking
    - No heavy AST machinery or complexity calculation

    This class is designed for markup languages where:
    - Nesting depth is typically shallow
    - Position-based identification is sufficient
    - Complex traversal algorithms are unnecessary

    Attributes:
        _processed_nodes: Set of processed node positions (start_byte, end_byte).
                         Uses position-based tracking instead of object ID tracking
                         used in ProgrammingLanguageExtractor.
    """

    def __init__(self) -> None:
        """Initialize the markup language extractor.

        Sets up position-based tracking for processed nodes.
        """
        super().__init__()

        # Lightweight tracking using position-based keys
        # Unlike ProgrammingLanguageExtractor which uses object IDs (set[int]),
        # markup languages can use simpler position-based tracking
        self._processed_nodes: set[tuple[int, int]] = set()

    def _reset_caches(self) -> None:
        """Reset caches including markup-specific tracking.

        Clears both parent class caches and the position-based processed nodes set.
        """
        super()._reset_caches()
        self._processed_nodes.clear()

    def _traverse_nodes(
        self, root_node: "tree_sitter.Node"
    ) -> Iterator["tree_sitter.Node"]:
        """Simple recursive node traversal.

        Yields all nodes in the tree in depth-first order.
        Suitable for markup languages where complex traversal is not needed.

        This is simpler than ProgrammingLanguageExtractor's iterative approach
        because markup languages typically have:
        - Shallower nesting depth
        - No risk of stack overflow
        - Simpler tree structures

        Args:
            root_node: Root node to start traversal from.

        Yields:
            Tree-sitter nodes in depth-first search order.

        Example:
            >>> for node in extractor._traverse_nodes(root):
            ...     process_node(node)
        """
        # Yield current node first (pre-order traversal)
        yield root_node

        # Recursively traverse children if they exist
        if hasattr(root_node, "children"):
            for child in root_node.children:
                # Recursive call - safe for markup languages with shallow nesting
                yield from self._traverse_nodes(child)

    def _is_node_processed(self, node: "tree_sitter.Node") -> bool:
        """Check if node has been processed using position-based tracking.

        Args:
            node: Tree-sitter node to check.

        Returns:
            True if the node at this position has been processed, False otherwise.

        Note:
            Uses (start_byte, end_byte) as the key, which is sufficient for
            markup languages where multiple elements at the same position
            are not expected.
        """
        node_key = (node.start_byte, node.end_byte)
        return node_key in self._processed_nodes

    def _mark_node_processed(self, node: "tree_sitter.Node") -> None:
        """Mark node as processed using position-based tracking.

        Args:
            node: Tree-sitter node to mark as processed.

        Note:
            Stores the position (start_byte, end_byte) rather than object ID,
            which is more memory-efficient and sufficient for markup languages.
        """
        node_key = (node.start_byte, node.end_byte)
        self._processed_nodes.add(node_key)
