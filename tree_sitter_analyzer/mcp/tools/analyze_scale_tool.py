#!/usr/bin/env python3
"""
Analyze Code Scale MCP Tool

This tool provides code scale analysis including metrics about
complexity, size, and structure through the MCP protocol.
Enhanced for LLM-friendly analysis workflow.
"""

from pathlib import Path
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils.file_metrics import compute_file_metrics
from ..utils.format_helper import apply_toon_format_to_response
from .analyze_scale_helpers import (
    extract_structural_overview,
    extract_structural_overview_universal,
    generate_llm_guidance,
)
from .base_tool import BaseMCPTool

# Set up logging
logger = setup_logger(__name__)


class AnalyzeScaleTool(BaseMCPTool):
    """
    MCP Tool for analyzing code scale and complexity metrics.

    This tool integrates with existing analyzer components to provide
    comprehensive code analysis through the MCP protocol, optimized
    for LLM workflow efficiency.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the analyze scale tool."""
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        logger.info("AnalyzeScaleTool initialized with security validation")

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Args:
            project_path: New project root directory
        """
        super().set_project_path(project_path)
        self.analysis_engine = get_analysis_engine(project_path)
        logger.info(f"AnalyzeScaleTool project path updated to: {project_path}")

    def _calculate_file_metrics(
        self, file_path: str, language: str | None = None
    ) -> dict[str, Any]:
        """
        Calculate file metrics using the unified implementation.

        Note: This retains the method name for backward compatibility within the tool,
        but delegates the computation to the shared module.
        """
        try:
            metrics = compute_file_metrics(
                file_path, language=language, project_root=self.project_root
            )
            # Keep historical convenience field
            file_size_bytes = int(metrics.get("file_size_bytes", 0))
            return {
                **metrics,
                "file_size_kb": round(file_size_bytes / 1024, 2),
            }
        except Exception as e:
            logger.error(f"Error calculating file metrics for {file_path}: {e}")
            return {
                "total_lines": 0,
                "code_lines": 0,
                "comment_lines": 0,
                "blank_lines": 0,
                "estimated_tokens": 0,
                "file_size_bytes": 0,
                "file_size_kb": 0,
            }

    def _extract_structural_overview(self, analysis_result: Any) -> dict[str, Any]:
        return extract_structural_overview(analysis_result)

    def _extract_structural_overview_universal(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        return extract_structural_overview_universal(analysis_result)

    @staticmethod
    def _count_elements(
        elements: list, element_type_const: str, element_type_str: str
    ) -> int:
        """Count elements matching either Java-style or universal element type."""
        count = 0
        for e in elements:
            if is_element_of_type(e, element_type_const):
                count += 1
            elif getattr(e, "element_type", "") == element_type_str:
                count += 1
        return count

    def _generate_llm_guidance(
        self, file_metrics: dict[str, Any], structural_overview: dict[str, Any]
    ) -> dict[str, Any]:
        return generate_llm_guidance(file_metrics, structural_overview)

    def get_tool_schema(self) -> dict[str, Any]:
        """
        Get the MCP tool schema for analyze_code_scale.

        Returns:
            Dictionary containing the tool schema
        """
        return {
            "type": "object",
            "properties": {
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Batch mode: list of file paths to compute metrics for (requires metrics_only=true)",
                },
                "metrics_only": {
                    "type": "boolean",
                    "description": "Batch mode: when true, compute file metrics only (no structural analysis)",
                    "default": False,
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the code file to analyze",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (optional, auto-detected if not specified)",
                },
                "include_complexity": {
                    "type": "boolean",
                    "description": "Include complexity metrics in the analysis",
                    "default": True,
                },
                "include_details": {
                    "type": "boolean",
                    "description": "Include detailed element information",
                    "default": False,
                },
                "include_guidance": {
                    "type": "boolean",
                    "description": "Include LLM analysis guidance",
                    "default": True,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, 50-70% token reduction) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the analyze_code_scale tool.

        Args:
            arguments: Tool arguments containing file_path and optional parameters

        Returns:
            Dictionary containing enhanced analysis results optimized for LLM workflow

        Raises:
            ValueError: If required arguments are missing or invalid
            FileNotFoundError: If the specified file doesn't exist
        """
        # Batch metrics mode
        if "file_paths" in arguments and arguments["file_paths"] is not None:
            return await self._execute_metrics_batch(arguments)

        # Single mode: Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        # include_complexity = arguments.get("include_complexity", True)  # Not used currently
        include_details = arguments.get("include_details", False)
        include_guidance = arguments.get("include_guidance", True)
        output_format = arguments.get("output_format", "toon")

        # Resolve + security validation with shared caching to avoid redundant checks
        resolved_file_path = self.resolve_and_validate_file_path(file_path)
        logger.info(f"Analyzing file: {file_path} (resolved to: {resolved_file_path})")

        # Sanitize inputs
        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)

        # Validate file exists
        if not Path(resolved_file_path).exists():
            raise ValueError(f"Invalid file path: File not found: {file_path}")

        # Detect language if not specified
        if not language:
            language = detect_language_from_file(
                resolved_file_path, project_root=self.project_root
            )
            if language == "unknown":
                raise ValueError(
                    f"Invalid file path: Unsupported language for file: {resolved_file_path}"
                )

        logger.info(
            f"Analyzing code scale for {resolved_file_path} (language: {language})"
        )

        try:
            # Use performance monitoring with proper context manager
            from ...mcp.utils import get_performance_monitor

            with get_performance_monitor().measure_operation(
                "analyze_code_scale_enhanced"
            ):
                # Calculate basic file metrics
                file_metrics = self._calculate_file_metrics(
                    resolved_file_path, language
                )

                # Handle JSON files specially - they don't need structural analysis
                if language == "json":
                    return self._create_json_file_analysis(
                        resolved_file_path,
                        file_metrics,
                        include_guidance,
                        output_format,
                    )

                # Use appropriate analyzer based on language
                if language == "java":
                    # Use AdvancedAnalyzer for comprehensive analysis
                    # Use unified analysis engine instead of deprecated advanced_analyzer
                    request = AnalysisRequest(
                        file_path=resolved_file_path,
                        language=language,
                        include_complexity=True,
                        include_details=True,
                    )
                    analysis_result = await self.analysis_engine.analyze(request)
                    if analysis_result is None:
                        raise RuntimeError(f"Failed to analyze file: {file_path}")
                    # Extract structural overview
                    structural_overview = self._extract_structural_overview(
                        analysis_result
                    )
                else:
                    # Use universal analysis_engine for other languages
                    request = AnalysisRequest(
                        file_path=resolved_file_path,
                        language=language,
                        include_details=include_details,
                    )
                    universal_result = await self.analysis_engine.analyze(request)
                    if not universal_result or not universal_result.success:
                        error_msg = (
                            universal_result.error_message or "Unknown error"
                            if universal_result
                            else "Unknown error"
                        )
                        raise RuntimeError(
                            f"Failed to analyze file with universal engine: {error_msg}"
                        )

                    # Adapt the result to a compatible structure for report generation
                    analysis_result = universal_result
                    structural_overview = self._extract_structural_overview_universal(
                        universal_result
                    )

                # Generate LLM guidance
                llm_guidance = None
                if include_guidance:
                    guidance_metrics = {**file_metrics, "language": language}
                    llm_guidance = self._generate_llm_guidance(
                        guidance_metrics, structural_overview
                    )

                # Build enhanced result structure
                elements = analysis_result.elements if analysis_result else []
                result = {
                    "success": True,
                    "file_path": file_path,
                    "language": language,
                    "file_metrics": file_metrics,
                    "summary": {
                        "classes": self._count_elements(
                            elements, ELEMENT_TYPE_CLASS, "class"
                        ),
                        "methods": self._count_elements(
                            elements, ELEMENT_TYPE_FUNCTION, "function"
                        ),
                        "fields": self._count_elements(
                            elements, ELEMENT_TYPE_VARIABLE, "variable"
                        ),
                        "imports": self._count_elements(
                            elements, ELEMENT_TYPE_IMPORT, "import"
                        ),
                        "annotations": len(
                            getattr(analysis_result, "annotations", [])
                            if analysis_result
                            else []
                        ),
                        "package": (
                            analysis_result.package.name
                            if analysis_result and analysis_result.package
                            else None
                        ),
                    },
                    "structural_overview": structural_overview,
                }

                if include_guidance:
                    result["llm_guidance"] = llm_guidance

                # Add detailed information if requested (backward compatibility)
                if include_details:
                    result["detailed_analysis"] = {
                        "statistics": (
                            analysis_result.get_statistics() if analysis_result else {}
                        ),
                        "classes": [
                            {
                                "name": cls.name,
                                "type": getattr(cls, "class_type", "unknown"),
                                "visibility": getattr(cls, "visibility", "unknown"),
                                "extends": getattr(cls, "extends_class", None),
                                "implements": getattr(cls, "implements_interfaces", []),
                                "annotations": [
                                    getattr(ann, "name", str(ann))
                                    for ann in getattr(cls, "annotations", [])
                                ],
                                "lines": f"{cls.start_line}-{cls.end_line}",
                            }
                            for cls in [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if is_element_of_type(e, ELEMENT_TYPE_CLASS)
                            ]
                        ],
                        "methods": [
                            {
                                "name": method.name,
                                "file_path": getattr(method, "file_path", file_path),
                                "visibility": getattr(method, "visibility", "unknown"),
                                "return_type": getattr(
                                    method, "return_type", "unknown"
                                ),
                                "parameters": len(getattr(method, "parameters", [])),
                                "annotations": [
                                    getattr(ann, "name", str(ann))
                                    for ann in getattr(method, "annotations", [])
                                ],
                                "is_constructor": getattr(
                                    method, "is_constructor", False
                                ),
                                "is_static": getattr(method, "is_static", False),
                                "complexity": getattr(method, "complexity_score", 0),
                                "lines": f"{method.start_line}-{method.end_line}",
                            }
                            for method in [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
                            ]
                        ],
                        "fields": [
                            {
                                "name": field.name,
                                "type": getattr(field, "field_type", "unknown"),
                                "file_path": getattr(field, "file_path", file_path),
                                "visibility": getattr(field, "visibility", "unknown"),
                                "is_static": getattr(field, "is_static", False),
                                "is_final": getattr(field, "is_final", False),
                                "annotations": [
                                    getattr(ann, "name", str(ann))
                                    for ann in getattr(field, "annotations", [])
                                ],
                                "lines": f"{field.start_line}-{field.end_line}",
                            }
                            for field in [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
                            ]
                        ],
                    }

                # Count elements by type
                classes_count = len(
                    [
                        e
                        for e in (analysis_result.elements if analysis_result else [])
                        if is_element_of_type(e, ELEMENT_TYPE_CLASS)
                    ]
                )
                methods_count = len(
                    [
                        e
                        for e in (analysis_result.elements if analysis_result else [])
                        if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
                    ]
                )

                logger.info(
                    f"Successfully analyzed {file_path}: {classes_count} classes, "
                    f"{methods_count} methods, {file_metrics['total_lines']} lines, "
                    f"~{file_metrics['estimated_tokens']} tokens"
                )

                # Apply TOON format to direct output if requested
                return apply_toon_format_to_response(result, output_format)

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            raise

    async def _execute_metrics_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Batch metrics mode (no structural analysis).

        Contract:
        - Default output_format is TOON.
        - When output_format='toon', response MUST NOT include detailed JSON fields like results.
        """
        output_format = arguments.get("output_format", "toon")
        metrics_only = bool(arguments.get("metrics_only", False))
        file_paths = arguments.get("file_paths")

        if not metrics_only:
            raise ValueError(
                "metrics_only must be true when using file_paths batch mode"
            )
        if not isinstance(file_paths, list) or not file_paths:
            raise ValueError("file_paths must be a non-empty list of strings")

        max_files = 200
        if len(file_paths) > max_files:
            raise ValueError(
                f"Too many files: {len(file_paths)} > max_files={max_files}"
            )

        import asyncio

        sem = asyncio.Semaphore(4)

        async def _one(fp: str) -> dict[str, Any]:
            async with sem:
                if not isinstance(fp, str) or not fp.strip():
                    return {
                        "file_path": fp,
                        "error": "file_path must be a non-empty string",
                    }
                try:
                    resolved = self.resolve_and_validate_file_path(fp)
                except ValueError as e:
                    return {"file_path": fp, "error": str(e)}

                if not Path(resolved).exists():
                    return {
                        "file_path": fp,
                        "resolved_path": resolved,
                        "error": "Invalid file path: file does not exist",
                    }

                lang: str | None = detect_language_from_file(
                    resolved, project_root=self.project_root
                )
                if lang == "unknown":
                    lang = None

                metrics = self._calculate_file_metrics(resolved, lang)
                return {
                    "file_path": fp,
                    "resolved_path": resolved,
                    "language": lang or "unknown",
                    "metrics": metrics,
                }

        per_file = await asyncio.gather(*[_one(fp) for fp in file_paths])
        errors = [x for x in per_file if "error" in x]
        ok = [x for x in per_file if "error" not in x]

        response: dict[str, Any] = {
            "success": len(ok) > 0,
            "count_files": len(file_paths),
            "count_ok": len(ok),
            "count_errors": len(errors),
            "limits": {"max_files": max_files, "concurrency": 4},
            "results": per_file,
        }
        return apply_toon_format_to_response(response, output_format)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments against the schema.

        Args:
            arguments: Arguments to validate

        Returns:
            True if arguments are valid

        Raises:
            ValueError: If arguments are invalid
        """
        # Batch mode validation
        if "file_paths" in arguments and arguments["file_paths"] is not None:
            if "file_path" in arguments:
                raise ValueError("file_paths is mutually exclusive with file_path")
            file_paths = arguments["file_paths"]
            if not isinstance(file_paths, list) or not file_paths:
                raise ValueError("file_paths must be a non-empty list")
            if not isinstance(arguments.get("metrics_only", False), bool):
                raise ValueError("metrics_only must be a boolean")
            if arguments.get("metrics_only", False) is not True:
                raise ValueError(
                    "metrics_only must be true when using file_paths batch mode"
                )
            return True

        # Single mode requires file_path
        if "file_path" not in arguments:
            raise ValueError("Required field 'file_path' is missing")

        # Validate file_path
        if "file_path" in arguments:
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

        if "include_complexity" in arguments:
            include_complexity = arguments["include_complexity"]
            if not isinstance(include_complexity, bool):
                raise ValueError("include_complexity must be a boolean")

        if "include_details" in arguments:
            include_details = arguments["include_details"]
            if not isinstance(include_details, bool):
                raise ValueError("include_details must be a boolean")

        if "include_guidance" in arguments:
            include_guidance = arguments["include_guidance"]
            if not isinstance(include_guidance, bool):
                raise ValueError("include_guidance must be a boolean")

        return True

    def _create_json_file_analysis(
        self,
        file_path: str,
        file_metrics: dict[str, Any],
        include_guidance: bool,
        output_format: str = "toon",
    ) -> dict[str, Any]:
        """
        Create analysis result for JSON files.

        Args:
            file_path: Path to the JSON file
            file_metrics: Basic file metrics
            include_guidance: Whether to include guidance
            output_format: Output format ('json' or 'toon')

        Returns:
            Analysis result for JSON file
        """
        result = {
            "success": True,
            "file_path": file_path,
            "language": "json",
            "file_size_bytes": file_metrics["file_size_bytes"],
            "total_lines": file_metrics["total_lines"],
            "non_empty_lines": file_metrics["total_lines"]
            - file_metrics["blank_lines"],
            "estimated_tokens": file_metrics["estimated_tokens"],
            "complexity_metrics": {
                "total_elements": 0,
                "max_depth": 0,
                "avg_complexity": 0.0,
            },
            "structural_overview": {
                "classes": [],
                "methods": [],
                "fields": [],
            },
            "scale_category": (
                "small"
                if file_metrics["total_lines"] < 100
                else "medium"
                if file_metrics["total_lines"] < 1000
                else "large"
            ),
            "analysis_recommendations": {
                "suitable_for_full_analysis": file_metrics["total_lines"] < 1000,
                "recommended_approach": "JSON files are configuration/data files - structural analysis not applicable",
                "token_efficiency_notes": (  # nosec B105
                    "JSON files can be read directly without tree-sitter parsing"
                ),
            },
        }

        if include_guidance:
            result["llm_analysis_guidance"] = {
                "file_characteristics": "JSON configuration/data file",
                "recommended_workflow": "Direct file reading for content analysis",
                "token_optimization": (  # nosec B105
                    "Use simple file reading tools for JSON content"
                ),
                "analysis_focus": "Data structure and configuration values",
            }

        # Apply TOON format to direct output if requested
        return apply_toon_format_to_response(result, output_format)

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for check_code_scale.

        Returns:
            Tool definition dictionary compatible with MCP server
        """
        return {
            "name": "check_code_scale",
            "description": (
                "SMART Workflow 'Analyze' step (use FIRST for any file): "
                "Get file size, element counts (classes/methods/fields/imports), "
                "complexity metrics, and LLM-optimized analysis guidance. "
                "Use this BEFORE analyze_code_structure to decide the right strategy. "
                "Supports batch mode for multiple files and token-aware recommendations."
            ),
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy access
analyze_scale_tool = AnalyzeScaleTool()
