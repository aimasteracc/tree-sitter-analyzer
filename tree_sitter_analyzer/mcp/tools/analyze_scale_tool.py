# Code scale analysis: metrics, complexity, and structure
#!/usr/bin/env python3
"""
Analyze Code Scale MCP Tool

This tool provides code scale analysis including metrics about
complexity, size, and structure through the MCP protocol.
Enhanced for LLM-friendly analysis workflow.
"""

from pathlib import Path
from typing import Any, cast

from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .analyze_scale_helpers import (
    BATCH_CONCURRENCY,
    TOOL_SCHEMA,
    _analyze_batch_item_core,
    _count_elements_impl,
    _do_compute_file_metrics,
    assemble_batch_response,
    build_analysis_result,
    build_detailed_analysis,
    create_json_file_analysis,
    extract_structural_overview,
    extract_structural_overview_universal,
    generate_llm_guidance,
    validate_batch_arguments,
    validate_mode_argument,
    validate_scale_arguments,
)
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    language_mismatch_error_response,
)

logger = setup_logger(__name__)

# Tool description constant — avoids escape sequences deep inside method body
_TOOL_DESCRIPTION = (
    "Cheap structural metrics for a file: line count, "
    "method/class/field/import counts, and a complexity estimate. "
    "Always call this FIRST when sizing an unknown file — it "
    "tells you whether the file is small enough for full analysis, "
    "or so large you need partial_read instead. Supports batch "
    "mode (metrics_only=true) for whole-directory scans.\n\n"
    "WHEN TO USE:\n"
    "- Sizing an unknown file before deeper analysis\n"
    "- Comparing two files / detecting outliers in a project scan\n"
    "- Picking files that warrant code_patterns / file_health\n"
    "- Batch counting elements across many files at once\n"
    "\n"
    "WHEN NOT TO USE:\n"
    "- To READ the file's content — use partial_read\n"
    "- To get the file's symbol outline — use get_code_outline\n"
    "- To judge code quality / smells — use file_health"
)


