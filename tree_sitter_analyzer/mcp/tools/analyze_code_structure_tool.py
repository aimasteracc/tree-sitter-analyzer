# AST-level code structure analysis tool
#!/usr/bin/env python3
"""
Code Structure Analysis Tool for MCP

Analyzes code structure and generates detailed overview tables
(classes, methods, fields) with line positions for large files.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...formatters.formatter_registry import FormatterRegistry
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils import get_performance_monitor
from ..utils.file_output_manager import FileOutputManager
from ..utils.format_helper import apply_toon_format_to_response
from .analyze_code_structure_helpers import TOOL_SCHEMA as _TOOL_SCHEMA
from .analyze_code_structure_helpers import (
    convert_analysis_result_to_structure_dict,
    extract_metadata,
)
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    format_summary_line,
    language_mismatch_error_response,
)

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


def _structure_items(value: Any) -> list[dict[str, Any]]:
    """Return list-shaped structure items and ignore malformed entries."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _total_lines(statistics: Any) -> int:
    """Extract a valid total line count from analysis statistics."""
    if not isinstance(statistics, dict):
        return 0
    total = statistics.get("total_lines", 0)
    return total if isinstance(total, int) else 0


def _method_complexity(method: dict[str, Any]) -> int:
    """Normalize method complexity to an integer routing score."""
    complexity = method.get("complexity_score", 0)
    return complexity if isinstance(complexity, int) else 0


def _line_range(method: dict[str, Any]) -> tuple[Any, Any] | None:
    """Return usable start/end line values for a method suggestion."""
    line_range = method.get("line_range", {})
    if not isinstance(line_range, dict):
        return None
    start = line_range.get("start")
    end = line_range.get("end")
    if start and end:
        return start, end
    return None


def _complex_method_step(methods: list[dict[str, Any]]) -> str | None:
    """Build the focused extraction step for the most complex method."""
    complex_methods = [m for m in methods if _method_complexity(m) >= 8]
    if not complex_methods:
        return None
    top = max(complex_methods, key=_method_complexity)
    bounds = _line_range(top)
    if not bounds:
        return None
    start, end = bounds
    return (
        f"extract_code_section(start_line={start}, end_line={end}) "
        f"to read complex method '{top.get('name', 'method')}' "
        f"(complexity={top.get('complexity_score', '?')})"
    )


def _query_navigation_steps(
    methods: list[dict[str, Any]], classes: list[dict[str, Any]]
) -> list[str]:
    """Build query steps for larger method/class collections."""
    steps = []
    if len(methods) > 5:
        steps.append(
            "query_code(query_key='methods') to get detailed method list with filters"
        )
    if len(classes) > 1:
        steps.append("query_code(query_key='classes') to examine class relationships")
    return steps


def _large_file_first_method_step(
    methods: list[dict[str, Any]], total_lines: int
) -> str | None:
    """Build a fallback extraction step for large files without complex methods."""
    if total_lines <= 500 or not methods:
        return None
    first = methods[0]
    bounds = _line_range(first)
    if not bounds:
        return None
    start, end = bounds
    return (
        f"extract_code_section(start_line={start}, end_line={end}) "
        f"to read '{first.get('name', 'first method')}'"
    )


def _build_next_steps(structure_dict: dict[str, Any], file_path: str) -> list[str]:
    """Build next_steps suggestions for AI agents."""
    methods = _structure_items(structure_dict.get("methods", []))
    classes = _structure_items(structure_dict.get("classes", []))
    total_line_count = _total_lines(structure_dict.get("statistics", {}))

    steps = []
    complex_step = _complex_method_step(methods)
    if complex_step:
        steps.append(complex_step)
    steps.extend(_query_navigation_steps(methods, classes))
    if not complex_step:
        fallback_step = _large_file_first_method_step(methods, total_line_count)
        if fallback_step:
            steps.append(fallback_step)
    return steps[:3]


def _convert_analysis_result(result: Any) -> dict[str, Any]:
    """Convert AnalysisResult to a JSON-serializable dict."""
    return convert_analysis_result_to_structure_dict(result)


def _build_success_response(
    options: _ExecutionOptions,
    metadata: dict[str, Any],
    table_output: str,
    next_steps: list[str],
) -> dict[str, Any]:
    """Build the successful tool response before optional file persistence."""
    response = _base_success_response(options, metadata, table_output)
    _attach_next_steps(response, next_steps)
    _suppress_table_output_if_requested(response, options)
    # Finding 6: synthesize an agent_summary + summary_line so the central
    # post-hook (and direct ``execute()`` callers) see populated envelope
    # keys. Round-16b dogfood saw both as ``None`` here.
    _attach_agent_summary(response, options, metadata, next_steps)
    return response


