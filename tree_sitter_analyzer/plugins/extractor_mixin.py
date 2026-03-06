#!/usr/bin/env python3
"""
Extractor Mixin Classes

Provides reusable functionality for language element extractors.
These mixins eliminate code duplication across language plugins.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    import tree_sitter

from ..encoding_utils import extract_text_slice, safe_encode
from ..utils import log_debug, log_error, log_warning

logger = logging.getLogger(__name__)


class CacheManagementMixin:
    """
    Mixin providing cache management functionality for element extractors.
    
    Provides standardized caching for node text, processed nodes, and extracted elements
    to optimize performance during AST traversal.
    """
    
    def _init_caches(self) -> None:
        """Initialize performance optimization caches."""
        # Cache node text to avoid repeated extraction
        if not hasattr(self, '_node_text_cache'):
            self._node_text_cache: Dict[Tuple[int, int], str] = {}
        # Track processed nodes to avoid duplicate processing
        if not hasattr(self, '_processed_nodes'):
            self._processed_nodes: Set[int] = set()
        # Cache extracted elements by node and type
        if not hasattr(self, '_element_cache'):
            self._element_cache: Dict[Tuple[int, str], Any] = {}
        # File encoding for safe text extraction
        if not hasattr(self, '_file_encoding'):
            self._file_encoding: Optional[str] = None
    
    def _reset_caches(self) -> None:
        """Reset all performance caches."""
        if hasattr(self, '_node_text_cache'):
            self._node_text_cache.clear()
        if hasattr(self, '_processed_nodes'):
            self._processed_nodes.clear()
        if hasattr(self, '_element_cache'):
            self._element_cache.clear()
        
        # Reset language-specific caches if they exist
        if hasattr(self, '_annotation_cache'):
            self._annotation_cache.clear()
        if hasattr(self, '_signature_cache'):
            self._signature_cache.clear()
        if hasattr(self, '_docstring_cache'):
            self._docstring_cache.clear()
        if hasattr(self, '_complexity_cache'):
            self._complexity_cache.clear()
        
        # Reset extracted elements lists
        if hasattr(self, 'annotations'):
            self.annotations.clear()
        if hasattr(self, 'current_package'):
            self.current_package = ""


class NodeTraversalMixin:
    """
    Mixin providing AST traversal functionality.
    
    Implements optimized iterative tree traversal with caching and batch processing
    for efficient element extraction.
    """
    
    def _traverse_and_extract_iterative(
        self,
        root_node: "tree_sitter.Node",
        extractors: Dict[str, Any],
        results: List[Any],
        element_type: str,
        container_node_types: Optional[Set[str]] = None,
    ) -> None:
        """
        Iterative node traversal and extraction with batch processing.
        
        Args:
            root_node: Root node of the AST
            extractors: Dictionary mapping node types to extractor functions
            results: List to append extracted results to
            element_type: Type of element being extracted (for logging)
            container_node_types: Set of node types that may contain target nodes
        """
        if not root_node:
            return
        
        # Ensure caches are initialized
        if not hasattr(self, '_processed_nodes'):
            self._init_caches()
        
        # Target node types for extraction
        target_node_types = set(extractors.keys())
        
        # Default container node types
        if container_node_types is None:
            container_node_types = {
                "program",
                "class_body",
                "interface_body",
                "enum_body",
                "module",
                "block",
            }
        
        # Iterative DFS stack: (node, depth)
        node_stack = [(root_node, 0)]
        processed_nodes = 0
        max_depth = 50  # Prevent infinite loops
        
        # Batch processing containers
        field_batch = []
        
        while node_stack:
            current_node, depth = node_stack.pop()
            
            # Safety check for maximum depth
            if depth > max_depth:
                log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
                continue
            
            processed_nodes += 1
            node_type = current_node.type
            
            # Early termination: skip nodes that don't contain target elements
            if (
                depth > 0
                and node_type not in target_node_types
                and node_type not in container_node_types
            ):
                continue
            
            # Collect target nodes for batch processing
            if node_type in target_node_types:
                if element_type == "field" and node_type == "field_declaration":
                    field_batch.append(current_node)
                else:
                    # Process non-field elements immediately
                    node_id = id(current_node)
                    
                    # Skip if already processed
                    if node_id in self._processed_nodes:
                        continue
                    
                    # Check element cache first
                    cache_key = (node_id, element_type)
                    if cache_key in self._element_cache:
                        element = self._element_cache[cache_key]
                        if element:
                            if isinstance(element, list):
                                results.extend(element)
                            else:
                                results.append(element)
                        self._processed_nodes.add(node_id)
                        continue
                    
                    # Extract and cache
                    extractor = extractors.get(node_type)
                    if extractor:
                        element = extractor(current_node)
                        if element:
                            if isinstance(element, list):
                                results.extend(element)
                            else:
                                results.append(element)
                        self._processed_nodes.add(node_id)
            
            # Add children to stack (reversed for correct DFS traversal)
            if current_node.children:
                for child in reversed(current_node.children):
                    node_stack.append((child, depth + 1))
            
            # Process field batch when it reaches optimal size
            if len(field_batch) >= 10:
                if hasattr(self, '_process_field_batch'):
                    self._process_field_batch(field_batch, extractors, results)
                field_batch.clear()
        
        # Process remaining field batch
        if field_batch and hasattr(self, '_process_field_batch'):
            self._process_field_batch(field_batch, extractors, results)
        
        log_debug(f"Iterative traversal processed {processed_nodes} nodes")


class NodeTextExtractionMixin:
    """
    Mixin providing optimized node text extraction with caching.
    """
    
    def _get_node_text_optimized(self, node: "tree_sitter.Node") -> str:
        """
        Get node text with optimized caching using position-based keys.
        
        Args:
            node: Tree-sitter node to extract text from
            
        Returns:
            Extracted text content of the node
        """
        # Ensure caches are initialized
        if not hasattr(self, '_node_text_cache'):
            self._init_caches()
        
        # Use position-based cache key for deterministic behavior
        cache_key = (node.start_byte, node.end_byte)
        
        # Check cache first
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]
        
        try:
            # Use encoding utilities for text extraction
            start_byte = node.start_byte
            end_byte = node.end_byte
            
            # Boundary checks: return empty string for invalid positions
            if start_byte < 0 or end_byte < 0:
                return ""
            
            encoding = self._file_encoding or "utf-8"
            content_lines = getattr(self, 'content_lines', [])
            content_bytes = safe_encode("\n".join(content_lines), encoding)
            
            # Check if end_byte is within bounds
            if end_byte > len(content_bytes):
                return ""
            
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)
            
            self._node_text_cache[cache_key] = text
            return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")
            # Fallback to simple text extraction
            return self._fallback_text_extraction(node)
    
    def _fallback_text_extraction(self, node: "tree_sitter.Node") -> str:
        """
        Fallback text extraction when optimized method fails.
        
        Args:
            node: Tree-sitter node to extract text from
            
        Returns:
            Extracted text content using line-based extraction
        """
        try:
            start_point = node.start_point
            end_point = node.end_point
            content_lines = getattr(self, 'content_lines', [])
            
            if start_point[0] == end_point[0]:
                # Single line
                line = content_lines[start_point[0]]
                result: str = line[start_point[1] : end_point[1]]
                return result
            else:
                # Multiple lines
                lines = []
                for i in range(start_point[0], end_point[0] + 1):
                    if i < len(content_lines):
                        line = content_lines[i]
                        if i == start_point[0]:
                            lines.append(line[start_point[1] :])
                        elif i == end_point[0]:
                            lines.append(line[: end_point[1]])
                        else:
                            lines.append(line)
                return "\n".join(lines)
        except Exception as fallback_error:
            log_error(f"Fallback text extraction also failed: {fallback_error}")
            return ""


class ElementExtractorBase(
    CacheManagementMixin, NodeTraversalMixin, NodeTextExtractionMixin
):
    """
    Comprehensive base class for element extractors.
    
    Combines cache management, node traversal, and text extraction functionality
    into a single base class that language-specific extractors can inherit from.
    
    Usage:
        class JavaElementExtractor(ElementExtractorBase):
            def extract_functions(self, tree, source_code):
                # Implementation using inherited methods
                self._reset_caches()
                self._traverse_and_extract_iterative(...)
    """
    
    def __init__(self) -> None:
        """Initialize the element extractor with caches."""
        self._init_caches()
        self.source_code: str = ""
        self.content_lines: List[str] = []
    
    def _init_caches(self) -> None:
        """Initialize all caches and state."""
        super()._init_caches()
        if not hasattr(self, 'source_code'):
            self.source_code = ""
        if not hasattr(self, 'content_lines'):
            self.content_lines = []
    
    # Type annotations for methods that language extractors must implement
    # These are abstract in ElementExtractor but we provide default implementations
    # here for ElementExtractorBase so mypy can recognize them
    def extract_functions(
        self, tree: Any, source_code: str
    ) -> list[Any]:
        """Extract function definitions. Must be implemented by subclasses."""
        return []
    
    def extract_classes(
        self, tree: Any, source_code: str
    ) -> list[Any]:
        """Extract class definitions. Must be implemented by subclasses."""
        return []
    
    def extract_variables(
        self, tree: Any, source_code: str
    ) -> list[Any]:
        """Extract variable declarations. Must be implemented by subclasses."""
        return []
    
    def extract_imports(
        self, tree: Any, source_code: str
    ) -> list[Any]:
        """Extract import statements. Must be implemented by subclasses."""
        return []