class AnalyzeScaleTool(BaseMCPTool):
    """
    MCP Tool for analyzing code scale and complexity metrics.

    This tool integrates with existing analyzer components to provide
    comprehensive code analysis through the MCP protocol, optimized
    for LLM workflow efficiency.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the analyze scale tool."""
        self.analysis_engine: Any = None  # set by the hook below
        super().__init__(project_root)
        logger.info("AnalyzeScaleTool initialized with security validation")

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self.analysis_engine = get_analysis_engine(project_root)

    def _calculate_file_metrics(
        self, file_path: str, language: str | None = None
    ) -> dict[str, Any]:
        """Compute file-level metrics (lines, complexity, size)."""
        return _do_compute_file_metrics(file_path, language, self.project_root)

    def _extract_structural_overview(self, analysis_result: Any) -> dict[str, Any]:
        """Extract structural overview using Python-specific analysis."""
        return extract_structural_overview(analysis_result)

    def _extract_structural_overview_universal(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """Extract structural overview using universal tree-sitter analysis."""
        return extract_structural_overview_universal(analysis_result)

    def _count_elements(
        self, elements: list, element_type_const: str, element_type_str: str
    ) -> int:
        """Count elements by type from analysis result."""
        return _count_elements_impl(elements, element_type_const, element_type_str)

    def _generate_llm_guidance(
        self, file_metrics: dict[str, Any], structural_overview: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate LLM-oriented guidance based on analysis."""
        return generate_llm_guidance(file_metrics, structural_overview)

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute code scale analysis for single or batch files."""
        validate_mode_argument(arguments)

        if "file_paths" in arguments and arguments["file_paths"] is not None:
            return await self._execute_metrics_batch(arguments)

        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        return await self._execute_single_file(arguments)

    async def _execute_single_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Single-file analysis path — orchestrates the 4 phases linearly."""
        file_path = self._normalize_file_path(arguments["file_path"])
        language = arguments.get("language")
        include_details = arguments.get("include_details", False)
        include_guidance = arguments.get("include_guidance", True)
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        logger.info("Analyzing file: %s (resolved to: %s)", file_path, resolved)

        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)
        if not Path(resolved).exists():
            raise ValueError(f"Invalid file path: File not found: {file_path}")

        mismatch_response = self._check_language_mismatch(
            file_path, resolved, language, output_format
        )
        if mismatch_response is not None:
            return mismatch_response

        language = self._resolve_language(resolved, language)
        logger.info("Analyzing code scale for %s (language: %s)", resolved, language)

        try:
            return await self._build_single_file_response(
                file_path,
                resolved,
                language,
                include_details,
                include_guidance,
                output_format,
            )
        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)
            raise

    def _check_language_mismatch(
        self,
        file_path: str,
        resolved: str,
        language: str | None,
        output_format: str,
    ) -> dict[str, Any] | None:
        """Refuse ``language='java'`` on a ``.py`` file, return envelope."""
        mismatch = detect_language_mismatch(
            resolved,
            language,
            project_root=self.project_root,
        )
        if not mismatch:
            return None
        response = language_mismatch_error_response(
            tool_name="analyze_scale",
            file_path=file_path,
            warning=mismatch,
        )
        response["output_format"] = output_format
        response["mode"] = "single"
        response["format"] = output_format
        return response

    async def _build_single_file_response(
        self,
        file_path: str,
        resolved: str,
        language: str,
        include_details: bool,
        include_guidance: bool,
        output_format: str,
    ) -> dict[str, Any]:
        """Run the actual metrics+structural pipeline inside the perf monitor."""
        from ...mcp.utils import get_performance_monitor

        with get_performance_monitor().measure_operation("analyze_code_scale_enhanced"):
            file_metrics = self._calculate_file_metrics(resolved, language)

            if language == "json":
                return self._create_json_file_analysis(
                    resolved, file_metrics, include_guidance, output_format
                )

            (
                analysis_result,
                structural_overview,
            ) = await self._run_structural_analysis(resolved, language, include_details)

            result = self._build_enhanced_result(
                file_path,
                language,
                file_metrics,
                analysis_result,
                structural_overview,
                include_guidance,
                include_details,
            )
            result["mode"] = "single"
            result["output_format"] = output_format
            result["format"] = output_format

            total_lines = file_metrics["total_lines"]
            est_tokens = file_metrics["estimated_tokens"]
            logger.info(
                "Successfully analyzed %s: %s lines, ~%s tokens",
                file_path,
                total_lines,
                est_tokens,
            )

            return apply_toon_format_to_response(result, output_format)

    def _resolve_language(self, resolved: str, language: str | None) -> str:
        """Detect language from file extension or argument override."""
        if language:
            return language
        detected = detect_language_from_file(resolved, project_root=self.project_root)
        if detected == "unknown":
            raise ValueError(
                f"Invalid file path: Unsupported language for file: {resolved}"
            )
        return detected

    async def _run_structural_analysis(
        self, resolved: str, language: str, include_details: bool
    ) -> tuple[Any, dict[str, Any]]:
        """Run structural analysis using tree-sitter elements."""
        _engine = self.analysis_engine
        if language == "java":
            # Pre-compute error prefix at this level — avoids depth-13 string
            # inside the nested "if result is None:" block below.
            fail_prefix = "Failed to analyze file: " + resolved
            request = AnalysisRequest(
                file_path=resolved,
                language=language,
                include_complexity=True,
                include_details=True,
            )
            result = await _engine.analyze(request)
            if result is None:
                raise RuntimeError(fail_prefix)
            return result, self._extract_structural_overview(result)

        request = AnalysisRequest(
            file_path=resolved,
            language=language,
            include_details=include_details,
        )
        universal_result = await _engine.analyze(request)
        if not universal_result or not universal_result.success:
            # Default first — keeps the string literal at a shallow depth.
            error_msg = "Unknown error"
            if universal_result and universal_result.error_message:
                error_msg = universal_result.error_message
            raise RuntimeError(
                f"Failed to analyze file with universal engine: {error_msg}"
            )

        return universal_result, self._extract_structural_overview_universal(
            universal_result
        )

    def _build_enhanced_result(
        self,
        file_path: str,
        language: str,
        file_metrics: dict[str, Any],
        analysis_result: Any,
        structural_overview: dict[str, Any],
        include_guidance: bool,
        include_details: bool,
    ) -> dict[str, Any]:
        """Build enhanced result with metrics, structure, and guidance."""
        result = build_analysis_result(
            file_path,
            language,
            file_metrics,
            analysis_result,
            structural_overview,
            self._count_elements,
        )

        if include_guidance:
            guidance_metrics = {**file_metrics, "language": language}
            result["llm_guidance"] = self._generate_llm_guidance(
                guidance_metrics,
                structural_overview,
            )

        if include_details:
            result["detailed_analysis"] = build_detailed_analysis(
                analysis_result, file_path
            )

        return result

    async def _execute_metrics_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute batch metrics computation for multiple files."""
        output_format = arguments.get("output_format", "toon")
        metrics_only = bool(arguments.get("metrics_only", False))
        file_paths = arguments.get("file_paths")

        validate_batch_arguments(metrics_only, file_paths)
        file_paths_list = cast("list[str]", file_paths)

        per_file = await self._scatter_batch_metrics(file_paths_list)
        response = assemble_batch_response(
            per_file, file_paths_list, output_format, metrics_only
        )
        return apply_toon_format_to_response(response, output_format)

    async def _scatter_batch_metrics(
        self, file_paths: list[str]
    ) -> list[dict[str, Any]]:
        """Fan out per-file analysis with a semaphore — order preserved."""
        import asyncio

        sem = asyncio.Semaphore(BATCH_CONCURRENCY)
        _root = self.project_root
        _resolve = self.resolve_and_validate_file_path
        _calc = self._calculate_file_metrics
        _detect = detect_language_from_file
        coros = [
            _analyze_batch_item_core(fp, sem, _resolve, _root, _calc, _detect)
            for fp in file_paths
        ]
        gathered = await asyncio.gather(*coros)
        return list(gathered)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path and option arguments."""
        return validate_scale_arguments(arguments)

    def _create_json_file_analysis(
        self,
        file_path: str,
        file_metrics: dict[str, Any],
        include_guidance: bool,
        output_format: str = "toon",
    ) -> dict[str, Any]:
        """Create analysis for non-source files (JSON, YAML, etc.)."""
        return create_json_file_analysis(
            file_path, file_metrics, include_guidance, output_format
        )

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "check_code_scale",
            "description": _TOOL_DESCRIPTION,
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


# Tool instance for easy access
analyze_scale_tool = AnalyzeScaleTool()
