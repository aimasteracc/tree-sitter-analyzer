"""
Tool Registry for MCP tools.

This module provides a registry for managing and accessing MCP tools.

Features:
- Tool registration
- Tool retrieval by name
- List all available tools
"""

from typing import Any

from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class ToolRegistry:
    """
    Registry for MCP tools.

    Manages registration and retrieval of tools.
    """

    def __init__(self):
        """Initialize tool registry."""
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool is None or name is empty
        """
        if tool is None:
            raise ValueError("Tool cannot be None")

        tool_name = tool.get_name()
        if not tool_name:
            raise ValueError("Tool name cannot be empty")

        self._tools[tool_name] = tool

    def get(self, tool_name: str) -> BaseTool:
        """
        Get tool by name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            Tool instance

        Raises:
            ValueError: If tool name is unknown
        """
        if tool_name not in self._tools:
            available = ", ".join(self.list_tools())
            raise ValueError(f"Unknown tool: {tool_name}. Available tools: {available}")

        return self._tools[tool_name]

    def list_tools(self) -> list[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """
        Get schemas for all registered tools.

        Returns:
            List of tool schemas in MCP format
        """
        schemas: list[dict[str, Any]] = []

        for tool in self._tools.values():
            schemas.append(
                {
                    "name": tool.get_name(),
                    "description": tool.get_description(),
                    "inputSchema": tool.get_schema(),
                }
            )

        return schemas
