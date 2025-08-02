#!/usr/bin/env python3
"""
Base Tool Protocol for MCP Tools

This module defines the protocol that all MCP tools must implement
to ensure type safety and consistency.
"""

from typing import Any, Protocol


class MCPTool(Protocol):
    """
    Protocol for MCP tools.

    All MCP tools must implement this protocol to ensure they have
    the required methods for integration with the MCP server.
    """

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition.

        Returns:
            Tool definition object compatible with MCP server
        """
        ...

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary containing execution results
        """
        ...

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        ...
