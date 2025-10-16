#!/usr/bin/env python3
"""
Table Format Tool for MCP

This tool provides code structure analysis and table formatting through the MCP protocol,
converting analysis results into structured table formats for better readability.
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
from ...table_formatter import TableFormatter
from ...utils import setup_logger
from ..utils import get_performance_monitor
from ..utils.file_output_manager import FileOutputManager
from .base_tool import BaseMCPTool

# Set up logging
logger = setup_logger(__name__)


class TableFormatTool(BaseMCPTool):
    """
    MCP Tool for code structure analysis and table formatting.

    This tool integrates with existing analyzer components to provide
    structured table output through the MCP protocol.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the table format tool."""
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
        logger.info(f"TableFormatTool project path updated to: {project_path}")

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
                    "enum": list(
                        set(
                            FormatterRegistry.get_available_formats()
                            + ["full", "compact", "csv", "json"]
                        )
                    ),
                    "default": "full",
                },
                "language": {
                    "type": "string",
                    "description": "Programming language (optional, auto-detected if not specified)",
                },
                "output_file": {
                    "type": "string",
                    "description": "Optional filename to save output to file (extension auto-detected based on content)",
                },
                "suppress_output": {
                    "type": "boolean",
                    "description": "When true and output_file is specified, suppress table_output in response to save tokens",
                    "default": False,
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

            # Check both new FormatterRegistry formats and legacy formats
            available_formats = list(
                set(
                    FormatterRegistry.get_available_formats()
                    + ["full", "compact", "csv", "json"]
                )
            )
            if format_type not in available_formats:
                raise ValueError(
                    f"format_type must be one of: {', '.join(sorted(available_formats))}"
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
        """Get method parameters in the correct format for TableFormatter"""
        parameters = getattr(method, "parameters", [])

        # If parameters is already a list of strings (like "int value"), convert to dict format
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
                    "visibility": "public",  # Force all classes to public for CLI compatibility
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
                        imp, "name", ""
                    ),  # Use name for CLI compatibility
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

    def _write_output_file(
        self, output_file: str, content: str, format_type: str
    ) -> str:
        """
        Write output content to file with automatic extension detection.

        Args:
            output_file: Base filename for output
            content: Content to write
            format_type: Format type (full, compact, csv, json)

        Returns:
            Full path of the written file
        """
        from pathlib import Path

        # Determine file extension based on format type
        extension_map = {
            "full": ".md",
            "compact": ".md",
            "csv": ".csv",
            "json": ".json",
        }

        # Get the appropriate extension
        extension = extension_map.get(format_type, ".txt")

        # Add extension if not already present
        if not output_file.endswith(extension):
            output_file = output_file + extension

        # Resolve output path relative to project root
        output_path = self.path_resolver.resolve(output_file)

        # Security validation for output path
        is_valid, error_msg = self.security_validator.validate_file_path(output_path)
        if not is_valid:
            raise ValueError(f"Invalid output file path: {error_msg}")

        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write content to file
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.logger.info(f"Output written to file: {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to write output file {output_path}: {e}")
            raise RuntimeError(f"Failed to write output file: {e}") from e

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute code structure analysis tool."""
        try:
            # Validate arguments first
            if "file_path" not in args:
                raise ValueError("file_path is required")

            file_path = args["file_path"]
            format_type = args.get("format_type", "full")
            language = args.get("language")
            output_file = args.get("output_file")
            suppress_output = args.get("suppress_output", False)

            # Security validation BEFORE path resolution to catch symlinks
            is_valid, error_msg = self.security_validator.validate_file_path(file_path)
            if not is_valid:
                self.logger.warning(
                    f"Security validation failed for file path: {file_path} - {error_msg}"
                )
                raise ValueError(f"Invalid file path: {error_msg}")

            # Resolve file path using common path resolver
            resolved_path = self.path_resolver.resolve(file_path)

            # Additional security validation on resolved path
            is_valid, error_msg = self.security_validator.validate_file_path(
                resolved_path
            )
            if not is_valid:
                self.logger.warning(
                    f"Security validation failed for resolved path: {resolved_path} - {error_msg}"
                )
                raise ValueError(f"Invalid resolved path: {error_msg}")

            # Sanitize format_type input
            if format_type:
                format_type = self.security_validator.sanitize_input(
                    format_type, max_length=50
                )

            # Sanitize language input
            if language:
                language = self.security_validator.sanitize_input(
                    language, max_length=50
                )

            # Sanitize output_file input
            if output_file:
                output_file = self.security_validator.sanitize_input(
                    output_file, max_length=255
                )

            # Sanitize suppress_output input (boolean, no sanitization needed but validate type)
            if suppress_output is not None and not isinstance(suppress_output, bool):
                raise ValueError("suppress_output must be a boolean")

            # Validate file exists
            if not Path(resolved_path).exists():
                # Tests expect FileNotFoundError here
                raise FileNotFoundError(f"File not found: {file_path}")

            # Detect language if not provided
            if not language:
                language = detect_language_from_file(resolved_path)

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

                # Try to use new FormatterRegistry first, fallback to legacy TableFormatter
                try:
                    if FormatterRegistry.is_format_supported(format_type):
                        # Use new FormatterRegistry
                        formatter = FormatterRegistry.get_formatter(format_type)
                        table_output = formatter.format(structure_result.elements)
                    else:
                        # Fallback to legacy TableFormatter for backward compatibility
                        formatter: Any = TableFormatter(format_type)
                        table_output = formatter.format_structure(structure_dict)  # type: ignore[attr-defined]
                except Exception as e:
                    # If FormatterRegistry fails, fallback to legacy TableFormatter
                    logger.warning(
                        f"FormatterRegistry failed, using legacy formatter: {e}"
                    )
                    formatter: Any = TableFormatter(format_type)
                    table_output = formatter.format_structure(structure_dict)  # type: ignore[attr-defined]

                # Ensure output format matches CLI exactly
                # Fix line ending differences: normalize to Unix-style LF (\n)
                table_output = table_output.replace("\r\n", "\n").replace("\r", "\n")

                # CLI uses sys.stdout.buffer.write() which doesn't add trailing newline
                # Ensure MCP output matches this behavior exactly
                # Remove any trailing whitespace and newlines to match CLI output
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

                # Build result - conditionally include table_output based on suppress_output
                result = {
                    "success": True,
                    "format_type": format_type,
                    "file_path": file_path,
                    "language": language,
                    "metadata": metadata,
                }

                # Only include table_output if not suppressed or no output file specified
                if not suppress_output or not output_file:
                    result["table_output"] = table_output

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

                return result

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
            "description": "Analyze code structure and generate detailed overview tables (classes, methods, fields) with line positions for large files, optionally save to file",
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy access
table_format_tool = TableFormatTool()
