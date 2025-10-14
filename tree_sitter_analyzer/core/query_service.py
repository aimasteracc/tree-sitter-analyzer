#!/usr/bin/env python3
"""
Query Service

Unified query service for both CLI and MCP interfaces to avoid code duplication.
Provides core tree-sitter query functionality including predefined and custom queries.
"""

import logging
from typing import Any

from ..encoding_utils import read_file_safe
from ..plugins.manager import PluginManager
from ..query_loader import query_loader
from ..utils.tree_sitter_compat import TreeSitterQueryCompat, get_node_text_safe
from .parser import Parser
from .query_filter import QueryFilter

logger = logging.getLogger(__name__)


class QueryService:
    """Unified query service providing tree-sitter query functionality"""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the query service"""
        self.project_root = project_root
        self.parser = Parser()
        self.filter = QueryFilter()
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

    def execute_query(
        self,
        file_path: str,
        language: str,
        query_key: str | None = None,
        query_string: str | None = None,
        filter_expression: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """
        Execute a query

        Args:
            file_path: Path to the file to analyze
            language: Programming language
            query_key: Predefined query key (e.g., 'methods', 'class')
            query_string: Custom query string (e.g., '(method_declaration) @method')
            filter_expression: Filter expression (e.g., 'name=main', 'name=~get*,public=true')

        Returns:
            List of query results, each containing capture_name, node_type, start_line, end_line, content

        Raises:
            ValueError: If neither query_key nor query_string is provided
            FileNotFoundError: If file doesn't exist
            Exception: If query execution fails
        """
        if not query_key and not query_string:
            raise ValueError("Must provide either query_key or query_string")

        if query_key and query_string:
            raise ValueError("Cannot provide both query_key and query_string")

        try:
            # Read file content
            content, encoding = read_file_safe(file_path)

            # Parse file
            parse_result = self.parser.parse_code(content, language, file_path)
            if not parse_result or not parse_result.tree:
                raise Exception("Failed to parse file")

            tree = parse_result.tree
            language_obj = tree.language if hasattr(tree, "language") else None
            if not language_obj:
                raise Exception(f"Language object not available for {language}")

            # Get query string
            if query_key:
                query_string = query_loader.get_query(language, query_key)
                if not query_string:
                    raise ValueError(
                        f"Query '{query_key}' not found for language '{language}'"
                    )

            # Execute tree-sitter query using modern API
            try:
                captures = TreeSitterQueryCompat.safe_execute_query(
                    language_obj, query_string, tree.root_node, fallback_result=[]
                )
                
                # If captures is empty, use plugin fallback
                if not captures:
                    captures = self._execute_plugin_query(tree.root_node, query_key, language, content)
                    
            except Exception as e:
                logger.debug(f"Tree-sitter query execution failed, using plugin fallback: {e}")
                # If query creation or execution fails, use plugin fallback
                captures = self._execute_plugin_query(tree.root_node, query_key, language, content)

            # Process capture results
            results = []
            if isinstance(captures, list):
                # Handle list of tuples from modern API and plugin execution
                for capture in captures:
                    if isinstance(capture, tuple) and len(capture) == 2:
                        node, name = capture
                        results.append(self._create_result_dict(node, name))
            else:
                # If captures is not in expected format, use plugin fallback
                plugin_captures = self._execute_plugin_query(tree.root_node, query_key, language, content)
                for capture in plugin_captures:
                    if isinstance(capture, tuple) and len(capture) == 2:
                        node, name = capture
                        results.append(self._create_result_dict(node, name))

            # Apply filters
            if filter_expression and results:
                results = self.filter.filter_results(results, filter_expression)

            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def _create_result_dict(self, node: Any, capture_name: str) -> dict[str, Any]:
        """
        Create result dictionary from tree-sitter node

        Args:
            node: tree-sitter node
            capture_name: capture name

        Returns:
            Result dictionary
        """
        # Use safe text extraction
        content = get_node_text_safe(node, "")  # We don't have source_code here, so pass empty string
        
        return {
            "capture_name": capture_name,
            "node_type": node.type if hasattr(node, "type") else "unknown",
            "start_line": (
                node.start_point[0] + 1 if hasattr(node, "start_point") else 0
            ),
            "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
            "content": content,
        }

    def get_available_queries(self, language: str) -> list[str]:
        """
        Get available query keys for specified language

        Args:
            language: Programming language

        Returns:
            List of available query keys
        """
        return query_loader.list_queries(language)

    def get_query_description(self, language: str, query_key: str) -> str | None:
        """
        Get description for query key

        Args:
            language: Programming language
            query_key: Query key

        Returns:
            Query description, or None if not found
        """
        try:
            return query_loader.get_query_description(language, query_key)
        except Exception:
            return None

    def _execute_plugin_query(self, root_node: Any, query_key: str | None, language: str, source_code: str) -> list[tuple[Any, str]]:
        """
        Execute query using plugin-based dynamic dispatch
        
        Args:
            root_node: Root node of the parsed tree
            query_key: Query key to execute (can be None for custom queries)
            language: Programming language
            source_code: Source code content
            
        Returns:
            List of (node, capture_name) tuples
        """
        captures = []
        
        # Try to get plugin for the language
        plugin = self.plugin_manager.get_plugin(language)
        if not plugin:
            logger.warning(f"No plugin found for language: {language}")
            return self._fallback_query_execution(root_node, query_key)
        
        # Use plugin's execute_query_strategy method
        try:
            # Create a mock tree object for plugin compatibility
            class MockTree:
                def __init__(self, root_node):
                    self.root_node = root_node
            
            mock_tree = MockTree(root_node)
            
            # Execute plugin query strategy
            elements = plugin.execute_query_strategy(mock_tree, source_code, query_key or "function")
            
            # Convert elements to captures format
            for element in elements:
                if hasattr(element, 'start_line') and hasattr(element, 'end_line'):
                    # Create a mock node for compatibility
                    class MockNode:
                        def __init__(self, element):
                            self.type = getattr(element, 'element_type', query_key or 'unknown')
                            self.start_point = (getattr(element, 'start_line', 1) - 1, 0)
                            self.end_point = (getattr(element, 'end_line', 1) - 1, 0)
                            self.text = getattr(element, 'raw_text', '').encode('utf-8')
                    
                    mock_node = MockNode(element)
                    captures.append((mock_node, query_key or 'element'))
            
            return captures
            
        except Exception as e:
            logger.debug(f"Plugin query strategy failed: {e}")
        
        # Fallback: Use plugin's element categories for tree traversal
        try:
            element_categories = plugin.get_element_categories()
            if element_categories and query_key and query_key in element_categories:
                node_types = element_categories[query_key]
                
                def walk_tree(node):
                    """Walk the tree and find matching nodes using plugin categories"""
                    if node.type in node_types:
                        captures.append((node, query_key))
                    
                    # Recursively process children
                    for child in node.children:
                        walk_tree(child)
                
                walk_tree(root_node)
                return captures
                
        except Exception as e:
            logger.debug(f"Plugin element categories failed: {e}")
        
        # Final fallback
        return self._fallback_query_execution(root_node, query_key)
    
    def _fallback_query_execution(self, root_node: Any, query_key: str | None) -> list[tuple[Any, str]]:
        """
        Basic fallback query execution for unsupported languages
        
        Args:
            root_node: Root node of the parsed tree
            query_key: Query key to execute
            
        Returns:
            List of (node, capture_name) tuples
        """
        captures = []
        
        def walk_tree_basic(node):
            """Basic tree walking for unsupported languages"""
            # Generic node type matching
            if query_key == "function" and "function" in node.type:
                captures.append((node, "function"))
            elif query_key == "class" and "class" in node.type:
                captures.append((node, "class"))
            elif query_key == "method" and "method" in node.type:
                captures.append((node, "method"))
            elif query_key == "variable" and "variable" in node.type:
                captures.append((node, "variable"))
            elif query_key == "import" and "import" in node.type:
                captures.append((node, "import"))
            
            # Recursively process children
            for child in node.children:
                walk_tree_basic(child)
        
        walk_tree_basic(root_node)
        return captures
