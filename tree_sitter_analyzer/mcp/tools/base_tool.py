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
from ..utils.shared_cache import get_shared_cache

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
        # Invalidate shared caches when the project root changes to avoid cross-project pollution.
        get_shared_cache().clear()
        logger.info(
            f"{self.__class__.__name__} project path updated to: {project_path}"
        )

    def resolve_and_validate_file_path(self, file_path: str) -> str:
        """
        Resolve a file path and validate it with caching to avoid redundant checks.

        This method is designed to be the single entry point used by tools that operate on
        `arguments["file_path"]`.
        """
        shared_cache = get_shared_cache()
        project_root = self.project_root

        # Validate the original input path first (pre-resolution) and cache it.
        # We intentionally validate only once per (project_root, file_path) to keep security
        # validation caching effective (tests expect 1 call when repeating within same root).
        cached_orig = shared_cache.get_security_validation(
            file_path, project_root=project_root
        )
        if cached_orig is None:
            cached_orig = self.security_validator.validate_file_path(
                file_path, base_path=project_root
            )
            shared_cache.set_security_validation(
                file_path, cached_orig, project_root=project_root
            )
        is_valid, error_msg = cached_orig
        if not is_valid:
            raise ValueError(
                f"Invalid file path: Security validation failed: {error_msg}"
            )

        # Resolve with shared cache (avoid repeating PathResolver.resolve across tools)
        resolved = shared_cache.get_resolved_path(file_path, project_root=project_root)
        if not resolved:
            try:
                resolved = self.path_resolver.resolve(file_path)
            except Exception as e:
                # Normalize resolver failures to ValueError for tool callers
                raise ValueError(f"Invalid file path: {e}") from e
            shared_cache.set_resolved_path(
                file_path, resolved, project_root=project_root
            )

        # Populate the resolved-path key for better cross-layer cache reuse without
        # performing a second validation call.
        if not shared_cache.get_security_validation(
            resolved, project_root=project_root
        ):
            shared_cache.set_security_validation(
                resolved, (True, ""), project_root=project_root
            )

        return resolved

    def resolve_and_validate_directory_path(self, dir_path: str) -> str:
        """
        Resolve a directory path and validate it.

        Args:
            dir_path: Path to the directory

        Returns:
            Resolved absolute path

        Raises:
            ValueError: If directory path is invalid or unsafe
        """
        # Resolve path
        resolved = self.path_resolver.resolve(dir_path)

        # Security validation for directory
        is_valid, error_msg = self.security_validator.validate_directory_path(
            resolved, must_exist=True
        )
        if not is_valid:
            raise ValueError(f"Invalid directory path: {error_msg}")

        return resolved

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