def _attach_agent_summary(
    response: dict[str, Any],
    options: _ExecutionOptions,
    metadata: dict[str, Any],
    next_steps: list[str],
) -> None:
    """Inject ``agent_summary`` + ``summary_line`` keys on the success path."""

    def _safe_int(value: Any) -> int:
        return value if isinstance(value, int) else 0

    n_classes = _safe_int(metadata.get("classes_count", 0))
    n_methods = _safe_int(metadata.get("methods_count", 0))
    n_fields = _safe_int(metadata.get("fields_count", 0))
    total_lines = _safe_int(metadata.get("total_lines", 0))
    # J5 (round-22): single-space join via helper.
    summary_line = format_summary_line(
        options.file_path,
        options.language,
        f"{total_lines} lines",
        f"classes={n_classes}",
        f"methods={n_methods}",
        f"fields={n_fields}",
    )
    response["summary_line"] = summary_line
    response["agent_summary"] = {
        "summary_line": summary_line,
        "next_step": (
            next_steps[0]
            if next_steps
            else "Call query_code or extract_code_section for deeper detail."
        ),
        "verdict": "n/a",
    }


def _base_success_response(
    options: _ExecutionOptions,
    metadata: dict[str, Any],
    table_output: str,
) -> dict[str, Any]:
    """Build the common success response payload.

    ``table_format`` mirrors the input ``format_type`` (the structure-table
    style: full/compact/csv). ``format_type`` is kept as a backward-compat
    alias for one release — round-7/12 dogfood audits called out the name
    as confusing because callers expected it to describe the envelope.

    ``output_format`` mirrors the input envelope choice (json/toon) so
    callers can verify which envelope they received without re-deriving it
    from the presence/absence of ``toon_content``.
    """
    return {
        "success": True,
        "table_format": options.format_type,
        # Deprecated alias — kept for one release; prefer ``table_format``.
        "format_type": options.format_type,
        "output_format": options.output_format,
        "file_path": options.file_path,
        "language": options.language,
        "metadata": metadata,
        "table_output": table_output,
    }


def _attach_next_steps(response: dict[str, Any], next_steps: list[str]) -> None:
    """Attach compact agent routing suggestions when present."""
    if next_steps:
        response["next_steps"] = next_steps


def _suppress_table_output_if_requested(
    response: dict[str, Any], options: _ExecutionOptions
) -> None:
    """Drop table output only when it was persisted to a file."""
    if options.suppress_output and options.output_file:
        del response["table_output"]


def _validate_required_file_path(arguments: dict[str, Any]) -> None:
    """Validate the required file_path argument."""
    if "file_path" not in arguments:
        raise ValueError("Required field 'file_path' is missing")
    file_path = arguments["file_path"]
    if not isinstance(file_path, str):
        raise ValueError("file_path must be a string")
    if not file_path.strip():
        raise ValueError("file_path cannot be empty")


def _validate_format_type(arguments: dict[str, Any]) -> None:
    """Validate the optional structure table format."""
    if "format_type" not in arguments:
        return
    if not isinstance(arguments["format_type"], str):
        raise ValueError("format_type must be a string")
    if arguments["format_type"] not in ["full", "compact", "csv"]:
        raise ValueError("format_type must be one of: csv, compact, full")


