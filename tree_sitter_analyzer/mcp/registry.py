#!/usr/bin/env python3
"""
MCP Tool Registry System

This module provides a centralized registry for all MCP tools, enabling:
- Tool discovery and listing
- Tool grouping by category/toolset
- Dynamic tool availability checking
- Tool metadata management

Inspired by hermes-agent's tools/registry.py design.
"""

from collections.abc import Callable
from typing import Any

from tree_sitter_analyzer.utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class ToolEntry:
    """Metadata for a single registered tool."""

    __slots__ = (
        "name",
        "toolset",
        "category",
        "schema",
        "handler",
        "check_fn",
        "is_async",
        "description",
        "emoji",
    )

    def __init__(
        self,
        name: str,
        toolset: str,
        category: str,
        schema: dict[str, Any],
        handler: Callable[..., Any],
        check_fn: Callable[[], bool] | None = None,
        is_async: bool = True,
        description: str = "",
        emoji: str = "",
    ) -> None:
        """
        Initialize a tool entry.

        Args:
            name: Tool name (unique identifier)
            toolset: Toolset/group name (e.g., "analysis", "query", "output")
            category: Category name (e.g., "dependency-graph", "symbol-query")
            schema: MCP tool schema (name, description, inputSchema)
            handler: Tool handler function
            check_fn: Optional availability check function
            is_async: Whether the handler is async
            description: Human-readable description
            emoji: Tool icon/emoji
        """
        self.name = name
        self.toolset = toolset
        self.category = category
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.is_async = is_async
        self.description = description or schema.get("description", "")
        self.emoji = emoji

    def is_available(self) -> bool:
        """Check if the tool is available."""
        if self.check_fn is None:
            return True
        try:
            return self.check_fn()
        except Exception:
            logger.warning(f"Check function failed for tool '{self.name}'")
            return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "toolset": self.toolset,
            "category": self.category,
            "description": self.description,
            "emoji": self.emoji,
            "available": self.is_available(),
            "is_async": self.is_async,
        }


