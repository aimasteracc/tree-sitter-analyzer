#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universal Code Analysis Tool for MCP

This tool provides universal code analysis capabilities for multiple programming
languages using the existing language detection and analysis infrastructure.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    get_analysis_engine,
)
from ...core.analysis_engine import get_analysis_engine, AnalysisRequest
from ...language_detector import detect_language_from_file, is_language_supported
from ..utils.error_handler import handle_mcp_errors
from ..utils import get_performance_monitor

logger = logging.getLogger(__name__)


class UniversalAnalyzeTool:
    """
    Universal code analysis tool for multiple programming languages

    This tool automatically detects the programming language and applies
    the appropriate analyzer to provide comprehensive code analysis.
    """

    def __init__(self) -> None:
        """Initialize the universal analysis tool"""
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer
        self.analysis_engine = get_analysis_engine()

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get MCP tool definition for universal code analysis

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "analyze_code_universal",
            "description": "Universal code analysis for multiple programming languages with automatic language detection",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the code file to analyze",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (optional, auto-detected if not specified)",
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["basic", "detailed", "structure", "metrics"],
                        "description": "Type of analysis to perform",
                        "default": "basic",
                    },
                    "include_ast": {
                        "type": "boolean",
                        "description": "Include AST information in the analysis",
                        "default": False,
                    },
                    "include_queries": {
                        "type": "boolean",
                        "description": "Include available query information",
                        "default": False,
                    },
                },
                "required": ["file_path"],
                "additionalProperties": False,
            },
        }


    @handle_mcp_errors("universal_analyze")
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute universal code analysis

        Args:
            arguments: Tool arguments containing file_path and optional parameters

        Returns:
            Dictionary containing analysis results

        Raises:
            ValueError: If required arguments are missing or invalid
            FileNotFoundError: If the specified file doesn't exist
        """
        # Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        analysis_type = arguments.get("analysis_type", "basic")
        include_ast = arguments.get("include_ast", False)
        include_queries = arguments.get("include_queries", False)

        # Validate file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language if not specified
        if not language:
            language = detect_language_from_file(file_path)
            if language == "unknown":
                raise ValueError(f"Could not detect language for file: {file_path}")

        # Check if language is supported
        if not is_language_supported(language):
            raise ValueError(f"Language '{language}' is not supported by tree-sitter")

        # Validate analysis_type
        valid_analysis_types = ["basic", "detailed", "structure", "metrics"]
        if analysis_type not in valid_analysis_types:
            raise ValueError(
                f"Invalid analysis_type '{analysis_type}'. Valid types: {', '.join(valid_analysis_types)}"
            )

        logger.info(
            f"Analyzing {file_path} (language: {language}, type: {analysis_type})"
        )

        try:
            monitor = get_performance_monitor()
            with monitor.measure_operation("universal_analyze"):
                # Get appropriate analyzer
                if language == "java":
                    # Use advanced analyzer for Java
                    result = await self._analyze_with_advanced_analyzer(
                        file_path, language, analysis_type, include_ast
                    )
                else:
                    # Use universal analyzer for other languages
                    result = await self._analyze_with_universal_analyzer(
                        file_path, language, analysis_type, include_ast
                    )

                # Add query information if requested
                if include_queries:
                    result["available_queries"] = await self._get_available_queries(
                        language
                    )

                logger.info(f"Successfully analyzed {file_path}")
                return result

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            raise

    async def _analyze_with_advanced_analyzer(
        self, file_path: str, language: str, analysis_type: str, include_ast: bool
    ) -> Dict[str, Any]:
        """
        Analyze using the advanced analyzer (Java-specific)

        Args:
            file_path: Path to the file to analyze
            language: Programming language
            analysis_type: Type of analysis to perform
            include_ast: Whether to include AST information

        Returns:
            Analysis results dictionary
        """
        # Use unified analysis engine instead of deprecated advanced_analyzer
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_complexity=True,
            include_details=True
        )
        analysis_result = await self.analysis_engine.analyze(request)

        if analysis_result is None:
            raise RuntimeError(f"Failed to analyze file: {file_path}")

        # Build base result
        result: Dict[str, Any] = {
            "file_path": file_path,
            "language": language,
            "analyzer_type": "advanced",
            "analysis_type": analysis_type,
        }

        if analysis_type == "basic":
            result.update(self._extract_basic_metrics(analysis_result))
        elif analysis_type == "detailed":
            result.update(self._extract_detailed_metrics(analysis_result))
        elif analysis_type == "structure":
            result.update(self._extract_structure_info(analysis_result))
        elif analysis_type == "metrics":
            result.update(self._extract_comprehensive_metrics(analysis_result))

        if include_ast:
            result["ast_info"] = {
                "node_count": getattr(
                    analysis_result, "line_count", 0
                ),  # Approximation
                "depth": 0,  # Advanced analyzer doesn't provide this, use 0 instead of string
            }

        return result

    async def _analyze_with_universal_analyzer(
        self, file_path: str, language: str, analysis_type: str, include_ast: bool
    ) -> Dict[str, Any]:
        """
        Analyze using the universal analyzer

        Args:
            file_path: Path to the file to analyze
            language: Programming language
            analysis_type: Type of analysis to perform
            include_ast: Whether to include AST information

        Returns:
            Analysis results dictionary
        """
        request = AnalysisRequest(
            file_path=file_path,
            language=language,
            include_details=(analysis_type == "detailed"),
        )
        analysis_result = await self.analysis_engine.analyze(request)

        if not analysis_result or not analysis_result.success:
            error_message = (
                analysis_result.error_message if analysis_result else "Unknown error"
            )
            raise RuntimeError(
                f"Failed to analyze file: {file_path} - {error_message}"
            )

        # Convert AnalysisResult to dictionary for consistent processing
        analysis_dict = analysis_result.to_dict()

        # Build base result
        result: Dict[str, Any] = {
            "file_path": file_path,
            "language": language,
            "analyzer_type": "universal",
            "analysis_type": analysis_type,
        }

        if analysis_type == "basic":
            result.update(self._extract_universal_basic_metrics(analysis_dict))
        elif analysis_type == "detailed":
            result.update(self._extract_universal_detailed_metrics(analysis_dict))
        elif analysis_type == "structure":
            result.update(self._extract_universal_structure_info(analysis_dict))
        elif analysis_type == "metrics":
            result.update(
                self._extract_universal_comprehensive_metrics(analysis_dict)
            )

        if include_ast:
            result["ast_info"] = analysis_dict.get("ast_info", {})

        return result

    def _extract_basic_metrics(self, analysis_result: Any) -> Dict[str, Any]:
        """Extract basic metrics from advanced analyzer result"""
        stats = analysis_result.get_statistics()

        return {
            "metrics": {
                "lines_total": analysis_result.line_count,
                "lines_code": stats.get("lines_of_code", 0),
                "lines_comment": stats.get("comment_lines", 0),
                "lines_blank": stats.get("blank_lines", 0),
                "elements": {
                    "classes": len([e for e in analysis_result.elements if e.__class__.__name__ == 'Class']),
                    "methods": len([e for e in analysis_result.elements if e.__class__.__name__ == 'Function']),
                    "fields": len([e for e in analysis_result.elements if e.__class__.__name__ == 'Variable']),
                    "imports": len([e for e in analysis_result.elements if e.__class__.__name__ == 'Import']),
                    "annotations": len(getattr(analysis_result, "annotations", [])),
                },
            }
        }

    def _extract_detailed_metrics(self, analysis_result: Any) -> Dict[str, Any]:
        """Extract detailed metrics from advanced analyzer result"""
        basic = self._extract_basic_metrics(analysis_result)

        # Add complexity metrics
        methods = [e for e in analysis_result.elements if e.__class__.__name__ == 'Function']
        total_complexity = sum(
            getattr(method, 'complexity_score', 0) or 0 for method in methods
        )

        basic["metrics"]["complexity"] = {
            "total": total_complexity,
            "average": (
                total_complexity / len(methods)
                if methods
                else 0
            ),
            "max": max(
                (getattr(method, 'complexity_score', 0) or 0 for method in methods),
                default=0,
            ),
        }

        return basic

    def _extract_structure_info(self, analysis_result: Any) -> Dict[str, Any]:
        """Extract structure information from advanced analyzer result"""
        return {
            "structure": {
                "package": (
                    analysis_result.package.name if analysis_result.package else None
                ),
                "classes": [cls.to_summary_item() if hasattr(cls, 'to_summary_item') else {'name': getattr(cls, 'name', 'unknown')} for cls in [e for e in analysis_result.elements if e.__class__.__name__ == 'Class']],
                "methods": [
                    method.to_summary_item() if hasattr(method, 'to_summary_item') else {'name': getattr(method, 'name', 'unknown')} for method in [e for e in analysis_result.elements if e.__class__.__name__ == 'Function']
                ],
                "fields": [field.to_summary_item() if hasattr(field, 'to_summary_item') else {'name': getattr(field, 'name', 'unknown')} for field in [e for e in analysis_result.elements if e.__class__.__name__ == 'Variable']],
                "imports": [imp.to_summary_item() if hasattr(imp, 'to_summary_item') else {'name': getattr(imp, 'name', 'unknown')} for imp in [e for e in analysis_result.elements if e.__class__.__name__ == 'Import']],
                "annotations": [
                    ann.to_summary_item() if hasattr(ann, 'to_summary_item') else {'name': getattr(ann, 'name', 'unknown')} for ann in getattr(analysis_result, "annotations", [])
                ],
            }
        }

    def _extract_comprehensive_metrics(self, analysis_result: Any) -> Dict[str, Any]:
        """Extract comprehensive metrics from advanced analyzer result"""
        detailed = self._extract_detailed_metrics(analysis_result)
        structure = self._extract_structure_info(analysis_result)

        # Combine both
        result = detailed.copy()
        result.update(structure)

        return result

    def _extract_universal_basic_metrics(
        self, analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract basic metrics from universal analyzer result"""
        elements = analysis_result.get("elements", [])
        return {
            "metrics": {
                "lines_total": analysis_result.get("line_count", 0),
                "lines_code": analysis_result.get("line_count", 0),  # Approximation
                "lines_comment": 0,  # Not available in universal analyzer
                "lines_blank": 0,    # Not available in universal analyzer
                "elements": {
                    "classes": len([e for e in elements if e.get("__class__", "") == "Class"]),
                    "methods": len([e for e in elements if e.get("__class__", "") == "Function"]),
                    "fields": len([e for e in elements if e.get("__class__", "") == "Variable"]),
                    "imports": len([e for e in elements if e.get("__class__", "") == "Import"]),
                    "annotations": 0,  # Not available in universal analyzer
                },
            }
        }

    def _extract_universal_detailed_metrics(
        self, analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract detailed metrics from universal analyzer result"""
        basic = self._extract_universal_basic_metrics(analysis_result)

        # Add query results if available
        if "query_results" in analysis_result:
            basic["query_results"] = analysis_result["query_results"]

        return basic

    def _extract_universal_structure_info(
        self, analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract structure information from universal analyzer result"""
        return {
            "structure": analysis_result.get("structure", {}),
            "queries_executed": analysis_result.get("queries_executed", []),
        }

    def _extract_universal_comprehensive_metrics(
        self, analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract comprehensive metrics from universal analyzer result"""
        detailed = self._extract_universal_detailed_metrics(analysis_result)
        structure = self._extract_universal_structure_info(analysis_result)

        # Combine both
        result = detailed.copy()
        result.update(structure)

        return result

    async def _get_available_queries(self, language: str) -> Dict[str, Any]:
        """
        Get available queries for the specified language

        Args:
            language: Programming language

        Returns:
            Dictionary containing available queries information
        """
        try:
            if language == "java":
                # For Java, we don't have predefined queries in the advanced analyzer
                return {
                    "language": language,
                    "queries": [],
                    "note": "Advanced analyzer uses built-in analysis logic",
                }
            else:
                # For other languages, get from universal analyzer
                queries = self.analysis_engine.get_supported_languages()
                return {"language": language, "queries": queries, "count": len(queries)}
        except Exception as e:
            logger.warning(f"Failed to get queries for {language}: {e}")
            return {"language": language, "queries": [], "error": str(e)}

    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        Validate tool arguments against the schema.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # Check required fields
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")

        # Validate file_path
        file_path = arguments["file_path"]
        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")
        if not file_path.strip():
            raise ValueError("file_path cannot be empty")

        # Validate optional fields
        if "language" in arguments:
            language = arguments["language"]
            if not isinstance(language, str):
                raise ValueError("language must be a string")

        if "analysis_type" in arguments:
            analysis_type = arguments["analysis_type"]
            if not isinstance(analysis_type, str):
                raise ValueError("analysis_type must be a string")
            valid_types = ["basic", "detailed", "structure", "metrics"]
            if analysis_type not in valid_types:
                raise ValueError(f"analysis_type must be one of {valid_types}")

        if "include_ast" in arguments:
            include_ast = arguments["include_ast"]
            if not isinstance(include_ast, bool):
                raise ValueError("include_ast must be a boolean")

        if "include_queries" in arguments:
            include_queries = arguments["include_queries"]
            if not isinstance(include_queries, bool):
                raise ValueError("include_queries must be a boolean")

        return True
