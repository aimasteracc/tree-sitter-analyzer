# AST-level code structure analysis tool
#!/usr/bin/env python3
"""
Code Structure Analysis Tool for MCP

Analyzes code structure and generates detailed overview tables
(classes, methods, fields) with line positions for large files.
"""

from dataclasses import dataclass
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
from .analyze_code_structure_helpers import (
    convert_analysis_result_to_dict,
    extract_metadata,
)
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


@dataclass(frozen=True)
class _ExecutionOptions:
    file_path: str
    resolved_path: str
    format_type: str
    language: str
    output_file: str | None
    suppress_output: bool
    output_format: str


def _format_table(
    structure_dict: dict[str, Any],
    result: Any,
    language: str,
    format_type: str,
) -> str:
    """Format analysis result as a compact or full table."""
    if format_type in ["full", "compact", "csv"]:
        formatter = FormatterRegistry.get_formatter_for_language(language, format_type)
        output = formatter.format_structure(structure_dict)
    elif FormatterRegistry.is_format_supported(format_type):
        output = FormatterRegistry.get_formatter(format_type).format(result.elements)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")
    return str(output.replace("\r\n", "\n").replace("\r", "\n").rstrip())


def _get_method_modifiers(method: Any) -> list[str]:
    """Extract method modifiers (static, final, abstract)."""
    mods = []
    if getattr(method, "is_static", False):
        mods.append("static")
    if getattr(method, "is_final", False):
        mods.append("final")
    if getattr(method, "is_abstract", False):
        mods.append("abstract")
    return mods


def _get_field_modifiers(field: Any) -> list[str]:
    """Extract field modifiers (visibility, static, final)."""
    mods = []
    visibility = getattr(field, "visibility", "private")
    if visibility and visibility != "package":
        mods.append(visibility)
    if getattr(field, "is_static", False):
        mods.append("static")
    if getattr(field, "is_final", False):
        mods.append("final")
    return mods


def _convert_parameters(parameters: Any) -> list[dict[str, str]]:
    """Convert method parameters to dict format."""
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


def _get_method_parameters(method: Any) -> list[dict[str, str]]:
    """Extract method parameters with types."""
    parameters = getattr(method, "parameters", [])
    if parameters and isinstance(parameters[0], str):
        result = []
        for param_str in parameters:
            parts = param_str.strip().split()
            if len(parts) >= 2:
                result.append({"name": parts[-1], "type": " ".join(parts[:-1])})
            elif len(parts) == 1:
                result.append({"name": "param", "type": parts[0]})
        return result
    return _convert_parameters(parameters)


def _build_next_steps(structure_dict: dict[str, Any], file_path: str) -> list[str]:
    """Build next_steps suggestions for AI agents."""
    steps: list[str] = []
    methods = structure_dict.get("methods", [])
    classes = structure_dict.get("classes", [])
    stats = structure_dict.get("statistics", {})
    if not isinstance(methods, list):
        methods = []
    if not isinstance(classes, list):
        classes = []
    total_lines = stats.get("total_lines", 0)
    if not isinstance(total_lines, int):
        total_lines = 0

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
        steps.append("query_code(query_key='classes') to examine class relationships")
    if total_lines > 500 and not complex_methods and methods:
        first = methods[0]
        lr = first.get("line_range", {})
        if lr.get("start") and lr.get("end"):
            steps.append(
                f"extract_code_section(start_line={lr['start']}, end_line={lr['end']}) to read '{first.get('name', 'first method')}'"
            )
    return steps[:3]


def _convert_analysis_result(result: Any) -> dict[str, Any]:
    """Convert AnalysisResult to a JSON-serializable dict."""
    return convert_analysis_result_to_dict(
        result,
        _get_method_parameters,
        _get_method_modifiers,
        _get_field_modifiers,
    )


def _build_success_response(
    options: _ExecutionOptions,
    metadata: dict[str, Any],
    table_output: str,
    next_steps: list[str],
) -> dict[str, Any]:
    """Build the successful tool response before optional file persistence."""
    response: dict[str, Any] = {
        "success": True,
        "format_type": options.format_type,
        "file_path": options.file_path,
        "language": options.language,
        "metadata": metadata,
        "table_output": table_output,
    }
    if next_steps:
        response["next_steps"] = next_steps
    if options.suppress_output and options.output_file:
        del response["table_output"]
    return response


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

    # JSON schema for input validation
    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return _TOOL_SCHEMA

    # Input validation - fail fast with clear error messages
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

    # Main entry point - dispatches to mode-specific handler
    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute AST structure analysis and return formatted results."""
        try:
            options = self._prepare_execution_options(args)
            result = await self._analyze_structure(options)
            structure_dict = self._convert_analysis_result_to_dict(result)
            table_output = _format_table(
                structure_dict, result, options.language, options.format_type
            )
            response = _build_success_response(
                options,
                extract_metadata(structure_dict),
                table_output,
                _build_next_steps(structure_dict, options.file_path),
            )
            if options.output_file:
                self._save_output(response, table_output, options)
            return apply_toon_format_to_response(response, options.output_format)
        except Exception as e:
            self.logger.error(f"Error in code structure analysis tool: {e}")
            raise

    def _prepare_execution_options(self, args: dict[str, Any]) -> _ExecutionOptions:
        """Validate, sanitize, and resolve execute arguments."""
        self.validate_arguments(args)
        file_path = args["file_path"]
        format_type = args.get("format_type", "full")
        language = args.get("language")
        output_file = args.get("output_file")
        resolved = self.resolve_and_validate_file_path(file_path)

        if format_type:
            format_type = self.security_validator.sanitize_input(
                format_type, max_length=50
            )
        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)
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

        return _ExecutionOptions(
            file_path=file_path,
            resolved_path=resolved,
            format_type=format_type,
            language=language,
            output_file=output_file,
            suppress_output=args.get("suppress_output", False),
            output_format=args.get("output_format", "toon"),
        )

    async def _analyze_structure(self, options: _ExecutionOptions) -> Any:
        """Run the analysis engine for the resolved input file."""
        monitor = get_performance_monitor()
        with monitor.measure_operation("code_structure_analysis"):
            request = AnalysisRequest(
                file_path=options.resolved_path,
                language=options.language,
                include_complexity=True,
                include_details=True,
            )
            result = await self.analysis_engine.analyze(request)
        if result is None:
            raise RuntimeError(
                f"Failed to analyze structure for file: {options.file_path}"
            )
        return result

    def _save_output(
        self,
        response: dict[str, Any],
        table_output: str,
        options: _ExecutionOptions,
    ) -> None:
        """Persist table output and annotate the response with save status."""
        try:
            base_name = (
                options.output_file
                if options.output_file and options.output_file.strip()
                else Path(options.file_path).stem + "_analysis"
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

    def _convert_analysis_result_to_dict(self, result: Any) -> dict[str, Any]:
        """Convert AnalysisResult to a JSON-serializable dict."""
        return _convert_analysis_result(result)


# Tool instance for easy access
analyze_code_structure_tool = AnalyzeCodeStructureTool()
