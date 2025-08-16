#!/usr/bin/env python3
"""
Code File Resource for MCP

This module provides MCP resource implementation for accessing code file content.
The resource allows dynamic access to file content through URI-based identification.
"""

import logging
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.encoding_utils import read_file_safe

logger = logging.getLogger(__name__)


class CodeFileResource:
    """
    MCP resource for accessing code file content

    This resource provides access to code file content through the MCP protocol.
    It supports reading files with proper encoding detection and error handling.

    URI Format: code://file/{file_path}

    Examples:
        - code://file/src/main/java/Example.java
        - code://file/scripts/helper.py
        - code://file/test.js
    """

    def __init__(self) -> None:
        """Initialize the code file resource"""
        self._uri_pattern = re.compile(r"^code://file/(.+)$")

    def get_resource_info(self) -> dict[str, Any]:
        """
        Get resource information for MCP registration

        Returns:
            Dict containing resource metadata
        """
        return {
            "name": "code_file",
            "description": "Access to code file content through URI-based identification",
            "uri_template": "code://file/{file_path}",
            "mime_type": "text/plain",
        }

    def matches_uri(self, uri: str) -> bool:
        """
        Check if the URI matches this resource pattern

        Args:
            uri: The URI to check

        Returns:
            True if the URI matches the code file pattern
        """
        return bool(self._uri_pattern.match(uri))

    def _extract_file_path(self, uri: str) -> str:
        """
        Extract file path from URI

        Args:
            uri: The URI to extract path from

        Returns:
            The extracted file path

        Raises:
            ValueError: If URI format is invalid
        """
        match = self._uri_pattern.match(uri)
        if not match:
            raise ValueError(f"Invalid URI format: {uri}")

        return match.group(1)

    async def _read_file_content(self, file_path: str) -> str:
        """
        Read file content with proper encoding detection

        Args:
            file_path: Path to the file to read

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file cannot be read due to permissions
            OSError: If file cannot be read due to other OS errors
        """
        try:
            # Use existing encoding-safe file reader
            # Check if file exists first
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            content, encoding = read_file_safe(file_path)
            return content

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except PermissionError:
            logger.error(f"Permission denied reading file: {file_path}")
            raise
        except OSError as e:
            logger.error(f"OS error reading file {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading file {file_path}: {e}")
            raise OSError(f"Failed to read file: {e}") from e

    def _validate_file_path(self, file_path: str) -> None:
        """
        Validate file path for security and correctness

        Args:
            file_path: The file path to validate

        Raises:
            ValueError: If file path is invalid or potentially dangerous
        """
        if not file_path:
            raise ValueError("File path cannot be empty")

        # Check for null bytes
        if "\x00" in file_path:
            raise ValueError("File path contains null bytes")

        # Check for potentially dangerous path traversal
        if ".." in file_path:
            raise ValueError(f"Path traversal not allowed: {file_path}")

        # Additional security checks could be added here
        # For example, restricting to certain directories

    async def read_resource(self, uri: str) -> str:
        """
        Read resource content from URI

        Args:
            uri: The resource URI to read

        Returns:
            Resource content as string

        Raises:
            ValueError: If URI format is invalid
            FileNotFoundError: If file doesn't exist
            PermissionError: If file cannot be read due to permissions
            OSError: If file cannot be read due to other errors
        """
        logger.debug(f"Reading resource: {uri}")

        # Validate URI format
        if not self.matches_uri(uri):
            raise ValueError(f"URI does not match code file pattern: {uri}")

        # Extract file path
        file_path = self._extract_file_path(uri)

        # Validate file path
        self._validate_file_path(file_path)

        # Read file content
        try:
            content = await self._read_file_content(file_path)
            logger.debug(
                f"Successfully read {len(content)} characters from {file_path}"
            )
            return content

        except Exception as e:
            logger.error(f"Failed to read resource {uri}: {e}")
            raise

    def get_supported_schemes(self) -> list[str]:
        """
        Get list of supported URI schemes

        Returns:
            List of supported schemes
        """
        return ["code"]

    def get_supported_resource_types(self) -> list[str]:
        """
        Get list of supported resource types

        Returns:
            List of supported resource types
        """
        return ["file"]

    def __str__(self) -> str:
        """String representation of the resource"""
        return "CodeFileResource(pattern=code://file/{file_path})"

    def __repr__(self) -> str:
        """Detailed string representation of the resource"""
        return f"CodeFileResource(uri_pattern={self._uri_pattern.pattern})"
