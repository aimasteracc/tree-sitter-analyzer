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
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    get_analysis_engine,
)
from tree_sitter_analyzer.language_detector import (
    detect_language_from_file,
    is_language_supported,
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
        return bool(self._uri_pattern.match(uri))

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
        match = self._uri_pattern.match(uri)
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
        Check if the file is a supported code file using language detection

        Args:
            file_path: Path to the file

        Returns:
            True if the file is a supported code file
        """
        try:
            language = detect_language_from_file(str(file_path))
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
            return detect_language_from_file(str(file_path))
        except Exception:
            return "unknown"

    async def _generate_overview_stats(self) -> dict[str, Any]:
        """
        Generate overview statistics for the project

        Returns:
            Dictionary containing overview statistics
        """
        logger.debug("Generating overview statistics")

        # Scan project directory for actual file counts
        if self._project_path is None:
            raise ValueError("Project path is not set")
        project_dir = Path(self._project_path)
        total_files = 0
        total_lines = 0
        language_counts: dict[str, int] = {}

        for file_path in project_dir.rglob("*"):
            if file_path.is_file() and self._is_supported_code_file(file_path):
                total_files += 1
                try:
                    with open(file_path, encoding="utf-8") as f:
                        file_lines = sum(1 for _ in f)
                        total_lines += file_lines
                except Exception as e:
                    logger.debug(
                        f"Skipping unreadable file during overview scan: {file_path} ({e})"
                    )
                    continue
                language = self._get_language_from_file(file_path)
                if language != "unknown":
                    language_counts[language] = language_counts.get(language, 0) + 1

        analysis_result = {
            "total_files": total_files,
            "total_lines": total_lines,
            "languages": [
                {"name": lang, "file_count": count}
                for lang, count in language_counts.items()
            ],
        }

        # Extract overview information
        languages_data = analysis_result.get("languages", [])
        if languages_data is None:
            languages_data = []

        # Ensure languages_data is a list for iteration
        if not isinstance(languages_data, list):
            languages_data = []

        overview = {
            "total_files": analysis_result.get("total_files", 0),
            "total_lines": analysis_result.get("total_lines", 0),
            "languages": [
                str(lang["name"])
                for lang in languages_data
                if isinstance(lang, dict) and "name" in lang
            ],
            "project_path": self._project_path,
            "last_updated": datetime.now().isoformat(),
        }

        logger.debug(f"Generated overview with {overview['total_files']} files")
        return overview

    async def _generate_languages_stats(self) -> dict[str, Any]:
        """
        Generate language-specific statistics

        Returns:
            Dictionary containing language statistics
        """
        logger.debug("Generating language statistics")

        # Scan project directory for actual language counts
        if self._project_path is None:
            raise ValueError("Project path is not set")
        project_dir = Path(self._project_path)
        total_files = 0
        total_lines = 0
        language_data = {}

        for file_path in project_dir.rglob("*"):
            if file_path.is_file() and self._is_supported_code_file(file_path):
                total_files += 1
                try:
                    with open(file_path, encoding="utf-8") as f:
                        file_lines = sum(1 for _ in f)
                        total_lines += file_lines
                except Exception as e:
                    logger.debug(f"Failed to count lines for {file_path}: {e}")
                    file_lines = 0

                language = self._get_language_from_file(file_path)
                if language != "unknown":
                    if language not in language_data:
                        language_data[language] = {"file_count": 0, "line_count": 0}
                    language_data[language]["file_count"] += 1
                    language_data[language]["line_count"] += file_lines

        # Convert to list format and calculate percentages
        languages_list = []
        for lang, data in language_data.items():
            percentage = (
                round((data["line_count"] / total_lines) * 100, 2)
                if total_lines > 0
                else 0.0
            )
            languages_list.append(
                {
                    "name": lang,
                    "file_count": data["file_count"],
                    "line_count": data["line_count"],
                    "percentage": percentage,
                }
            )

        languages_stats = {
            "languages": languages_list,
            "total_languages": len(languages_list),
            "last_updated": datetime.now().isoformat(),
        }

        logger.debug(f"Generated stats for {len(languages_list)} languages")
        return languages_stats

    async def _generate_complexity_stats(self) -> dict[str, Any]:
        """
        Generate complexity statistics

        Returns:
            Dictionary containing complexity statistics
        """
        logger.debug("Generating complexity statistics")

        # Analyze files for complexity
        if self._project_path is None:
            raise ValueError("Project path is not set")
        project_dir = Path(self._project_path)
        complexity_data = []
        total_complexity = 0
        max_complexity = 0
        file_count = 0

        # Analyze each supported code file
        for file_path in project_dir.rglob("*"):
            if file_path.is_file() and self._is_supported_code_file(file_path):
                try:
                    language = self._get_language_from_file(file_path)

                    # Use appropriate analyzer based on language
                    if language == "java":
                        # Use analysis engine for Java
                        file_analysis = await self.analysis_engine.analyze_file(
                            str(file_path)
                        )
                        if file_analysis and hasattr(file_analysis, "methods"):
                            # Extract complexity from methods if available
                            complexity = sum(
                                method.complexity_score or 0
                                for method in file_analysis.methods
                            )
                        elif file_analysis and hasattr(file_analysis, "elements"):
                            # Extract complexity from elements for new architecture
                            methods = [
                                e
                                for e in file_analysis.elements
                                if hasattr(e, "complexity_score")
                            ]
                            complexity = sum(
                                getattr(method, "complexity_score", 0) or 0
                                for method in methods
                            )
                        else:
                            complexity = 0
                    else:
                        # Use universal analyzer for other languages
                        request = AnalysisRequest(
                            file_path=str(file_path), language=language
                        )
                        file_analysis_result = await self.analysis_engine.analyze(
                            request
                        )

                        complexity = 0
                        if file_analysis_result and file_analysis_result.success:
                            analysis_dict = file_analysis_result.to_dict()
                            # Assuming complexity is part of the metrics in the new structure
                            if (
                                "metrics" in analysis_dict
                                and "complexity" in analysis_dict["metrics"]
                            ):
                                complexity = analysis_dict["metrics"]["complexity"].get(
                                    "total", 0
                                )

                    if complexity > 0:
                        complexity_data.append(
                            {
                                "file": str(file_path.relative_to(project_dir)),
                                "language": language,
                                "complexity": complexity,
                            }
                        )

                        total_complexity += complexity
                        max_complexity = max(max_complexity, complexity)
                        file_count += 1

                except Exception as e:
                    logger.warning(f"Failed to analyze complexity for {file_path}: {e}")
                    continue

        # Calculate average complexity
        avg_complexity = total_complexity / file_count if file_count > 0 else 0

        complexity_stats = {
            "average_complexity": round(avg_complexity, 2),
            "max_complexity": max_complexity,
            "total_files_analyzed": file_count,
            "files_by_complexity": sorted(
                complexity_data,
                key=lambda x: int(cast(int, x.get("complexity", 0))),
                reverse=True,
            ),
            "last_updated": datetime.now().isoformat(),
        }

        logger.debug(f"Generated complexity stats for {file_count} files")
        return complexity_stats

    async def _generate_files_stats(self) -> dict[str, Any]:
        """
        Generate file-level statistics

        Returns:
            Dictionary containing file statistics
        """
        logger.debug("Generating file statistics")

        # Get detailed file information
        files_data = []
        if self._project_path is None:
            raise ValueError("Project path is not set")
        project_dir = Path(self._project_path)

        # Analyze each supported code file
        for file_path in project_dir.rglob("*"):
            if file_path.is_file() and self._is_supported_code_file(file_path):
                try:
                    # Get file stats
                    file_stats = file_path.stat()

                    # Determine language using language detector
                    language = self._get_language_from_file(file_path)

                    # Count lines
                    try:
                        with open(file_path, encoding="utf-8") as f:
                            line_count = sum(1 for _ in f)
                    except Exception:
                        line_count = 0

                    files_data.append(
                        {
                            "path": str(file_path.relative_to(project_dir)),
                            "language": language,
                            "line_count": line_count,
                            "size_bytes": file_stats.st_size,
                            "modified": datetime.fromtimestamp(
                                file_stats.st_mtime
                            ).isoformat(),
                        }
                    )

                except Exception as e:
                    logger.warning(f"Failed to get stats for {file_path}: {e}")
                    continue

        files_stats = {
            "files": sorted(
                files_data,
                key=lambda x: int(cast(int, x.get("line_count", 0))),
                reverse=True,
            ),
            "total_count": len(files_data),
            "last_updated": datetime.now().isoformat(),
        }

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

        # Generate statistics based on type
        try:
            if stats_type == "overview":
                stats_data = await self._generate_overview_stats()
            elif stats_type == "languages":
                stats_data = await self._generate_languages_stats()
            elif stats_type == "complexity":
                stats_data = await self._generate_complexity_stats()
            elif stats_type == "files":
                stats_data = await self._generate_files_stats()
            else:
                raise ValueError(f"Unknown statistics type: {stats_type}")

            # Convert to JSON
            json_content = json.dumps(stats_data, indent=2, ensure_ascii=False)
            logger.debug(f"Successfully generated {stats_type} statistics")
            return json_content

        except Exception as e:
            logger.error(f"Failed to generate {stats_type} statistics: {e}")
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
