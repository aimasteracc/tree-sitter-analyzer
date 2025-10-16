#!/usr/bin/env python3
"""
Base Tool Protocol for MCP Tools

This module defines the base class that all MCP tools should inherit from
to ensure consistent behavior and project path management.
"""

from abc import ABC, abstractmethod
from typing import Any

from ...security import SecurityValidator
from ...utils import setup_logger
from ..utils.path_resolver import PathResolver

# Set up logging
logger = setup_logger(__name__)


class BaseMCPTool(ABC):
    """
    Base class for all MCP tools.

    Provides common functionality including project path management,
    security validation, and path resolution.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize the base MCP tool.

        Args:
            project_root: Optional project root directory
        """
        self.project_root = project_root
        self.security_validator = SecurityValidator(project_root)
        self.path_resolver = PathResolver(project_root)
        logger.debug(
            f"{self.__class__.__name__} initialized with project root: {project_root}"
        )

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Args:
            project_path: New project root directory
        """
        self.project_root = project_path
        self.security_validator = SecurityValidator(project_path)
        self.path_resolver = PathResolver(project_path)
        logger.info(
            f"{self.__class__.__name__} project path updated to: {project_path}"
        )

    @abstractmethod
    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition.

        Returns:
            Tool definition object compatible with MCP server
        """
        pass

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary containing execution results
        """
        pass

    @abstractmethod
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
        pass


# Keep the protocol for backward compatibility
class MCPTool(BaseMCPTool):
    """
    Protocol for MCP tools (deprecated, use BaseMCPTool instead).

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
        raise NotImplementedError("Subclasses must implement execute method")

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
        raise NotImplementedError("Subclasses must implement validate_arguments method")