def _validate_optional_string(
    arguments: dict[str, Any], field_name: str, *, allow_blank: bool = True
) -> None:
    """Validate an optional string argument and optional blank rejection."""
    if field_name not in arguments:
        return
    value = arguments[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not allow_blank and not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _validate_suppress_output(arguments: dict[str, Any]) -> None:
    """Validate the optional suppress_output flag."""
    if "suppress_output" in arguments and not isinstance(
        arguments["suppress_output"], bool
    ):
        raise ValueError("suppress_output must be a boolean")


def _ensure_input_file_exists(resolved_path: str, file_path: str) -> None:
    """Raise a user-facing error when the resolved input is missing."""
    if not Path(resolved_path).exists():
        raise ValueError(f"Invalid file path: File not found: {file_path}")


def _output_base_name(options: _ExecutionOptions) -> str:
    """Return the managed file-output base name."""
    if options.output_file and options.output_file.strip():
        return options.output_file
    return Path(options.file_path).stem + "_analysis"


def _mark_file_saved(response: dict[str, Any], saved_path: str) -> None:
    """Annotate a successful file save."""
    response["output_file_path"] = saved_path
    response["file_saved"] = True


def _mark_file_save_error(response: dict[str, Any], error: Exception) -> None:
    """Annotate a failed file save without failing the whole tool call."""
    response["file_save_error"] = str(error)
    response["file_saved"] = False


class AnalyzeCodeStructureTool(BaseMCPTool):
    """MCP Tool for code structure analysis and table formatting."""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize with optional project root for path resolution."""
        # ARCH-A4: super().__init__() drives _on_project_root_changed which
        # populates these synchronously. None placeholder never observable.
        self.analysis_engine: Any = None
        self.file_output_manager: FileOutputManager = cast("FileOutputManager", None)
        super().__init__(project_root)
        self.logger = logger

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self.analysis_engine = get_analysis_engine(project_root)
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "analyze_code_structure",
            "description": (
                "Per-file structural table: classes, methods, fields, "
                "imports each with their line range and signature. Three "
                "table formats (``full`` = everything, ``compact`` = "
                "essentials only, ``csv`` = machine-readable rows). Returns "
                "both the parsed table and a free-form ``table_output`` "
                "rendering. Same data as ``get_code_outline`` but presented "
                "as a table the agent can scan visually.\n\n"
                "WHEN TO USE:\n"
                "- To see a class's full method list with signatures and "
                "line numbers in one render\n"
                "- For CSV export of file structure (e.g. for a refactor "
                "planning sheet)\n"
                "- To verify an extraction plan against actual member lists\n"
                "- When you want a flat table rather than the hierarchical "
                "outline from get_code_outline\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For a hierarchical outline — use get_code_outline\n"
                "- For just the counts — use analyze_scale (cheaper)\n"
                "- To read implementation bodies — use partial_read"
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
        _validate_required_file_path(arguments)
        _validate_format_type(arguments)
        _validate_optional_string(arguments, "language")
        _validate_optional_string(arguments, "output_file", allow_blank=False)
        _validate_suppress_output(arguments)
        return True

    # Main entry point - dispatches to mode-specific handler
    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute AST structure analysis and return formatted results."""
        try:
            # O3 (round-30 dogfood): strict mismatch gate. Resolve the
            # path FIRST so we can validate the explicit language
            # against the real extension; the heavy
            # ``_prepare_execution_options`` (language detection +
            # security sanitisation) only runs if the gate passes.
            file_path = args.get("file_path")
            if isinstance(file_path, str) and file_path.strip():
                try:
                    resolved_for_check = self.resolve_and_validate_file_path(file_path)
                except Exception:
                    resolved_for_check = file_path
                mismatch = detect_language_mismatch(
                    resolved_for_check,
                    args.get("language")
                    if isinstance(args.get("language"), str)
                    else None,
                    project_root=self.project_root,
                )
                if mismatch:
                    response = language_mismatch_error_response(
                        tool_name="analyze_code_structure",
                        file_path=file_path,
                        warning=mismatch,
                    )
                    response["output_format"] = args.get("output_format", "toon")
                    return response

            options = self._prepare_execution_options(args)
            result = await self._analyze_structure(options)
            return self._format_response(result, options)
        except Exception as e:
            self.logger.error(f"Error in code structure analysis tool: {e}")
            raise

    def _format_response(
        self, result: Any, options: _ExecutionOptions
    ) -> dict[str, Any]:
        """Convert analysis output into the final MCP response payload."""
        structure_dict = _convert_analysis_result(result)
        table_output = _format_table(
            structure_dict, result, options.language, options.format_type
        )
        response = _build_success_response(
            options,
            extract_metadata(structure_dict),
            table_output,
            _build_next_steps(structure_dict, options.file_path),
        )
        # Hoist the rich per-element detail to top-level so agents can read it
        # without parsing ``table_output``. Mirrors ``universal_analyze``'s
        # shape for cross-tool parity.
        for key in ("classes", "methods", "fields", "imports"):
            response[key] = structure_dict.get(key, [])
        # S2 (round-37 dogfood): hoist ``statistics`` to top-level so MCP
        # matches CLI ``--table=full --format json`` parity. CLI exposes
        # ``statistics: {class_count, method_count, field_count, import_count,
        # total_lines}``; MCP only had ``metadata: {classes_count,
        # methods_count, ...}`` (plural, nested). Both shapes now coexist.
        stats = structure_dict.get("statistics")
        if isinstance(stats, dict):
            response["statistics"] = stats
        if options.output_file:
            self._save_output(response, table_output, options)
        return apply_toon_format_to_response(response, options.output_format)

    def _prepare_execution_options(self, args: dict[str, Any]) -> _ExecutionOptions:
        """Validate, sanitize, and resolve execute arguments."""
        self.validate_arguments(args)
        file_path = args["file_path"]
        resolved = self.resolve_and_validate_file_path(file_path)
        _ensure_input_file_exists(resolved, file_path)
        format_type = self._sanitize_optional_arg(args.get("format_type", "full"), 50)
        output_file = self._sanitize_optional_arg(args.get("output_file"), 255)
        language = self._resolve_language(args.get("language"), resolved)

        return _ExecutionOptions(
            file_path=file_path,
            resolved_path=resolved,
            format_type=format_type,
            language=language,
            output_file=output_file,
            suppress_output=args.get("suppress_output", False),
            output_format=args.get("output_format", "toon"),
        )

    def _sanitize_optional_arg(self, value: Any, max_length: int) -> Any:
        """Sanitize an optional string-like argument when it is present."""
        if not value:
            return value
        return self.security_validator.sanitize_input(value, max_length=max_length)

    def _resolve_language(self, language: Any, resolved_path: str) -> str:
        """Sanitize the explicit language or detect it from the resolved path."""
        sanitized = self._sanitize_optional_arg(language, 50)
        if sanitized:
            return cast(str, sanitized)
        return detect_language_from_file(resolved_path, project_root=self.project_root)

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
            saved = self.file_output_manager.save_to_file(
                content=table_output,
                base_name=_output_base_name(options),
            )
            _mark_file_saved(response, saved)
        except Exception as e:
            self.logger.error(f"Failed to save output to file: {e}")
            _mark_file_save_error(response, e)


# Tool instance for easy access
analyze_code_structure_tool = AnalyzeCodeStructureTool()
