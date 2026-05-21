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

from ...constants import (
    is_element_of_type,
)
from ...core.analysis_engine import AnalysisRequest, get_analysis_engine
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils.error_sanitizer import safe_error_message
from ..utils.file_metrics import compute_file_metrics
from ..utils.format_helper import apply_toon_format_to_response
from .analyze_scale_helpers import (
    build_analysis_result,
    build_detailed_analysis,
    create_json_file_analysis,
    extract_structural_overview,
    extract_structural_overview_universal,
    generate_llm_guidance,
    validate_scale_arguments,
)
from .base_tool import (
    BaseMCPTool,
    detect_language_mismatch,
    language_mismatch_error_response,
)

# JSON schema for tool input validation
logger = setup_logger(__name__)

# r37bb: batch-mode limits — module-level so the validator + envelope
# stay in sync (previously a magic 200 literal lived in two places).
_BATCH_MAX_FILES = 200
_BATCH_CONCURRENCY = 4

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Batch mode (requires metrics_only=true)",
        },
        "metrics_only": {"type": "boolean", "default": False},
        "file_path": {"type": "string"},
        "language": {"type": "string"},
        "include_complexity": {"type": "boolean", "default": True},
        "include_details": {"type": "boolean", "default": False},
        "include_guidance": {"type": "boolean", "default": True},
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    "additionalProperties": False,
}


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
        # Use unified analysis engine instead of deprecated AdvancedAnalyzer.
        self.analysis_engine = get_analysis_engine(project_root)

    # _calculate_file_metrics: implementation
    def _calculate_file_metrics(
        self, file_path: str, language: str | None = None
    ) -> dict[str, Any]:
        """Compute file-level metrics (lines, complexity, size)."""
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

    # _extract_structural_overview: implementation
    def _extract_structural_overview(self, analysis_result: Any) -> dict[str, Any]:
        """Extract structural overview using Python-specific analysis."""
        return extract_structural_overview(analysis_result)

    # _extract_structural_overview_universal: implementation
    def _extract_structural_overview_universal(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """Extract structural overview using universal tree-sitter analysis."""
        return extract_structural_overview_universal(analysis_result)

    @staticmethod
    # _count_elements: implementation
    def _count_elements(
        elements: list, element_type_const: str, element_type_str: str
    ) -> int:
        """Count elements by type from analysis result."""
        count = 0
        for e in elements:
            if is_element_of_type(e, element_type_const):
                count += 1
            elif getattr(e, "element_type", "") == element_type_str:
                count += 1
        return count

    # _generate_llm_guidance: implementation
    def _generate_llm_guidance(
        self, file_metrics: dict[str, Any], structural_overview: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate LLM-oriented guidance based on analysis."""
        return generate_llm_guidance(file_metrics, structural_overview)

    # get_tool_schema: implementation
    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    # Main entry point - dispatches to mode-specific handler
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute code scale analysis for single or batch files.

        r37bb (dogfood): tool flagged this at 118 lines. Split into
        argument validation + dispatch + single-file pipeline. Behaviour
        preserved (Issue 1 mode gate, K12 path normalize, O3 mismatch,
        F12 format echo, M9 verdict — all kept exactly).
        """
        self._validate_mode_argument(arguments)

        if "file_paths" in arguments and arguments["file_paths"] is not None:
            return await self._execute_metrics_batch(arguments)

        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        return await self._execute_single_file(arguments)

    @staticmethod
    def _validate_mode_argument(arguments: dict[str, Any]) -> None:
        """Issue 1: reject unknown ``mode`` early instead of silent no-op."""
        if "mode" not in arguments or arguments["mode"] is None:
            return
        mode_value = arguments["mode"]
        if mode_value not in ("single", "batch", "batch_metrics"):
            raise ValueError(
                f"mode={mode_value!r} not supported. AnalyzeScale dispatches "
                "on file_paths presence: pass file_paths=[...] for batch, "
                "file_path='...' for single."
            )

    async def _execute_single_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Single-file analysis path — orchestrates the 4 phases linearly."""
        # K12: normalize the echoed file_path so ``./X`` and ``X`` produce
        # byte-identical responses — confuses downstream dedup/caching otherwise.
        file_path = self._normalize_file_path(arguments["file_path"])
        language = arguments.get("language")
        include_details = arguments.get("include_details", False)
        include_guidance = arguments.get("include_guidance", True)
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        logger.info(f"Analyzing file: {file_path} (resolved to: {resolved})")

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
        logger.info(f"Analyzing code scale for {resolved} (language: {language})")

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
            logger.error(f"Error analyzing {file_path}: {e}")
            raise

    def _check_language_mismatch(
        self,
        file_path: str,
        resolved: str,
        language: str | None,
        output_format: str,
    ) -> dict[str, Any] | None:
        """O3 dogfood: refuse ``language='java'`` on a ``.py`` file, return envelope."""
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
            # Issue 2 + F12: echo dispatch mode + format aliases.
            result["mode"] = "single"
            result["output_format"] = output_format
            result["format"] = output_format

            logger.info(
                f"Successfully analyzed {file_path}: "
                f"{file_metrics['total_lines']} lines, "
                f"~{file_metrics['estimated_tokens']} tokens"
            )

            return apply_toon_format_to_response(result, output_format)

    # _resolve_language: implementation
    def _resolve_language(self, resolved: str, language: str | None) -> str:
        """Detect language from file extension or argument override."""
        # Conditional check
        if language:
            return language
        detected = detect_language_from_file(resolved, project_root=self.project_root)
        # Conditional check
        if detected == "unknown":
            raise ValueError(
                f"Invalid file path: Unsupported language for file: {resolved}"
            )
        return detected

    # _run_structural_analysis: implementation
    async def _run_structural_analysis(
        self, resolved: str, language: str, include_details: bool
    ) -> tuple[Any, dict[str, Any]]:
        """Run structural analysis using tree-sitter elements."""
        # Conditional check
        if language == "java":
            request = AnalysisRequest(
                file_path=resolved,
                language=language,
                include_complexity=True,
                include_details=True,
            )
            result = await self.analysis_engine.analyze(request)
            # Conditional check
            if result is None:
                raise RuntimeError(f"Failed to analyze file: {resolved}")
            return result, self._extract_structural_overview(result)

        request = AnalysisRequest(
            file_path=resolved,
            language=language,
            include_details=include_details,
        )
        universal_result = await self.analysis_engine.analyze(request)
        # Conditional check
        if not universal_result or not universal_result.success:
            error_msg = (
                universal_result.error_message or "Unknown error"
                if universal_result
                else "Unknown error"
            )
            raise RuntimeError(
                f"Failed to analyze file with universal engine: {error_msg}"
            )

        return universal_result, self._extract_structural_overview_universal(
            universal_result
        )

    # _build_enhanced_result: implementation
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

        # Conditional check
        if include_guidance:
            guidance_metrics = {**file_metrics, "language": language}
            result["llm_guidance"] = self._generate_llm_guidance(
                guidance_metrics,
                structural_overview,
                # Batch metrics computation for multiple files
            )

        # Conditional check
        if include_details:
            result["detailed_analysis"] = build_detailed_analysis(
                analysis_result, file_path
            )

        return result

    async def _execute_metrics_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute batch metrics computation for multiple files.

        r37bb (dogfood): split into validation + parallel scatter +
        envelope assembly. Behaviour preserved (Issue 2/3 echo, F12
        format alias, M9 verdict, max_files=200, concurrency=4).
        """
        output_format = arguments.get("output_format", "toon")
        metrics_only = bool(arguments.get("metrics_only", False))
        file_paths = arguments.get("file_paths")

        self._validate_batch_arguments(metrics_only, file_paths)
        # After validation we know ``file_paths`` is a non-empty ``list[str]``.
        # Use ``cast`` (typing-only, no runtime assert) so we don't trip the
        # ``assert_in_prod`` smell — production code that runs with ``-O``
        # would strip a real ``assert`` and break mypy's narrowing here.
        file_paths_list = cast("list[str]", file_paths)

        per_file = await self._scatter_batch_metrics(file_paths_list)
        return self._assemble_batch_response(
            per_file, file_paths_list, output_format, metrics_only
        )

    @staticmethod
    def _validate_batch_arguments(metrics_only: bool, file_paths: object) -> None:
        """Reject malformed batch inputs early with a precise message."""
        if not metrics_only:
            raise ValueError(
                "metrics_only must be true when using file_paths batch mode"
            )
        if not isinstance(file_paths, list) or not file_paths:
            raise ValueError("file_paths must be a non-empty list of strings")
        max_files = _BATCH_MAX_FILES
        if len(file_paths) > max_files:
            raise ValueError(
                f"Too many files: {len(file_paths)} > max_files={max_files}"
            )

    async def _scatter_batch_metrics(
        self, file_paths: list[str]
    ) -> list[dict[str, Any]]:
        """Fan out per-file analysis with a 4-way semaphore — order preserved."""
        import asyncio

        sem = asyncio.Semaphore(_BATCH_CONCURRENCY)
        return list(
            await asyncio.gather(
                *[self._analyze_one_in_batch(fp, sem) for fp in file_paths]
            )
        )

    async def _analyze_one_in_batch(self, fp: str, sem: Any) -> dict[str, Any]:
        """One file slot of the scatter: validate → resolve → metrics."""
        async with sem:
            if not isinstance(fp, str) or not fp.strip():
                return {
                    "file_path": fp,
                    "error": "file_path must be a non-empty string",
                }
            try:
                resolved = self.resolve_and_validate_file_path(fp)
            except ValueError as e:
                return {
                    "file_path": fp,
                    "error": safe_error_message(e, self.project_root),
                }
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

    def _assemble_batch_response(
        self,
        per_file: list[dict[str, Any]],
        file_paths: list[str],
        output_format: str,
        metrics_only: bool,
    ) -> dict[str, Any]:
        """Compose the canonical batch envelope + apply TOON formatting."""
        errors = [x for x in per_file if "error" in x]
        ok = [x for x in per_file if "error" not in x]
        summary_line = (
            f"batch metrics: {len(ok)}/{len(file_paths)} files ok, {len(errors)} errors"
        )
        response: dict[str, Any] = {
            "success": len(ok) > 0,
            "mode": "batch_metrics" if metrics_only else "batch",
            "output_format": output_format,
            "format": output_format,
            "count_files": len(file_paths),
            "count_ok": len(ok),
            "count_errors": len(errors),
            "limits": {
                "max_files": _BATCH_MAX_FILES,
                "concurrency": _BATCH_CONCURRENCY,
            },
            "results": per_file,
            "verdict": "INFO",  # r37x: top-level verdict mirror
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": (
                    "analyze_code_structure on the highest-line files for "
                    "deeper inspection"
                ),
                "verdict": "INFO",  # M9: measurement tool emits INFO
            },
        }
        return apply_toon_format_to_response(response, output_format)

    # Input validation - delegates to shared helper
    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate file_path and option arguments."""
        return validate_scale_arguments(arguments)

    # _create_json_file_analysis: delegates to shared helper
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

    # MCP tool metadata - name, description, schema
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "check_code_scale",
            "description": (
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
            ),
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy access
analyze_scale_tool = AnalyzeScaleTool()
