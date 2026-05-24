#!/usr/bin/env python3
"""
Project Statistics Resource for MCP

This module provides MCP resource implementation for accessing project
statistics and analysis data. The resource allows dynamic access to
project analysis results through URI-based identification.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
from tree_sitter_analyzer.language_detector import (
    detect_language_from_file,
    is_language_supported,
)

from ._project_stats_resource_helpers import (
    build_complexity_stats,
    build_files_stats,
    build_languages_list,
    build_languages_stats,
    build_overview_stats,
    collect_complexity_data,
    collect_files_data,
    collect_language_scan,
    collect_overview_scan,
    require_project_dir,
)

logger = logging.getLogger(__name__)


class ProjectStatsResource:
    """
    MCP resource for accessing project statistics and analysis data

    This resource provides access to project analysis results through the MCP protocol.
    It supports various types of statistics including overview, language breakdown,
    complexity metrics, and file-level information.

    URI Format: code://stats/{stats_type}

    Supported stats types:
        - overview: General project overview
        - languages: Language breakdown and statistics
        - complexity: Complexity metrics and analysis
        - files: File-level statistics and information

    Examples:
        - code://stats/overview
        - code://stats/languages
        - code://stats/complexity
        - code://stats/files
    """

    def __init__(self) -> None:
        """Initialize the project statistics resource"""
        self._uri_pattern = re.compile(r"^code://stats/(.+)$")
        self._project_path: str | None = None
        self.analysis_engine = get_analysis_engine()
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer

        # Supported statistics types
        self._supported_stats_types = {"overview", "languages", "complexity", "files"}

    @property
    def project_root(self) -> str | None:
        """Get current project root path"""
        return self._project_path

    @project_root.setter
    def project_root(self, value: str | None) -> None:
        """Set the current project root path"""
        self._project_path = value

    def get_resource_info(self) -> dict[str, Any]:
        """
        Get resource information for MCP registration

        Returns:
            Dict containing resource metadata
        """
        return {
            "name": "project_stats",
            "description": "Access to project statistics and analysis data",
            "uri_template": "code://stats/{stats_type}",
            "mime_type": "application/json",
        }

    def matches_uri(self, uri: str) -> bool:
        """
        Check if the URI matches this resource pattern

        Args:
            uri: The URI to check

        Returns:
            True if the URI matches the project stats pattern
        """
        # Convert to string to handle AnyUrl type from MCP library
        uri_str = str(uri)
        return bool(self._uri_pattern.match(uri_str))

    def _extract_stats_type(self, uri: str) -> str:
        """
        Extract statistics type from URI

        Args:
            uri: The URI to extract stats type from

        Returns:
            The extracted statistics type

        Raises:
            ValueError: If URI format is invalid
        """
        # Convert to string to handle AnyUrl type from MCP library
        uri_str = str(uri)
        match = self._uri_pattern.match(uri_str)
        if not match:
            raise ValueError(f"Invalid URI format: {uri}")

        return match.group(1)

    def set_project_path(self, project_path: str) -> None:
        """
        Set the project path for analysis

        Args:
            project_path: Path to the project directory

        Raises:
            TypeError: If project_path is not a string
            ValueError: If project_path is empty
        """
        if not isinstance(project_path, str):
            raise TypeError("Project path must be a string")

        if not project_path:
            raise ValueError("Project path cannot be empty")

        self._project_path = project_path

        # Note: analysis_engine is already initialized in __init__
        # No need to reinitialize here

        logger.debug(f"Set project path to: {project_path}")

    def _validate_project_path(self) -> None:
        """
        Validate that project path is set and exists

        Raises:
            ValueError: If project path is not set
            FileNotFoundError: If project path doesn't exist
        """
        if not self._project_path:
            raise ValueError("Project path not set. Call set_project_path() first.")

        if self._project_path is None:
            raise ValueError("Project path is not set")
        project_dir = Path(self._project_path)
        if not project_dir.exists():
            raise FileNotFoundError(
                f"Project directory does not exist: {self._project_path}"
            )

        if not project_dir.is_dir():
            raise FileNotFoundError(
                f"Project path is not a directory: {self._project_path}"
            )

    def _is_supported_code_file(self, file_path: Path) -> bool:
        """
        Check if file is a supported code file using language detection

        Args:
            file_path: Path to the file

        Returns:
            True if file is a supported code file
        """
        try:
            language = detect_language_from_file(
                str(file_path), project_root=self._project_path
            )
            return is_language_supported(language)
        except Exception:
            return False

    def _get_language_from_file(self, file_path: Path) -> str:
        """
        Get language from file using language detector

        Args:
            file_path: Path to the file

        Returns:
            Detected language name
        """
        try:
            return detect_language_from_file(
                str(file_path), project_root=self._project_path
            )
        except Exception:
            return "unknown"

    async def _generate_overview_stats(self) -> dict[str, Any]:
        """
        Generate overview statistics for the project

        Returns:
            Dictionary containing overview statistics
        """
        logger.debug("Generating overview statistics")

        total_files, total_lines, language_counts = collect_overview_scan(
            require_project_dir(self._project_path),
            self._is_supported_code_file,
            self._get_language_from_file,
            logger=logger,
        )
        overview = build_overview_stats(
            self._project_path, total_files, total_lines, language_counts
        )

        logger.debug(f"Generated overview with {overview['total_files']} files")
        return overview

    async def _generate_languages_stats(self) -> dict[str, Any]:
        """
        Generate language-specific statistics

        Returns:
            Dictionary containing language statistics
        """
        logger.debug("Generating language statistics")

        total_lines, language_data = collect_language_scan(
            require_project_dir(self._project_path),
            self._is_supported_code_file,
            self._get_language_from_file,
            logger=logger,
        )
        languages_list = build_languages_list(total_lines, language_data)
        languages_stats = build_languages_stats(languages_list)

        logger.debug(f"Generated stats for {len(languages_list)} languages")
        return languages_stats

    async def _generate_complexity_stats(self) -> dict[str, Any]:
        """
        Generate complexity statistics

        Returns:
            Dictionary containing complexity statistics
        """
        logger.debug("Generating complexity statistics")

        complexity_data = await collect_complexity_data(
            require_project_dir(self._project_path),
            self.analysis_engine,
            self._is_supported_code_file,
            self._get_language_from_file,
            logger=logger,
        )
        complexity_stats = build_complexity_stats(complexity_data)

        logger.debug(
            f"Generated complexity stats for {complexity_stats['total_files_analyzed']} files"
        )
        return complexity_stats

    async def _generate_files_stats(self) -> dict[str, Any]:
        """
        Generate file-level statistics

        Returns:
            Dictionary containing file statistics
        """
        logger.debug("Generating file statistics")

        files_data = collect_files_data(
            require_project_dir(self._project_path),
            self._is_supported_code_file,
            self._get_language_from_file,
            logger=logger,
        )
        files_stats = build_files_stats(files_data)

        logger.debug(f"Generated stats for {len(files_data)} files")
        return files_stats

    async def read_resource(self, uri: str) -> str:
        """
        Read resource content from URI

        Args:
            uri: The resource URI to read

        Returns:
            Resource content as JSON string

        Raises:
            ValueError: If URI format is invalid or stats type is unsupported
            FileNotFoundError: If project path doesn't exist
        """
        logger.debug(f"Reading resource: {uri}")

        # Validate URI format
        if not self.matches_uri(uri):
            raise ValueError(f"URI does not match project stats pattern: {uri}")

        # Extract statistics type
        stats_type = self._extract_stats_type(uri)

        # Validate statistics type
        if stats_type not in self._supported_stats_types:
            raise ValueError(
                f"Unsupported statistics type: {stats_type}. "
                f"Supported types: {', '.join(self._supported_stats_types)}"
            )

        # Validate project path
        self._validate_project_path()

        try:
            stats_data = await self._generate_stats(stats_type)
            json_content = json.dumps(stats_data, indent=2, ensure_ascii=False)
            logger.debug(f"Successfully generated {stats_type} statistics")
            return json_content
        except Exception as e:
            logger.error(f"Failed to generate {stats_type} statistics: {e}")
            raise

    async def _generate_stats(self, stats_type: str) -> dict[str, Any]:
        """Dispatch a supported stats type to its generator."""
        generators = {
            "overview": self._generate_overview_stats,
            "languages": self._generate_languages_stats,
            "complexity": self._generate_complexity_stats,
            "files": self._generate_files_stats,
        }
        generator = generators.get(stats_type)
        if generator is None:
            raise ValueError(f"Unknown statistics type: {stats_type}")
        return await generator()

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
        return ["stats"]

    def get_supported_stats_types(self) -> list[str]:
        """
        Get list of supported statistics types

        Returns:
            List of supported statistics types
        """
        return list(self._supported_stats_types)

    def __str__(self) -> str:
        """String representation of the resource"""
        return "ProjectStatsResource(pattern=code://stats/{stats_type})"

    def __repr__(self) -> str:
        """Detailed string representation of the resource"""
        return (
            f"ProjectStatsResource(uri_pattern={self._uri_pattern.pattern}, "
            f"project_path={self._project_path})"
        )
