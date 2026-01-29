"""Argument validator for SearchContentTool.

This module provides validation logic for search tool arguments.
"""

import logging
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.mcp.tools.search_strategies.base import SearchContext

logger = logging.getLogger(__name__)


class SearchArgumentValidator:
    """Validator for search tool arguments.

    This class handles all argument validation logic, including:
    - Required parameter checks
    - Type validation
    - Value range validation
    - Mutual exclusivity checks
    - Path validation
    """

    def __init__(
        self, project_root: str | Path | None = None, path_resolver: Any = None
    ) -> None:
        """Initialize the validator.

        Args:
            project_root: Root directory of the project (defaults to current directory)
            path_resolver: Optional path resolver for validating file paths
        """
        self.project_root = (
            Path(project_root) if project_root is not None else Path.cwd()
        )
        self.path_resolver = path_resolver

    def validate(self, arguments: dict[str, Any]) -> SearchContext:
        """Validate arguments and create SearchContext.

        Args:
            arguments: Arguments dictionary from tool call

        Returns:
            SearchContext with validated parameters

        Raises:
            ValueError: If required parameters are missing or invalid
            TypeError: If parameter types are incorrect
        """
        # Validate required parameters
        self._validate_required_parameters(arguments)

        # Validate parameter types
        self._validate_parameter_types(arguments)

        # Validate parameter values
        self._validate_parameter_values(arguments)

        # Validate mutual exclusivity
        self._validate_mutual_exclusivity(arguments)

        # Validate and resolve paths
        roots, files = self._validate_and_resolve_paths(arguments)

        # Create and return SearchContext
        context = SearchContext(
            arguments=arguments,
            project_root=self.project_root,
        )

        # Override roots and files with validated values
        context.roots = roots
        context.files = files

        return context

    def _validate_required_parameters(self, arguments: dict[str, Any]) -> None:
        """Validate that required parameters are present.

        Args:
            arguments: Arguments dictionary

        Raises:
            ValueError: If required parameters are missing
        """
        if "query" not in arguments:
            raise ValueError("Missing required parameter: 'query'")

        # Either roots or files must be provided
        if "roots" not in arguments and "files" not in arguments:
            raise ValueError("Either 'roots' or 'files' parameter must be provided")

    def _validate_parameter_types(self, arguments: dict[str, Any]) -> None:
        """Validate parameter types.

        Args:
            arguments: Arguments dictionary

        Raises:
            TypeError: If parameter types are incorrect
        """
        # String parameters
        string_params = ["query", "case", "output_format", "max_filesize", "encoding"]
        for param in string_params:
            if param in arguments and not isinstance(arguments[param], str):
                raise TypeError(f"Parameter '{param}' must be a string")

        # List parameters
        list_params = ["roots", "files", "include_globs", "exclude_globs"]
        for param in list_params:
            if param in arguments and not isinstance(arguments[param], list):
                raise TypeError(f"Parameter '{param}' must be a list")

        # Boolean parameters
        bool_params = [
            "fixed_strings",
            "word",
            "multiline",
            "follow_symlinks",
            "hidden",
            "no_ignore",
            "total_only",
            "count_only_matches",
            "summary_only",
            "group_by_file",
            "optimize_paths",
            "suppress_output",
            "enable_parallel",
        ]
        for param in bool_params:
            if param in arguments and not isinstance(arguments[param], bool):
                raise TypeError(f"Parameter '{param}' must be a boolean")

        # Integer parameters
        int_params = ["context_before", "context_after", "max_count", "timeout_ms"]
        for param in int_params:
            if param in arguments and not isinstance(arguments[param], int):
                raise TypeError(f"Parameter '{param}' must be an integer")

    def _validate_parameter_values(self, arguments: dict[str, Any]) -> None:
        """Validate parameter values.

        Args:
            arguments: Arguments dictionary

        Raises:
            ValueError: If parameter values are invalid
        """
        # Validate case parameter
        if "case" in arguments:
            valid_cases = ["smart", "insensitive", "sensitive"]
            if arguments["case"] not in valid_cases:
                raise ValueError(
                    f"Invalid case value: '{arguments['case']}'. "
                    f"Must be one of: {', '.join(valid_cases)}"
                )

        # Validate output_format parameter
        if "output_format" in arguments:
            valid_formats = ["toon", "json"]
            if arguments["output_format"] not in valid_formats:
                raise ValueError(
                    f"Invalid output_format value: '{arguments['output_format']}'. "
                    f"Must be one of: {', '.join(valid_formats)}"
                )

        # Validate integer ranges
        if "context_before" in arguments and arguments["context_before"] < 0:
            raise ValueError("context_before must be non-negative")

        if "context_after" in arguments and arguments["context_after"] < 0:
            raise ValueError("context_after must be non-negative")

        if "max_count" in arguments and arguments["max_count"] < 1:
            raise ValueError("max_count must be at least 1")

        if "timeout_ms" in arguments and arguments["timeout_ms"] < 1:
            raise ValueError("timeout_ms must be at least 1")

    def _validate_mutual_exclusivity(self, arguments: dict[str, Any]) -> None:
        """Validate mutually exclusive parameters.

        Args:
            arguments: Arguments dictionary

        Raises:
            ValueError: If mutually exclusive parameters are both set
        """
        # roots and files are mutually exclusive
        if "roots" in arguments and "files" in arguments:
            raise ValueError("Parameters 'roots' and 'files' are mutually exclusive")

        # Output mode flags are mutually exclusive
        output_modes = [
            "total_only",
            "count_only_matches",
            "summary_only",
            "group_by_file",
            "optimize_paths",
        ]
        active_modes = [mode for mode in output_modes if arguments.get(mode, False)]

        if len(active_modes) > 1:
            raise ValueError(
                f"Output mode parameters are mutually exclusive. "
                f"Found multiple active modes: {', '.join(active_modes)}"
            )

    def _validate_and_resolve_paths(
        self, arguments: dict[str, Any]
    ) -> tuple[list[str] | None, list[str] | None]:
        """Validate and resolve file paths.

        Args:
            arguments: Arguments dictionary

        Returns:
            Tuple of (validated_roots, validated_files)

        Raises:
            ValueError: If paths are invalid or outside project root
        """
        roots = None
        files = None

        # Validate roots
        if "roots" in arguments:
            roots = self._validate_roots(arguments["roots"])

        # Validate files
        if "files" in arguments:
            files = self._validate_files(arguments["files"])

            # Warn about large files if max_filesize is set
            self._warn_about_large_files(files, arguments.get("max_filesize"))

        return roots, files

    def _validate_roots(self, roots: list[str]) -> list[str]:
        """Validate root directories.

        Args:
            roots: List of root directory paths

        Returns:
            List of validated root paths

        Raises:
            ValueError: If roots are invalid
        """
        if not roots:
            raise ValueError("roots parameter cannot be empty")

        if not self.path_resolver:
            return roots

        validated_roots = []
        for root in roots:
            try:
                resolved = self.path_resolver.resolve(root)
                validated_roots.append(resolved)
            except Exception as e:
                raise ValueError(f"Invalid root path '{root}': {e}") from e

        return validated_roots

    def _validate_files(self, files: list[str]) -> list[str]:
        """Validate file paths.

        Args:
            files: List of file paths

        Returns:
            List of validated file paths

        Raises:
            ValueError: If files are invalid
        """
        if not files:
            raise ValueError("files parameter cannot be empty")

        if not self.path_resolver:
            return files

        validated_files = []
        for file_path in files:
            try:
                resolved = self.path_resolver.resolve(file_path)
                validated_files.append(resolved)
            except Exception as e:
                raise ValueError(f"Invalid file path '{file_path}': {e}") from e

        return validated_files

    def _warn_about_large_files(
        self, files: list[str], max_filesize: str | None
    ) -> None:
        """Warn about files that exceed the size limit.

        Args:
            files: List of file paths
            max_filesize: Maximum file size string (e.g., "10M")
        """
        if not max_filesize:
            return

        # Parse size limit
        from tree_sitter_analyzer.mcp.tools.fd_rg import RgCommandBuilder

        limit_bytes = RgCommandBuilder()._parse_size_to_bytes(max_filesize)
        if not limit_bytes:
            return

        # Check each file
        for file_path in files:
            try:
                size = Path(file_path).stat().st_size
                if size > limit_bytes:
                    logger.warning(
                        f"File {file_path} is {size} bytes, which exceeds the search limit of {max_filesize}. "
                        "It will be skipped by ripgrep. Increase 'max_filesize' to search this file."
                    )
            except Exception as e:
                logger.debug(f"Could not check size of {file_path}: {e}")
