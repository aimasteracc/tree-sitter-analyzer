#!/usr/bin/env python3
"""
MCP Tool Discovery Tools

Provides MCP tools for discovering and listing registered tools:
- tools/list: List all tools with optional filtering
- tools/describe: Get detailed information about a specific tool
"""

from typing import Any

from ...utils import setup_logger
from ..registry import get_registry
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ToolDiscoveryTool(BaseMCPTool):
    """MCP tool for discovering and listing registered tools."""

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get MCP tool definition.

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "tools/list",
            "description": (
                "List all available MCP tools with optional filtering by toolset.\n\n"
                "WHEN TO USE:\n"
                "- Discover available analysis tools\n"
                "- Find tools in a specific category (analysis, query, navigation, etc.)\n"
                "- Get overview of all tool capabilities\n"
                "- Check which tools are currently available\n\n"
                "RETURNS:\n"
                "- List of tools with metadata (name, toolset, category, description, emoji)\n"
                "- Filtered by toolset if specified\n"
                "- Includes availability status for each tool"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "toolset": {
                        "type": "string",
                        "enum": ["analysis", "query", "navigation", "safety", "diagnostic", "index"],
                        "description": "Optional toolset filter (default: all tools)",
                    },
                    "available_only": {
                        "type": "boolean",
                        "description": "Only return available tools (default: false)",
                        "default": False,
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool list operation.

        Args:
            arguments: Tool arguments (toolset, available_only)

        Returns:
            Dictionary with tools list
        """
        registry = get_registry()
        toolset = arguments.get("toolset")
        available_only = arguments.get("available_only", False)

        tools = registry.list_tools(toolset=toolset, available_only=available_only)

        # Group by toolset
        result: dict[str, Any] = {"tools": [], "count": len(tools)}

        for tool in tools:
            result["tools"].append(
                {
                    "name": tool.name,
                    "toolset": tool.toolset,
                    "category": tool.category,
                    "description": tool.description,
                    "emoji": tool.emoji,
                    "available": tool.is_available(),
                }
            )

        return result

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if valid

        Raises:
            ValueError: If arguments are invalid
        """
        toolset = arguments.get("toolset")
        if toolset is not None:
            valid_toolsets = ["analysis", "query", "navigation", "safety", "diagnostic", "index"]
            if toolset not in valid_toolsets:
                raise ValueError(
                    f"Invalid toolset '{toolset}'. Must be one of: {valid_toolsets}"
                )

        available_only = arguments.get("available_only")
        if available_only is not None and not isinstance(available_only, bool):
            raise ValueError("'available_only' must be a boolean")

        return True


class ToolDescribeTool(BaseMCPTool):
    """MCP tool for getting detailed information about a specific tool."""

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get MCP tool definition.

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "tools/describe",
            "description": (
                "Get detailed information about a specific MCP tool.\n\n"
                "WHEN TO USE:\n"
                "- Learn about a tool's capabilities and parameters\n"
                "- Get tool's input schema for proper usage\n"
                "- Understand tool's category and toolset membership\n"
                "- Check tool availability and metadata\n\n"
                "RETURNS:\n"
                "- Tool metadata (name, toolset, category, description, emoji)\n"
                "- Full MCP input schema\n"
                "- Availability status"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Name of the tool to describe",
                    },
                },
                "required": ["tool_name"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool describe operation.

        Args:
            arguments: Tool arguments (tool_name)

        Returns:
            Dictionary with tool details
        """
        registry = get_registry()
        tool_name = arguments["tool_name"]

        entry = registry.get_tool(tool_name)
        if entry is None:
            return {
                "error": f"Tool '{tool_name}' not found",
                "available_tools": [t.name for t in registry.list_tools()],
            }

        return {
            "name": entry.name,
            "toolset": entry.toolset,
            "category": entry.category,
            "description": entry.description,
            "emoji": entry.emoji,
            "available": entry.is_available(),
            "is_async": entry.is_async,
            "schema": entry.schema,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if valid

        Raises:
            ValueError: If arguments are invalid
        """
        if "tool_name" not in arguments:
            raise ValueError("'tool_name' is required")

        tool_name = arguments["tool_name"]
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("'tool_name' must be a non-empty string")

        return True
