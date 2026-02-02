"""
Base MCP Tool class.

This module provides the abstract base class for all MCP tools.

All tools must implement:
- get_name(): Return tool name
- get_description(): Return tool description
- get_schema(): Return JSON schema for arguments
- execute(): Execute the tool with given arguments
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    Abstract base class for MCP tools.

    All tools must inherit from this class and implement the required methods.
    """

    @abstractmethod
    def get_name(self) -> str:
        """
        Get tool name.

        Returns:
            Tool name (e.g., "analyze_code_structure")
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Get tool description.

        Returns:
            Human-readable description of what the tool does
        """
        pass

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """
        Get JSON schema for tool arguments.

        Returns:
            JSON schema dict defining the tool's input parameters
        """
        pass

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with given arguments.

        Args:
            arguments: Tool arguments matching the schema

        Returns:
            Tool execution result as a dictionary
        """
        pass
