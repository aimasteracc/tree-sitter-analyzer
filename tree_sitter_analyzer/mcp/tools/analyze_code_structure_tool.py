#!/usr/bin/env python3
"""
Code Structure Analysis Tool for MCP

This tool analyzes code structure and generates detailed overview tables
(classes, methods, fields) with line positions for large files.
"""

from pathlib import Path
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...formatters.formatter_registry import FormatterRegistry
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils import get_performance_monitor
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

# Set up logging
logger = setup_logger(__name__)


class AnalyzeCodeStructureTool(BaseMCPTool):
    """
    MCP Tool for code structure analysis and table formatting.

    This tool integrates with existing analyzer components to provide
    structured table output through the MCP protocol.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the analyze code structure tool."""
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)
        self.logger = logger

    def set_project_path(self, project_path: str) -> None:
        """
        Update the project path for all components.

        Args:
            project_path: New project root directory
        """
        super().set_project_path(project_path)
        self.analysis_engine = get_analysis_engine(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"AnalyzeCodeStructureTool project path updated to: {project_path}")

    def get_tool_schema(self) -> dict[str, Any]:
        """
        Get the MCP tool schema for analyze_code_structure.

        Returns:
            Dictionary containing the tool schema
        """
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the code file to analyze and format",
                },
                "format_type": {
                    "type": "string",
                    "description": "Table format type",
                    "enum": ["full", "compact", "csv"],
                    "default": "full",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (optional, auto-detected if not specified)",
                },
                "output_file": {
                    "type": "string",
                    "description": "Optional filename to save output to file "
                    "(extension auto-detected based on content)",
                },
                "suppress_output": {
                    "type": "boolean",
                    "description": "When true and output_file is specified, "
                    "suppress table_output in response to save tokens",
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format for metadata: 'toon' (default, 50-70% token reduction) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Dictionary of arguments to validate

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

        # Validate format_type if provided
        if "format_type" in arguments:
            format_type = arguments["format_type"]
            if not isinstance(format_type, str):
                raise ValueError("format_type must be a string")

            # Only support v1.6.1.4 specification formats (no HTML formats)
            allowed_formats = ["full", "compact", "csv"]
            if format_type not in allowed_formats:
                raise ValueError(
                    f"format_type must be one of: {', '.join(sorted(allowed_formats))}"
                )

        # Validate language if provided
        if "language" in arguments:
            language = arguments["language"]
            if not isinstance(language, str):
                raise ValueError("language must be a string")

        # Validate output_file if provided
        if "output_file" in arguments:
            output_file = arguments["output_file"]
            if not isinstance(output_file, str):
                raise ValueError("output_file must be a string")
            if not output_file.strip():
                raise ValueError("output_file cannot be empty")

        # Validate suppress_output if provided
        if "suppress_output" in arguments:
            suppress_output = arguments["suppress_output"]
            if not isinstance(suppress_output, bool):
                raise ValueError("suppress_output must be a boolean")

        return True

    def _convert_parameters(self, parameters: Any) -> list[dict[str, str]]:
        """Convert parameters to expected format"""
        result = []
        for param in parameters:
            if isinstance(param, dict):
                result.append(
                    {
                        "name": param.get("name", "param"),
                        "type": param.get("type", "Object"),
                    }
                )
            else:
                result.append(
                    {
                        "name": getattr(param, "name", "param"),
                        "type": getattr(param, "param_type", "Object"),
                    }
                )
        return result

    def _get_method_modifiers(self, method: Any) -> list[str]:
        """Extract method modifiers as a list"""
        modifiers = []
        if getattr(method, "is_static", False):
            modifiers.append("static")
        if getattr(method, "is_final", False):
            modifiers.append("final")
        if getattr(method, "is_abstract", False):
            modifiers.append("abstract")
        return modifiers

    def _get_method_parameters(self, method: Any) -> list[dict[str, str]]:
        """Get method parameters in correct format for TableFormatter"""
        parameters = getattr(method, "parameters", [])

        # If parameters is already a list of strings, convert to dict format
        if parameters and isinstance(parameters[0], str):
            result = []
            for param_str in parameters:
                parts = param_str.strip().split()
                if len(parts) >= 2:
                    param_type = " ".join(
                        parts[:-1]
                    )  # Everything except last part is type
                    param_name = parts[-1]  # Last part is name
                    result.append({"name": param_name, "type": param_type})
                elif len(parts) == 1:
                    # Only type, no name
                    result.append({"name": "param", "type": parts[0]})
            return result

        # Fallback to original conversion method
        return self._convert_parameters(parameters)

    def _get_field_modifiers(self, field: Any) -> list[str]:
        """Extract field modifiers as a list"""
        modifiers = []

        # Add visibility to modifiers for CLI compatibility
        visibility = getattr(field, "visibility", "private")
        if visibility and visibility != "package":
            modifiers.append(visibility)

        if getattr(field, "is_static", False):
            modifiers.append("static")
        if getattr(field, "is_final", False):
            modifiers.append("final")
        return modifiers

    def _convert_analysis_result_to_dict(self, result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to dictionary format expected by TableFormatter"""
        # Extract elements by type
        classes = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)
        ]
        methods = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ]
        fields = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
        ]
        imports = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
        ]
        packages = [
            e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)
        ]

        # Convert package to expected format
        package_info = None
        if packages:
            package_info = {"name": packages[0].name}

        return {
            "success": True,
            "file_path": result.file_path,
            "language": result.language,
            "package": package_info,
            "classes": [
                {
                    "name": getattr(cls, "name", "unknown"),
                    "line_range": {
                        "start": getattr(cls, "start_line", 0),
                        "end": getattr(cls, "end_line", 0),
                    },
                    "type": getattr(cls, "class_type", "class"),
                    "visibility": "public",  # Force all classes to public
                    "extends": getattr(cls, "extends_class", None),
                    "implements": getattr(cls, "implements_interfaces", []),
                    "annotations": [],
                }
                for cls in classes
            ],
            "methods": [
                {
                    "name": getattr(method, "name", "unknown"),
                    "line_range": {
                        "start": getattr(method, "start_line", 0),
                        "end": getattr(method, "end_line", 0),
                    },
                    "return_type": getattr(method, "return_type", "void"),
                    "parameters": self._get_method_parameters(method),
                    "visibility": getattr(method, "visibility", "public"),
                    "is_static": getattr(method, "is_static", False),
                    "is_constructor": getattr(method, "is_constructor", False),
                    "complexity_score": getattr(method, "complexity_score", 0),
                    "modifiers": self._get_method_modifiers(method),
                    "annotations": [],
                }
                for method in methods
            ],
            "fields": [
                {
                    "name": getattr(field, "name", "unknown"),
                    "type": getattr(field, "field_type", "Object"),
                    "line_range": {
                        "start": getattr(field, "start_line", 0),
                        "end": getattr(field, "end_line", 0),
                    },
                    "visibility": getattr(field, "visibility", "private"),
                    "modifiers": self._get_field_modifiers(field),
                    "annotations": [],
                }
                for field in fields
            ],
            "imports": [
                {
                    "name": getattr(imp, "name", "unknown"),
                    "statement": getattr(
                        imp, "import_statement", getattr(imp, "name", "")
                    ),  # Use import_statement if available, fallback to name
                    "is_static": getattr(imp, "is_static", False),
                    "is_wildcard": getattr(imp, "is_wildcard", False),
                }
                for imp in imports
            ],
            "statistics": {
                "class_count": len(classes),
                "method_count": len(methods),
                "field_count": len(fields),
                "import_count": len(imports),
                "total_lines": result.line_count,
            },
        }

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute code structure analysis tool."""
        try:
            # Validate arguments first
            self.validate_arguments(args)

            file_path = args["file_path"]
            format_type = args.get("format_type", "full")
            language = args.get("language")
            output_file = args.get("output_file")
            suppress_output = args.get("suppress_output", False)
            output_format = args.get("output_format", "toon")

            # Use unified resolution and validation
            resolved_path = self.resolve_and_validate_file_path(file_path)

            # Sanitize inputs
            if format_type:
                format_type = self.security_validator.sanitize_input(
                    format_type, max_length=50
                )
            if language:
                language = self.security_validator.sanitize_input(
                    language, max_length=50
                )
            if output_file:
                output_file = self.security_validator.sanitize_input(
                    output_file, max_length=255
                )

            # Validate file exists
            if not Path(resolved_path).exists():
                raise ValueError(f"Invalid file path: File not found: {file_path}")

            # Detect language if not provided
            if not language:
                language = detect_language_from_file(
                    resolved_path, project_root=self.project_root
                )

            # Use performance monitoring
            monitor = get_performance_monitor()
            with monitor.measure_operation("code_structure_analysis"):
                # Analyze structure using the unified analysis engine
                request = AnalysisRequest(
                    file_path=resolved_path,
                    language=language,
                    include_complexity=True,
                    include_details=True,
                )
                structure_result = await self.analysis_engine.analyze(request)

                if structure_result is None:
                    raise RuntimeError(
                        f"Failed to analyze structure for file: {file_path}"
                    )

                # Always convert analysis result to dict for metadata extraction
                structure_dict = self._convert_analysis_result_to_dict(structure_result)

                # Use unified FormatterRegistry for all formats
                # This handles both language-specific and generic formatters
                if format_type in ["full", "compact", "csv"]:
                    # Use language-specific formatter from registry
                    formatter = FormatterRegistry.get_formatter_for_language(
                        language, format_type
                    )
                    table_output = formatter.format_structure(structure_dict)
                elif FormatterRegistry.is_format_supported(format_type):
                    # Use generic format-based formatter
                    registry_formatter = FormatterRegistry.get_formatter(format_type)
                    table_output = registry_formatter.format(structure_result.elements)
                else:
                    # Unsupported format
                    raise ValueError(f"Unsupported format type: {format_type}")

                # Ensure output format matches CLI exactly
                table_output = table_output.replace("\r\n", "\n").replace("\r", "\n")
                table_output = table_output.rstrip()

                # Extract metadata from structure dict
                metadata = {}
                if "statistics" in structure_dict:
                    stats = structure_dict["statistics"]
                    metadata = {
                        "classes_count": stats.get("class_count", 0),
                        "methods_count": stats.get("method_count", 0),
                        "fields_count": stats.get("field_count", 0),
                        "total_lines": stats.get("total_lines", 0),
                    }

                # Build result - include table_output based on suppress_output
                result = {
                    "success": True,
                    "format_type": format_type,
                    "file_path": file_path,
                    "language": language,
                    "metadata": metadata,
                    "table_output": table_output,
                }

                # Include table_output in response if needed
                if suppress_output and output_file:
                    del result["table_output"]

                # Handle file output if requested
                if output_file:
                    try:
                        # Generate base name from original file path if not provided
                        if not output_file or output_file.strip() == "":
                            base_name = Path(file_path).stem + "_analysis"
                        else:
                            base_name = output_file

                        # Save to file with automatic extension detection
                        saved_file_path = self.file_output_manager.save_to_file(
                            content=table_output, base_name=base_name
                        )

                        result["output_file_path"] = saved_file_path
                        result["file_saved"] = True

                        self.logger.info(f"Analysis output saved to: {saved_file_path}")

                    except Exception as e:
                        self.logger.error(f"Failed to save output to file: {e}")
                        result["file_save_error"] = str(e)
                        result["file_saved"] = False

                # Apply TOON format to direct output if requested
                return apply_toon_format_to_response(result, output_format)

        except Exception as e:
            self.logger.error(f"Error in code structure analysis tool: {e}")
            raise

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get the MCP tool definition for analyze_code_structure.

        Returns:
            Tool definition dictionary compatible with MCP server
        """
        return {
            "name": "analyze_code_structure",
            "description": (
                "Analyze code structure and generate detailed overview tables "
                "(classes, methods, fields) with line positions for large files, "
                "optionally save to file"
            ),
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy access
analyze_code_structure_tool = AnalyzeCodeStructureTool()
