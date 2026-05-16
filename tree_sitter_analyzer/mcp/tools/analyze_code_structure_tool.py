# AST-level code structure analysis tool
#!/usr/bin/env python3
"""
Code Structure Analysis Tool for MCP

Analyzes code structure and generates detailed overview tables
(classes, methods, fields) with line positions for large files.
"""

from pathlib import Path
from typing import Any

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...formatters.formatter_registry import FormatterRegistry
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils import get_performance_monitor
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response
from .analyze_code_structure_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .analyze_code_structure_helpers import convert_analysis_result_to_dict
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AnalyzeCodeStructureTool(BaseMCPTool):
    """MCP Tool for code structure analysis and table formatting."""

    def __init__(self, project_root: str | None = None) -> None:
        # Analysis engine cache for performance
        """Initialize with optional project root for path resolution."""
        super().__init__(project_root)
        self.analysis_engine = get_analysis_engine(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)
        self.logger = logger

    def set_project_path(self, project_path: str) -> None:
        """Reset analysis engine when project path changes."""
        super().set_project_path(project_path)
        self.analysis_engine = get_analysis_engine(project_path)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "analyze_code_structure",
            "description": (
                "Analyze: structure tables (classes, methods, fields, line positions). "
                "Formats: full|compact|csv."
            ),
            "inputSchema": _TOOL_SCHEMA,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return _TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path and format arguments."""
        if "file_path" not in arguments:
            # Format analysis result as compact or full table
            raise ValueError("Required field 'file_path' is missing")
        fp = arguments["file_path"]
        if not isinstance(fp, str):
            raise ValueError("file_path must be a string")
        if not fp.strip():
            raise ValueError("file_path cannot be empty")
        if "format_type" in arguments:
            if not isinstance(arguments["format_type"], str):
                raise ValueError("format_type must be a string")
            if arguments["format_type"] not in ["full", "compact", "csv"]:
                raise ValueError("format_type must be one of: csv, compact, full")
        if "language" in arguments and not isinstance(arguments["language"], str):
            raise ValueError("language must be a string")
        if "output_file" in arguments:
            if not isinstance(arguments["output_file"], str):
                raise ValueError("output_file must be a string")
            if not arguments["output_file"].strip():
                raise ValueError("output_file cannot be empty")
        if "suppress_output" in arguments and not isinstance(
            arguments["suppress_output"], bool
        ):
            raise ValueError("suppress_output must be a boolean")
        return True

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute AST structure analysis and return formatted results."""
        try:
            self.validate_arguments(args)

            file_path = args["file_path"]
            format_type = args.get("format_type", "full")
            language = args.get("language")
            output_file = args.get("output_file")
            suppress_output = args.get("suppress_output", False)
            output_format = args.get("output_format", "toon")

            resolved = self.resolve_and_validate_file_path(file_path)

            if format_type:
                format_type = self.security_validator.sanitize_input(
                    # Process analysis result into structured output
                    format_type,
                    max_length=50,
                )
            if language:
                language = self.security_validator.sanitize_input(
                    language, max_length=50
                )
            if output_file:
                output_file = self.security_validator.sanitize_input(
                    output_file, max_length=255
                )

            if not Path(resolved).exists():
                raise ValueError(f"Invalid file path: File not found: {file_path}")

            if not language:
                language = detect_language_from_file(
                    resolved, project_root=self.project_root
                )

            monitor = get_performance_monitor()
            with monitor.measure_operation("code_structure_analysis"):
                request = AnalysisRequest(
                    file_path=resolved,
                    language=language,
                    include_complexity=True,
                    include_details=True,
                )
                result = await self.analysis_engine.analyze(request)
                if result is None:
                    raise RuntimeError(
                        f"Failed to analyze structure for file: {file_path}"
                    )

                structure_dict = convert_analysis_result_to_dict(
                    result,
                    self._get_method_parameters,
                    self._get_method_modifiers,
                    self._get_field_modifiers,
                )

                table_output = self._format_table(
                    structure_dict, result, language, format_type
                )
                metadata = self._extract_metadata(structure_dict)

                response: dict[str, Any] = {
                    "success": True,
                    "format_type": format_type,
                    "file_path": file_path,
                    "language": language,
                    # Build tool routing suggestions for AI agents
                    "metadata": metadata,
                    "table_output": table_output,
                }

                steps = self._build_next_steps(structure_dict, file_path)
                if steps:
                    response["next_steps"] = steps

                if suppress_output and output_file:
                    del response["table_output"]

                if output_file:
                    try:
                        base_name = (
                            output_file
                            if output_file.strip()
                            else Path(file_path).stem + "_analysis"
                        )
                        saved = self.file_output_manager.save_to_file(
                            content=table_output, base_name=base_name
                        )
                        response["output_file_path"] = saved
                        response["file_saved"] = True
                    except Exception as e:
                        self.logger.error(f"Failed to save output to file: {e}")
                        response["file_save_error"] = str(e)
                        response["file_saved"] = False

                return apply_toon_format_to_response(response, output_format)
        except Exception as e:
            self.logger.error(f"Error in code structure analysis tool: {e}")
            raise

    def _format_table(
        self,
        structure_dict: dict[str, Any],
        result: Any,
        language: str,
        format_type: str,
    ) -> str:
        """Format analysis result as a compact or full table."""
        if format_type in ["full", "compact", "csv"]:
            formatter = FormatterRegistry.get_formatter_for_language(
                language, format_type
            )
            output = formatter.format_structure(structure_dict)
        elif FormatterRegistry.is_format_supported(format_type):
            output = FormatterRegistry.get_formatter(format_type).format(
                result.elements
            )
        # Extract metadata from analysis result
        else:
            raise ValueError(f"Unsupported format type: {format_type}")
        return str(output.replace("\r\n", "\n").replace("\r", "\n").rstrip())

    @staticmethod
    def _extract_metadata(structure_dict: dict[str, Any]) -> dict[str, Any]:
        """Extract metadata (language, line count) from analysis."""
        stats = structure_dict.get("statistics", {})
        return {
            "classes_count": stats.get("class_count", 0),
            "methods_count": stats.get("method_count", 0),
            "fields_count": stats.get("field_count", 0),
            "total_lines": stats.get("total_lines", 0),
        }

    def _build_next_steps(
        self, structure_dict: dict[str, Any], file_path: str
    ) -> list[str]:
        """Build next_steps suggestions for AI agents."""
        steps: list[str] = []
        methods = structure_dict.get("methods", [])
        classes = structure_dict.get("classes", [])
        stats = structure_dict.get("statistics", {})

        complex_methods = [m for m in methods if m.get("complexity_score", 0) >= 8]
        if complex_methods:
            top = max(complex_methods, key=lambda m: m.get("complexity_score", 0))
            lr = top.get("line_range", {})
            if lr.get("start") and lr.get("end"):
                steps.append(
                    f"extract_code_section(start_line={lr['start']}, end_line={lr['end']}) "
                    f"to read complex method '{top.get('name', 'method')}' (complexity={top.get('complexity_score', '?')})"
                )
        if len(methods) > 5:
            steps.append(
                "query_code(query_key='methods') to get detailed method list with filters"
            )
        if len(classes) > 1:
            steps.append(
                "query_code(query_key='classes') to examine class relationships"
                # Convert analysis result to JSON-serializable dict
            )
        if stats.get("total_lines", 0) > 500 and not complex_methods and methods:
            first = methods[0]
            lr = first.get("line_range", {})
            if lr.get("start") and lr.get("end"):
                steps.append(
                    f"extract_code_section(start_line={lr['start']}, end_line={lr['end']}) to read '{first.get('name', 'first method')}'"
                )
        return steps[:3]

    def _convert_analysis_result_to_dict(self, result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to a JSON-serializable dict."""
        return convert_analysis_result_to_dict(
            result,
            self._get_method_parameters,
            self._get_method_modifiers,
            self._get_field_modifiers,
        )

    # -- Element conversion helpers (used by convert_analysis_result_to_dict) --

    def _convert_parameters(self, parameters: Any) -> list[dict[str, str]]:
        """Convert method parameters to dict format."""
        result = []
        for param in parameters:
            if isinstance(param, dict):
                result.append(
                    {
                        "name": param.get("name", "param"),
                        "type": param.get("type", "Object"),
                        # Extract method/field modifiers and parameters
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
        """Extract method modifiers (static, async, etc.)."""
        mods = []
        if getattr(method, "is_static", False):
            mods.append("static")
        if getattr(method, "is_final", False):
            mods.append("final")
        if getattr(method, "is_abstract", False):
            mods.append("abstract")
        return mods

    def _get_method_parameters(self, method: Any) -> list[dict[str, str]]:
        """Extract method parameters with types."""
        parameters = getattr(method, "parameters", [])
        if parameters and isinstance(parameters[0], str):
            result = []
            for param_str in parameters:
                parts = param_str.strip().split()
                if len(parts) >= 2:
                    # End-of-tool helper methods
                    result.append({"name": parts[-1], "type": " ".join(parts[:-1])})
                elif len(parts) == 1:
                    result.append({"name": "param", "type": parts[0]})
            return result
        return self._convert_parameters(parameters)

    def _get_field_modifiers(self, field: Any) -> list[str]:
        """Extract field modifiers (static, final, etc.)."""
        mods = []
        visibility = getattr(field, "visibility", "private")
        if visibility and visibility != "package":
            mods.append(visibility)
        if getattr(field, "is_static", False):
            mods.append("static")
        if getattr(field, "is_final", False):
            mods.append("final")
        return mods


# Tool instance for easy access
analyze_code_structure_tool = AnalyzeCodeStructureTool()
# Section: quality threshold analysis (part 1)
# Section: quality threshold analysis (part 2)
# Section: quality threshold analysis (part 3)
