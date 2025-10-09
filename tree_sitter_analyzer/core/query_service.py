#!/usr/bin/env python3
"""
Query Service

Unified query service for both CLI and MCP interfaces to avoid code duplication.
Provides core tree-sitter query functionality including predefined and custom queries.
"""

import logging
from typing import Any

from ..encoding_utils import read_file_safe
from ..query_loader import query_loader
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

    async def execute_query(
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

            # Execute tree-sitter query using new API with fallback
            import tree_sitter
            captures = []
            
            # Try to create and execute the query
            try:
                ts_query = tree_sitter.Query(language_obj, query_string)
                
                # Try to execute the query
                captures = ts_query.captures(tree.root_node)
                
                # If captures is empty or not in expected format, try manual fallback
                if not captures or (isinstance(captures, list) and len(captures) == 0):
                    captures = self._manual_query_execution(tree.root_node, query_key, language)
                    
            except (AttributeError, Exception) as e:
                # If query creation or execution fails, use manual fallback
                captures = self._manual_query_execution(tree.root_node, query_key, language)

            # Process capture results
            results = []
            if isinstance(captures, dict):
                # New tree-sitter API returns dictionary
                for capture_name, nodes in captures.items():
                    for node in nodes:
                        results.append(self._create_result_dict(node, capture_name))
            elif isinstance(captures, list):
                # Handle both old API (list of tuples) and manual execution (list of tuples)
                for capture in captures:
                    if isinstance(capture, tuple) and len(capture) == 2:
                        node, name = capture
                        results.append(self._create_result_dict(node, name))
            else:
                # If captures is not in expected format, try manual fallback
                manual_captures = self._manual_query_execution(tree.root_node, query_key, language)
                for capture in manual_captures:
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
        return {
            "capture_name": capture_name,
            "node_type": node.type if hasattr(node, "type") else "unknown",
            "start_line": (
                node.start_point[0] + 1 if hasattr(node, "start_point") else 0
            ),
            "end_line": node.end_point[0] + 1 if hasattr(node, "end_point") else 0,
            "content": (
                node.text.decode("utf-8", errors="replace")
                if hasattr(node, "text") and node.text
                else ""
            ),
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

    def _manual_query_execution(self, root_node: Any, query_key: str | None, language: str) -> list[tuple[Any, str]]:
        """
        Manual query execution fallback for tree-sitter 0.25.x compatibility
        
        Args:
            root_node: Root node of the parsed tree
            query_key: Query key to execute (can be None for custom queries)
            language: Programming language
            
        Returns:
            List of (node, capture_name) tuples
        """
        captures = []
        
        def walk_tree(node):
            """Walk the tree and find matching nodes"""
            # If query_key is None, this is a custom query - try to match common patterns
            if query_key is None:
                # For custom queries, try to match common node types
                if language == "java":
                    if node.type == "method_declaration":
                        captures.append((node, "method"))
                    elif node.type == "class_declaration":
                        captures.append((node, "class"))
                    elif node.type == "field_declaration":
                        captures.append((node, "field"))
                elif language == "python":
                    if node.type == "function_definition":
                        captures.append((node, "function"))
                    elif node.type == "class_definition":
                        captures.append((node, "class"))
                    elif node.type in ["import_statement", "import_from_statement"]:
                        captures.append((node, "import"))
                elif language in ["javascript", "typescript"]:
                    if node.type in ["function_declaration", "method_definition"]:
                        captures.append((node, "function"))
                    elif node.type == "class_declaration":
                        captures.append((node, "class"))
            
            # Markdown-specific queries
            elif language == "markdown":
                if query_key == "headers" and node.type in ["atx_heading", "setext_heading"]:
                    captures.append((node, "headers"))
                elif query_key == "code_blocks" and node.type in ["fenced_code_block", "indented_code_block"]:
                    captures.append((node, "code_blocks"))
                elif query_key == "links" and node.type == "inline":
                    # リンクは inline ノード内のパターンとして検出
                    node_text = node.text.decode('utf-8', errors='replace') if hasattr(node, 'text') and node.text else ""
                    if '[' in node_text and '](' in node_text:
                        captures.append((node, "links"))
                elif query_key == "images" and node.type == "inline":
                    # 画像は inline ノード内のパターンとして検出
                    node_text = node.text.decode('utf-8', errors='replace') if hasattr(node, 'text') and node.text else ""
                    if '![' in node_text and '](' in node_text:
                        captures.append((node, "images"))
                elif query_key == "lists" and node.type in ["list", "list_item"]:
                    captures.append((node, "lists"))
                elif query_key == "emphasis" and node.type == "inline":
                    # 強調は inline ノード内の * や ** パターンとして検出
                    node_text = node.text.decode('utf-8', errors='replace') if hasattr(node, 'text') and node.text else ""
                    if '*' in node_text or '_' in node_text:
                        captures.append((node, "emphasis"))
                elif query_key == "blockquotes" and node.type == "block_quote":
                    captures.append((node, "blockquotes"))
                elif query_key == "tables" and node.type == "pipe_table":
                    captures.append((node, "tables"))
                elif query_key == "horizontal_rules" and node.type == "thematic_break":
                    captures.append((node, "horizontal_rules"))
                elif query_key == "html_blocks" and node.type == "html_block":
                    captures.append((node, "html_blocks"))
                elif query_key == "inline_html" and node.type == "html_tag":
                    captures.append((node, "inline_html"))
                elif query_key == "inline_code" and node.type == "code_span":
                    captures.append((node, "inline_code"))
                elif query_key == "text_content" and node.type in ["paragraph", "inline"]:
                    captures.append((node, "text_content"))
                elif query_key == "all_elements" and node.type in [
                    "atx_heading", "setext_heading", "fenced_code_block", "indented_code_block",
                    "inline", "list", "list_item", "block_quote", "pipe_table",
                    "paragraph", "section"
                ]:
                    captures.append((node, "all_elements"))
            
            # Python-specific queries
            elif language == "python":
                if query_key in ["function", "functions"] and node.type == "function_definition":
                    captures.append((node, "function"))
                elif query_key in ["class", "classes"] and node.type == "class_definition":
                    captures.append((node, "class"))
                elif query_key in ["import", "imports"] and node.type in ["import_statement", "import_from_statement"]:
                    captures.append((node, "import"))
            
            # JavaScript/TypeScript-specific queries
            elif language in ["javascript", "typescript"]:
                if query_key == "function" and node.type in ["function_declaration", "function_expression", "arrow_function"]:
                    captures.append((node, "function"))
                elif query_key == "class" and node.type == "class_declaration":
                    captures.append((node, "class"))
                elif query_key == "method" and node.type == "method_definition":
                    captures.append((node, "method"))
            
            # Java-specific queries
            elif language == "java":
                if query_key in ["method", "methods"] and node.type == "method_declaration":
                    # Always use "method" as capture name for consistency
                    captures.append((node, "method"))
                elif query_key in ["class", "classes"] and node.type == "class_declaration":
                    captures.append((node, "class"))
                elif query_key == "field" and node.type == "field_declaration":
                    captures.append((node, "field"))
            
            # Recursively process children
            for child in node.children:
                walk_tree(child)
        
        walk_tree(root_node)
        return captures
