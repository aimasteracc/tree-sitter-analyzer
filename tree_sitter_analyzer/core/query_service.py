#!/usr/bin/env python3
"""
Query Service

Unified query service for both CLI and MCP interfaces to avoid code duplication.
Provides core tree-sitter query functionality including predefined and custom queries.
"""

import asyncio
import logging
from typing import Any

from ..encoding_utils import read_file_safe
from ..plugins.manager import PluginManager
from ..query_loader import query_loader
from ..utils.tree_sitter_compat import get_node_text_safe
from ._query_service_helpers import (
    fallback_query_captures,
    plugin_category_captures,
    plugin_strategy_captures,
)
from .parser import Parser
from .query_executor import execute_ts_query, process_captures, resolve_query_string
from .query_filter import QueryFilter

logger = logging.getLogger(__name__)


class QueryService:
    """Unified query service providing tree-sitter query functionality"""

    _MAX_PARENT_CONTEXT_DEPTH = 64

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the query service"""
        self.project_root = project_root
        self.parser = Parser()
        self.filter = QueryFilter()
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

    async def execute_query(
        self,
        file_path: str,
        language: str,
        query_key: str | None = None,
        query_string: str | None = None,
        filter_expression: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """Execute a query against a file."""
        qs = resolve_query_string(language, query_key, query_string)

        try:
            content, _encoding = await self._read_file_async(file_path)

            parse_result = self.parser.parse_code(content, language, file_path)
            if not parse_result or not parse_result.tree:
                raise Exception("Failed to parse file")

            tree = parse_result.tree
            language_obj = tree.language if hasattr(tree, "language") else None
            if not language_obj:
                raise Exception(f"Language object not available for {language}")

            captures = execute_ts_query(
                tree,
                language_obj,
                qs,
                tree.root_node,
                self._execute_plugin_query,
                query_key,
                language,
                content,
            )

            results = process_captures(captures, content, self._create_result_dict)

            if filter_expression and results:
                results = self.filter.filter_results(results, filter_expression)

            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def _create_result_dict(
        self, node: Any, capture_name: str, source_code: str = ""
    ) -> dict[str, Any]:
        """
        Create result dictionary from tree-sitter node

        Args:
            node: tree-sitter node
            capture_name: capture name
            source_code: source code content for text extraction

        Returns:
            Result dictionary
        """
        # Use safe text extraction with source code
        content = get_node_text_safe(node, source_code)

        start_line = node.start_point[0] + 1 if hasattr(node, "start_point") else 0
        end_line = node.end_point[0] + 1 if hasattr(node, "end_point") else 0

        node_type = getattr(node, "type", "unknown")
        if not isinstance(node_type, str):
            node_type = "unknown"

        result = {
            "capture_name": capture_name,
            "node_type": node_type,
            "start_line": start_line,
            "end_line": end_line,
            "line_span": end_line - start_line + 1,
            "content": content,
        }

        name = self._extract_node_name(node)
        if name:
            result["name"] = name

        # Add enclosing context (parent class/module name)
        parent_name = self._extract_parent_context(node)
        if parent_name:
            result["parent"] = parent_name

        return result

    def _extract_node_name(self, node: Any) -> str | None:
        """Extract a human-readable name from a tree-sitter node."""
        child_by_field_name = getattr(node, "child_by_field_name", None)
        if not callable(child_by_field_name):
            return None

        for field in ("name", "declarator"):
            name_node = child_by_field_name(field)
            text = self._extract_name_node_text(name_node)
            if text:
                return text

        return None

    def _extract_name_node_text(self, name_node: Any) -> str | None:
        if name_node is None or not self._is_node_like(name_node):
            return None

        text = get_node_text_safe(name_node, "")
        if not text or len(text) >= 200:
            return None

        declarator_text = self._extract_nested_declarator_name(name_node)
        return declarator_text or text

    def _extract_nested_declarator_name(self, name_node: Any) -> str | None:
        name_node_type = getattr(name_node, "type", "")
        if not (
            isinstance(name_node_type, str) and name_node_type.endswith("_declarator")
        ):
            return None

        nested_child = getattr(name_node, "child_by_field_name", None)
        if not callable(nested_child):
            return None

        inner = nested_child("declarator") or nested_child("name")
        if inner is None or not self._is_node_like(inner):
            return None
        return get_node_text_safe(inner, "")

    # Node types that represent enclosing containers
    _CONTAINER_TYPES = frozenset(
        {
            "class_declaration",
            "class_definition",
            "class",
            "interface_declaration",
            "interface_definition",
            "interface",
            "struct_declaration",
            "struct_definition",
            "struct",
            "enum_declaration",
            "enum_definition",
            "enum",
            "trait_declaration",
            "trait",
            "module_declaration",
            "module_definition",
            "module",
            "namespace_definition",
            "namespace",
            "object_declaration",  # Kotlin
        }
    )

    def _extract_parent_context(self, node: Any) -> str | None:
        """Walk up the tree to find the enclosing class/struct/module name."""
        current = getattr(node, "parent", None)
        seen_ids: set[int] = set()
        depth = 0
        while (
            current is not None
            and depth < self._MAX_PARENT_CONTEXT_DEPTH
            and id(current) not in seen_ids
        ):
            seen_ids.add(id(current))
            depth += 1

            if not self._is_node_like(current):
                break

            current_type = getattr(current, "type", None)
            if not isinstance(current_type, str):
                current = getattr(current, "parent", None)
                continue

            if current_type in self._CONTAINER_TYPES:
                text = self._extract_container_name(current)
                if text:
                    return text

            current = getattr(current, "parent", None)

        return None

    def _extract_container_name(self, node: Any) -> str | None:
        child_by_field_name = getattr(node, "child_by_field_name", None)
        if not callable(child_by_field_name):
            return None

        name_node = child_by_field_name("name")
        if name_node is None:
            return None

        text = get_node_text_safe(name_node, "")
        if text and len(text) < 200:
            return text
        return None

    def _is_node_like(self, node: Any) -> bool:
        """Return True for real tree-sitter nodes or explicitly configured test nodes."""
        node_type = getattr(node, "type", None)
        if isinstance(node_type, str):
            return True

        text = getattr(node, "text", None)
        if isinstance(text, (bytes, str)):
            return True

        start_point = getattr(node, "start_point", None)
        end_point = getattr(node, "end_point", None)
        return self._is_point(start_point) and self._is_point(end_point)

    @staticmethod
    def _is_point(value: Any) -> bool:
        """Return True for tree-sitter point tuples."""
        return (
            isinstance(value, tuple)
            and len(value) == 2
            and all(isinstance(part, int) for part in value)
        )

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

    def _execute_plugin_query(
        self, root_node: Any, query_key: str | None, language: str, source_code: str
    ) -> list[tuple[Any, str]]:
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
        # Try to get plugin for the language
        plugin = self.plugin_manager.get_plugin(language)
        if not plugin:
            logger.warning(f"No plugin found for language: {language}")
            return self._fallback_query_execution(root_node, query_key)

        captures = plugin_strategy_captures(plugin, query_key, source_code)
        if captures is not None:
            return captures

        captures = plugin_category_captures(plugin, root_node, query_key)
        if captures is not None:
            return captures

        # Final fallback
        return self._fallback_query_execution(root_node, query_key)

    def _fallback_query_execution(
        self, root_node: Any, query_key: str | None
    ) -> list[tuple[Any, str]]:
        """
        Basic fallback query execution for unsupported languages

        Args:
            root_node: Root node of the parsed tree
            query_key: Query key to execute

        Returns:
            List of (node, capture_name) tuples
        """
        return fallback_query_captures(root_node, query_key)

    async def _read_file_async(self, file_path: str) -> tuple[str, str]:
        """
        非同期ファイル読み込み

        Args:
            file_path: ファイルパス

        Returns:
            tuple[str, str]: (content, encoding)
        """
        # CPU集約的でない単純なファイル読み込みなので、
        # run_in_executorを使用して非同期化
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, read_file_safe, file_path)
