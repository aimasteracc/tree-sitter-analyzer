#!/usr/bin/env python3
"""
Analyze Code Scale MCP Tool

This tool provides code scale analysis including metrics about
complexity, size, and structure through the MCP protocol.
Enhanced for LLM-friendly analysis workflow.
"""

import re
from pathlib import Path
from typing import Any

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...security import SecurityValidator
from ...utils import setup_logger
from ..utils.path_resolver import PathResolver

# Set up logging
logger = setup_logger(__name__)


class AnalyzeScaleTool:
    """
    MCP Tool for analyzing code scale and complexity metrics.

    This tool integrates with existing analyzer components to provide
    comprehensive code analysis through the MCP protocol, optimized
    for LLM workflow efficiency.
    """

    def __init__(self, project_root: str = None) -> None:
        """Initialize the analyze scale tool."""
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer
        self.project_root = project_root
        self.analysis_engine = get_analysis_engine(project_root)
        self.security_validator = SecurityValidator(project_root)
        self.path_resolver = PathResolver(project_root)
        logger.info("AnalyzeScaleTool initialized with security validation")

    def _calculate_file_metrics(self, file_path: str) -> dict[str, Any]:
        """
        Calculate basic file metrics including line counts and estimated token count.

        Args:
            file_path: Path to the file to analyze

        Returns:
            Dictionary containing file metrics
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            lines = content.split("\n")
            total_lines = len(lines)

            # Count different types of lines
            code_lines = 0
            comment_lines = 0
            blank_lines = 0

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    blank_lines += 1
                elif (
                    stripped.startswith("//")
                    or stripped.startswith("/*")
                    or stripped.startswith("*")
                ):
                    comment_lines += 1
                else:
                    code_lines += 1

            # Estimate token count (rough approximation)
            # Split by common delimiters and count non-empty tokens
            tokens = re.findall(r"\b\w+\b|[^\w\s]", content)
            estimated_tokens = len([t for t in tokens if t.strip()])

            # Calculate file size
            file_size = len(content.encode("utf-8"))

            return {
                "total_lines": total_lines,
                "code_lines": code_lines,
                "comment_lines": comment_lines,
                "blank_lines": blank_lines,
                "estimated_tokens": estimated_tokens,
                "file_size_bytes": file_size,
                "file_size_kb": round(file_size / 1024, 2),
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
        """
        Extract structural overview with position information for LLM guidance.

        Args:
            analysis_result: Result from AdvancedAnalyzer

        Returns:
            Dictionary containing structural overview
        """
        overview: dict[str, Any] = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }

        # Extract class information with position from unified analysis engine
        classes = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Class"
        ]
        for cls in classes:
            class_info = {
                "name": cls.name,
                "type": cls.class_type,
                "start_line": cls.start_line,
                "end_line": cls.end_line,
                "line_span": cls.end_line - cls.start_line + 1,
                "visibility": cls.visibility,
                "extends": cls.extends_class,
                "implements": cls.implements_interfaces,
                "annotations": [ann.name for ann in cls.annotations],
            }
            overview["classes"].append(class_info)

        # Extract method information with position and complexity from unified analysis engine
        methods = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Function"
        ]
        for method in methods:
            method_info = {
                "name": method.name,
                "start_line": method.start_line,
                "end_line": method.end_line,
                "line_span": method.end_line - method.start_line + 1,
                "visibility": method.visibility,
                "return_type": method.return_type,
                "parameter_count": len(method.parameters),
                "complexity": method.complexity_score,
                "is_constructor": method.is_constructor,
                "is_static": method.is_static,
                "annotations": [ann.name for ann in method.annotations],
            }
            overview["methods"].append(method_info)

            # Track complexity hotspots
            if method.complexity_score > 10:  # High complexity threshold
                overview["complexity_hotspots"].append(
                    {
                        "type": "method",
                        "name": method.name,
                        "complexity": method.complexity_score,
                        "start_line": method.start_line,
                        "end_line": method.end_line,
                    }
                )

        # Extract field information with position
        # Extract field information from unified analysis engine
        fields = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Variable"
        ]
        for field in fields:
            field_info = {
                "name": field.name,
                "type": field.field_type,
                "start_line": field.start_line,
                "end_line": field.end_line,
                "visibility": field.visibility,
                "is_static": field.is_static,
                "is_final": field.is_final,
                "annotations": [ann.name for ann in field.annotations],
            }
            overview["fields"].append(field_info)

        # Extract import information
        # Extract import information from unified analysis engine
        imports = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Import"
        ]
        for imp in imports:
            import_info = {
                "name": imp.imported_name,
                "statement": imp.import_statement,
                "line": imp.line_number,
                "is_static": imp.is_static,
                "is_wildcard": imp.is_wildcard,
            }
            overview["imports"].append(import_info)

        return overview

    def _generate_llm_guidance(
        self, file_metrics: dict[str, Any], structural_overview: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate guidance for LLM on how to efficiently analyze this file.

        Args:
            file_metrics: Basic file metrics
            structural_overview: Structural overview of the code

        Returns:
            Dictionary containing LLM guidance
        """
        guidance: dict[str, Any] = {
            "analysis_strategy": "",
            "recommended_tools": [],
            "key_areas": [],
            "complexity_assessment": "",
            "size_category": "",
        }

        total_lines = file_metrics["total_lines"]
        # estimated_tokens = file_metrics["estimated_tokens"]  # Not used currently

        # Determine size category
        if total_lines < 100:
            guidance["size_category"] = "small"
            guidance["analysis_strategy"] = (
                "This is a small file that can be analyzed in full detail."
            )
        elif total_lines < 500:
            guidance["size_category"] = "medium"
            guidance["analysis_strategy"] = (
                "This is a medium-sized file. Consider focusing on key classes and methods."
            )
        elif total_lines < 1500:
            guidance["size_category"] = "large"
            guidance["analysis_strategy"] = (
                "This is a large file. Use targeted analysis with read_code_partial."
            )
        else:
            guidance["size_category"] = "very_large"
            guidance["analysis_strategy"] = (
                "This is a very large file. Strongly recommend using structural analysis first, then targeted deep-dives."
            )

        # Recommend tools based on file size and complexity
        if total_lines > 200:
            guidance["recommended_tools"].append("read_code_partial")

        # Ensure all required fields exist
        required_fields = [
            "complexity_hotspots",
            "classes",
            "methods",
            "fields",
            "imports",
        ]
        for field in required_fields:
            if field not in structural_overview:
                structural_overview[field] = []

        if len(structural_overview["complexity_hotspots"]) > 0:
            guidance["recommended_tools"].append("format_table")
            guidance["complexity_assessment"] = (
                f"Found {len(structural_overview['complexity_hotspots'])} complexity hotspots"
            )
        else:
            guidance["complexity_assessment"] = (
                "No significant complexity hotspots detected"
            )

        # Identify key areas for analysis
        if len(structural_overview["classes"]) > 1:
            guidance["key_areas"].append(
                "Multiple classes - consider analyzing class relationships"
            )

        if len(structural_overview["methods"]) > 20:
            guidance["key_areas"].append(
                "Many methods - focus on public interfaces and high-complexity methods"
            )

        if len(structural_overview["imports"]) > 10:
            guidance["key_areas"].append("Many imports - consider dependency analysis")

        return guidance

    def get_tool_schema(self) -> dict[str, Any]:
        """
        Get the MCP tool schema for analyze_code_scale.

        Returns:
            Dictionary containing the tool schema
        """
        return {
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
            },
            "required": ["file_path"],
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
        # Validate required arguments
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        file_path = arguments["file_path"]
        language = arguments.get("language")
        # include_complexity = arguments.get("include_complexity", True)  # Not used currently
        include_details = arguments.get("include_details", False)
        include_guidance = arguments.get("include_guidance", True)

        # Resolve file path to absolute path
        resolved_file_path = self.path_resolver.resolve(file_path)
        logger.info(f"Analyzing file: {file_path} (resolved to: {resolved_file_path})")

        # Security validation using resolved path
        is_valid, error_msg = self.security_validator.validate_file_path(
            resolved_file_path
        )
        if not is_valid:
            logger.warning(
                f"Security validation failed for file path: {resolved_file_path} - {error_msg}"
            )
            raise ValueError(f"Invalid file path: {error_msg}")

        # Sanitize inputs
        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)

        # Validate file exists
        if not Path(resolved_file_path).exists():
            raise ValueError("Invalid file path: file does not exist")

        # Detect language if not specified
        if not language:
            language = detect_language_from_file(resolved_file_path)
            if language == "unknown":
                raise ValueError(
                    f"Could not detect language for file: {resolved_file_path}"
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
                file_metrics = self._calculate_file_metrics(resolved_file_path)

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
                            universal_result.error_message
                            if universal_result
                            else "Unknown error"
                        )
                        raise RuntimeError(
                            f"Failed to analyze file with universal engine: {error_msg}"
                        )

                    # Adapt the result to a compatible structure for report generation
                    # This part needs careful implementation based on universal_result structure
                    analysis_result = None  # Placeholder
                    structural_overview = {}  # Placeholder

                # Generate LLM guidance
                llm_guidance = None
                if include_guidance:
                    llm_guidance = self._generate_llm_guidance(
                        file_metrics, structural_overview
                    )

                # Build enhanced result structure
                result = {
                    "file_path": file_path,
                    "language": language,
                    "file_metrics": file_metrics,
                    "summary": {
                        "classes": len(
                            [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if e.__class__.__name__ == "Class"
                            ]
                        ),
                        "methods": len(
                            [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if e.__class__.__name__ == "Function"
                            ]
                        ),
                        "fields": len(
                            [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if e.__class__.__name__ == "Variable"
                            ]
                        ),
                        "imports": len(
                            [
                                e
                                for e in (
                                    analysis_result.elements if analysis_result else []
                                )
                                if e.__class__.__name__ == "Import"
                            ]
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
                                if e.__class__.__name__ == "Class"
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
                                if e.__class__.__name__ == "Function"
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
                                if e.__class__.__name__ == "Variable"
                            ]
                        ],
                    }

                # Count elements by type
                classes_count = len(
                    [
                        e
                        for e in (analysis_result.elements if analysis_result else [])
                        if e.__class__.__name__ == "Class"
                    ]
                )
                methods_count = len(
                    [
                        e
                        for e in (analysis_result.elements if analysis_result else [])
                        if e.__class__.__name__ == "Function"
                    ]
                )

                logger.info(
                    f"Successfully analyzed {file_path}: {classes_count} classes, "
                    f"{methods_count} methods, {file_metrics['total_lines']} lines, "
                    f"~{file_metrics['estimated_tokens']} tokens"
                )

                return result

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            raise

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
        schema = self.get_tool_schema()
        required_fields = schema.get("required", [])

        # Check required fields
        for field in required_fields:
            if field not in arguments:
                raise ValueError(f"Required field '{field}' is missing")

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

    def get_tool_definition(self) -> Any:
        """
        Get the MCP tool definition for analyze_code_scale.

        Returns:
            Tool definition object compatible with MCP server
        """
        try:
            from mcp.types import Tool

            return Tool(
                name="analyze_code_scale",
                description="Analyze code scale, complexity, and structure metrics with LLM-optimized guidance for efficient large file analysis",
                inputSchema=self.get_tool_schema(),
            )
        except ImportError:
            # Fallback for when MCP is not available
            return {
                "name": "analyze_code_scale",
                "description": "Analyze code scale, complexity, and structure metrics with LLM-optimized guidance for efficient large file analysis",
                "inputSchema": self.get_tool_schema(),
            }


# Tool instance for easy access
analyze_scale_tool = AnalyzeScaleTool()
