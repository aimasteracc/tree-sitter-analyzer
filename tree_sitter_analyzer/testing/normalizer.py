#!/usr/bin/env python3
"""
MCP Output Normalizer

Normalizes MCP tool output for deterministic comparison in golden master tests.
Handles volatile fields, path normalization, and key ordering.
"""

import re
from copy import deepcopy
from typing import Any


class MCPOutputNormalizer:
    """
    Normalizes MCP output for deterministic comparison.

    This class removes volatile fields that change between runs,
    normalizes file paths for cross-platform compatibility,
    and sorts dictionary keys for consistent ordering.
    """

    # Fields to remove entirely (volatile - change between runs)
    VOLATILE_FIELDS: set[str] = {
        "timestamp",
        "duration_ms",
        "cache_hit",
        "analysis_time",
        "execution_time",
        "processing_time",
        "fd_elapsed_ms",
        "rg_elapsed_ms",
        "elapsed_ms",
        "elapsed_time",
        "content_hash",  # File content hash - changes with file content
        "mtime",  # File modification time - changes when files are modified
        "size_bytes",  # File size - changes when files are modified
    }

    # Fields that contain file paths (need normalization)
    PATH_FIELDS: set[str] = {
        "file_path",
        "project_root",
        "absolute_path",
        "resolved_path",
        "output_file",
        "directory",
        "root",
        "path",
    }

    # Regex patterns for dynamic values
    TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
    DURATION_PATTERN = re.compile(r"\d+\.\d+\s*(ms|s|seconds?|milliseconds?)")

    def __init__(
        self,
        remove_volatile: bool = True,
        normalize_paths: bool = True,
        sort_keys: bool = True,
        custom_volatile_fields: set[str] | None = None,
    ) -> None:
        """
        Initialize the normalizer.

        Args:
            remove_volatile: Whether to remove volatile fields
            normalize_paths: Whether to normalize file paths
            sort_keys: Whether to sort dictionary keys
            custom_volatile_fields: Additional fields to treat as volatile
        """
        self.remove_volatile = remove_volatile
        self.normalize_paths = normalize_paths
        self.sort_keys = sort_keys
        self.volatile_fields = self.VOLATILE_FIELDS.copy()
        if custom_volatile_fields:
            self.volatile_fields.update(custom_volatile_fields)

    def normalize(self, output: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize output for comparison.

        Args:
            output: Raw MCP tool output

        Returns:
            Normalized output suitable for golden master comparison
        """
        result = deepcopy(output)

        if self.remove_volatile:
            result = self._remove_volatile_fields(result)

        if self.normalize_paths:
            result = self._normalize_paths(result)

        if self.sort_keys:
            result = self._sort_keys_recursive(result)

        return result

    def _remove_volatile_fields(self, data: Any) -> Any:
        """
        Remove fields that change between runs.

        Args:
            data: Data to process

        Returns:
            Data with volatile fields removed
        """
        if isinstance(data, dict):
            return {
                k: self._remove_volatile_fields(v)
                for k, v in data.items()
                if k not in self.volatile_fields
            }
        elif isinstance(data, list):
            return [self._remove_volatile_fields(item) for item in data]
        else:
            return data

    def _normalize_paths(self, data: Any, key: str | None = None) -> Any:
        """
        Normalize file paths for cross-platform comparison.

        Converts backslashes to forward slashes and removes
        absolute path prefixes for relative path comparison.

        Args:
            data: Data to process
            key: Current key name (for context)

        Returns:
            Data with normalized paths
        """
        if isinstance(data, dict):
            return {k: self._normalize_paths(v, k) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._normalize_paths(item, key) for item in data]
        elif isinstance(data, str):
            # Check if this is a path field
            if key and key in self.PATH_FIELDS:
                return self._normalize_single_path(data)
            # Also check for path-like strings
            if "\\" in data or data.startswith("/") or ":" in data[:3]:
                return self._normalize_single_path(data)
            return data
        else:
            return data

    def _normalize_single_path(self, path: str) -> str:
        """
        Normalize a single file path.

        Args:
            path: Path to normalize

        Returns:
            Normalized path with forward slashes
        """
        # Convert backslashes to forward slashes
        normalized = path.replace("\\", "/")

        # Remove drive letter prefix (Windows)
        if len(normalized) > 2 and normalized[1] == ":":
            normalized = normalized[2:]

        # Remove leading absolute path components
        # Keep relative paths starting from known project directories
        known_roots = ["/examples/", "/tests/", "/tree_sitter_analyzer/"]
        for root in known_roots:
            idx = normalized.find(root)
            if idx != -1:
                normalized = normalized[idx:]
                break

        return normalized

    def _sort_keys_recursive(self, data: Any) -> Any:
        """
        Recursively sort dictionary keys for consistent ordering.

        Args:
            data: Data to process

        Returns:
            Data with sorted dictionary keys
        """
        if isinstance(data, dict):
            return {k: self._sort_keys_recursive(v) for k, v in sorted(data.items())}
        elif isinstance(data, list):
            # Don't sort lists - order may be significant
            return [self._sort_keys_recursive(item) for item in data]
        else:
            return data

    def normalize_string_values(self, data: Any) -> Any:
        """
        Normalize string values that may contain dynamic content.

        Args:
            data: Data to process

        Returns:
            Data with normalized string values
        """
        if isinstance(data, dict):
            return {k: self.normalize_string_values(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.normalize_string_values(item) for item in data]
        elif isinstance(data, str):
            # Replace timestamps with placeholder
            result = self.TIMESTAMP_PATTERN.sub("<TIMESTAMP>", data)
            # Replace durations with placeholder
            result = self.DURATION_PATTERN.sub("<DURATION>", result)
            return result
        else:
            return data

    def round_floats(self, data: Any, precision: int = 2) -> Any:
        """
        Round floating point numbers to specified precision.

        Args:
            data: Data to process
            precision: Number of decimal places

        Returns:
            Data with rounded floats
        """
        if isinstance(data, dict):
            return {k: self.round_floats(v, precision) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.round_floats(item, precision) for item in data]
        elif isinstance(data, float):
            return round(data, precision)
        else:
            return data