class ToolRegistry:
    """
    Singleton registry for all MCP tools.

    Provides centralized tool registration, discovery, and management.
    """

    _instance: "ToolRegistry | None" = None

    def __init__(self) -> None:
        """Initialize the tool registry (singleton pattern)."""
        if ToolRegistry._instance is not None:
            raise RuntimeError("ToolRegistry is a singleton. Use get_instance().")
        self._tools: dict[str, ToolEntry] = {}
        self._toolsets: dict[str, list[str]] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def register(
        self,
        name: str,
        toolset: str,
        category: str,
        schema: dict[str, Any],
        handler: Callable[..., Any],
        check_fn: Callable[[], bool] | None = None,
        is_async: bool = True,
        description: str = "",
        emoji: str = "",
    ) -> None:
        """
        Register a tool.

        Args:
            name: Tool name (unique identifier)
            toolset: Toolset/group name
            category: Category name
            schema: MCP tool schema
            handler: Tool handler function
            check_fn: Optional availability check function
            is_async: Whether the handler is async
            description: Human-readable description
            emoji: Tool icon/emoji
        """
        if name in self._tools:
            logger.warning(
                f"Tool name collision: '{name}' (toolset '{self._tools[name].toolset}') "
                f"is being overwritten by toolset '{toolset}'"
            )

        entry = ToolEntry(
            name=name,
            toolset=toolset,
            category=category,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            is_async=is_async,
            description=description,
            emoji=emoji,
        )
        self._tools[name] = entry

        # Update toolset index
        if toolset not in self._toolsets:
            self._toolsets[toolset] = []
        if name not in self._toolsets[toolset]:
            self._toolsets[toolset].append(name)

        logger.debug(f"Registered tool: '{name}' in toolset '{toolset}'")

    def get_tool(self, name: str) -> ToolEntry | None:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            ToolEntry if found, None otherwise
        """
        return self._tools.get(name)

    def list_tools(
        self, toolset: str | None = None, available_only: bool = False
    ) -> list[ToolEntry]:
        """
        List tools, optionally filtered by toolset.

        Args:
            toolset: Optional toolset filter
            available_only: If True, only return available tools

        Returns:
            List of ToolEntry objects
        """
        tools = list(self._tools.values())

        if toolset is not None:
            tools = [t for t in tools if t.toolset == toolset]

        if available_only:
            tools = [t for t in tools if t.is_available()]

        return tools

    def get_toolsets(self) -> dict[str, dict[str, Any]]:
        """
        Get all toolsets with their metadata.

        Returns:
            Dictionary mapping toolset names to metadata
        """
        return {
            toolset: {
                "tools": [self._tools[name].to_dict() for name in tool_names],
                "count": len(tool_names),
            }
            for toolset, tool_names in self._toolsets.items()
        }

    def get_toolset_names(self) -> list[str]:
        """Get all toolset names."""
        return list(self._toolsets.keys())

    def deregister(self, name: str) -> None:
        """
        Remove a tool from the registry.

        Args:
            name: Tool name to remove
        """
        if name not in self._tools:
            logger.warning(f"Cannot deregister unknown tool: '{name}'")
            return

        entry = self._tools[name]
        toolset = entry.toolset

        # Remove from tools
        del self._tools[name]

        # Remove from toolset
        if toolset in self._toolsets and name in self._toolsets[toolset]:
            self._toolsets[toolset].remove(name)
            if not self._toolsets[toolset]:
                del self._toolsets[toolset]

        logger.debug(f"Deregistered tool: '{name}'")

    def clear(self) -> None:
        """Clear all tools from the registry (for testing)."""
        self._tools.clear()
        self._toolsets.clear()


# Global singleton instance
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
    ToolRegistry.reset()


# Toolset definitions (categories for organizing tools)
TOOLSET_DEFINITIONS: dict[str, dict[str, Any]] = {
    "analysis": {
        "description": "Code analysis and dependency tools",
        "emoji": "🔍",
        "tools": [
            "dependency_query",
            "trace_impact",
            "analyze_scale",
            "analyze_code_structure",
            "code_diff",
            "code_smell_detector",
            "code_clone_detection",
            "health_score",
            "error_recovery",
            "semantic_impact",
            "understand_codebase",
            "test_coverage",
            "refactoring_suggestions",
            "design_patterns",
            "grammar_discovery",
            "env_tracker",
            "doc_coverage",
            "function_size",
            "test_smells",
            "logging_patterns",
            "naming_conventions",
            "coupling_metrics",
            "cognitive_complexity",
            "nesting_depth",
            "i18n_strings",
            "assertion_quality",
            "exception_quality",
            "solid_principles",
        ],
    },
    "query": {
        "description": "Symbol and code query tools",
        "emoji": "🔎",
        "tools": ["query_code", "extract_code_section", "get_code_outline"],
    },
    "navigation": {
        "description": "File and code navigation tools",
        "emoji": "🧭",
        "tools": ["list_files", "find_and_grep", "search_content", "batch_search"],
    },
    "safety": {
        "description": "Safety and security tools",
        "emoji": "🛡️",
        "tools": ["modification_guard", "security_scan"],
    },
    "diagnostic": {
        "description": "Diagnostic and verification tools",
        "emoji": "🩺",
        "tools": ["check_tools", "ci_report", "pr_summary"],
    },
    "overview": {
        "description": "Unified project overview and reporting",
        "emoji": "📊",
        "tools": ["overview"],
    },
    "optimization": {
        "description": "Code optimization and transformation tools",
        "emoji": "⚡",
        "tools": [],
    },
    "index": {
        "description": "Project index and summary tools",
        "emoji": "📚",
        "tools": ["build_project_index", "get_project_summary"],
    },
}
