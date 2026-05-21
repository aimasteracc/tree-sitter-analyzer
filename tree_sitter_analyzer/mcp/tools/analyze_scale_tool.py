# Code scale analysis: metrics, complexity, and structure
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
        """Execute code scale analysis for single or batch files."""
        # Issue 1: validate ``mode`` early so unknown values raise instead
        # of silently no-op'ing. The full validator is heavier (file_paths
        # / file_path checks), so this only enforces the mode-typo gate.
        if "mode" in arguments and arguments["mode"] is not None:
            mode_value = arguments["mode"]
            if mode_value not in ("single", "batch", "batch_metrics"):
                raise ValueError(
                    f"mode={mode_value!r} not supported. AnalyzeScale dispatches "
                    "on file_paths presence: pass file_paths=[...] for batch, "
                    "file_path='...' for single."
                )

        # Conditional check
        if "file_paths" in arguments and arguments["file_paths"] is not None:
            return await self._execute_metrics_batch(arguments)

        # Conditional check
        if "file_path" not in arguments:
            raise ValueError("file_path is required")

        # K12: normalize the echoed file_path so ``./X`` and ``X`` produce
        # byte-identical responses — confuses downstream dedup/caching/
        # display otherwise.
        file_path = self._normalize_file_path(arguments["file_path"])
        language = arguments.get("language")
        include_details = arguments.get("include_details", False)
        include_guidance = arguments.get("include_guidance", True)
        output_format = arguments.get("output_format", "toon")

        resolved = self.resolve_and_validate_file_path(file_path)
        logger.info(f"Analyzing file: {file_path} (resolved to: {resolved})")

        # Conditional check
        if language:
            language = self.security_validator.sanitize_input(language, max_length=50)

        # Conditional check
        if not Path(resolved).exists():
            raise ValueError(f"Invalid file path: File not found: {file_path}")

        # O3 (round-30 dogfood): strict mismatch gate — refuse
        # ``language='java'`` on a ``.py`` file with a canonical
        # validation envelope. Without this analyze_scale silently
        # produced bogus structural counts.
        mismatch = detect_language_mismatch(
            resolved,
            language,
            project_root=self.project_root,
        )
        if mismatch:
            response = language_mismatch_error_response(
                tool_name="analyze_scale",
                file_path=file_path,
                warning=mismatch,
            )
            response["output_format"] = output_format
            response["mode"] = "single"
            response["format"] = output_format
            return response

        language = self._resolve_language(resolved, language)
        logger.info(f"Analyzing code scale for {resolved} (language: {language})")

        # Error handling
        try:
            from ...mcp.utils import get_performance_monitor

            with get_performance_monitor().measure_operation(
                "analyze_code_scale_enhanced"
            ):
                file_metrics = self._calculate_file_metrics(resolved, language)

                # Conditional check
                if language == "json":
                    return self._create_json_file_analysis(
                        resolved, file_metrics, include_guidance, output_format
                    )

                (
                    analysis_result,
                    structural_overview,
                ) = await self._run_structural_analysis(
                    resolved, language, include_details
                )

                result = self._build_enhanced_result(
                    file_path,
                    language,
                    file_metrics,
                    analysis_result,
                    structural_overview,
                    include_guidance,
                    include_details,
                )
                # Issue 2: echo dispatch mode + output_format on the
                # single-file path so callers can audit envelope parity.
                # F12: ``format`` is kept as a back-compat alias of
                # ``output_format`` so JSON callers see the same key the
                # TOON envelope already exposes (round-16b dogfood saw the
                # JSON path miss ``format`` entirely).
                result["mode"] = "single"
                result["output_format"] = output_format
                result["format"] = output_format

                logger.info(
                    f"Successfully analyzed {file_path}: "
                    f"{file_metrics['total_lines']} lines, "
                    f"~{file_metrics['estimated_tokens']} tokens"
                )

                return apply_toon_format_to_response(result, output_format)
        # Language detection with argument override

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            raise

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

    # _execute_metrics_batch: implementation
    async def _execute_metrics_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute batch metrics computation for multiple files."""
        output_format = arguments.get("output_format", "toon")
        metrics_only = bool(arguments.get("metrics_only", False))
        file_paths = arguments.get("file_paths")

        # Conditional check
        if not metrics_only:
            raise ValueError(
                "metrics_only must be true when using file_paths batch mode"
            )
        # Conditional check
        if not isinstance(file_paths, list) or not file_paths:
            raise ValueError("file_paths must be a non-empty list of strings")

        max_files = 200
        # Conditional check
        if len(file_paths) > max_files:
            raise ValueError(
                f"Too many files: {len(file_paths)} > max_files={max_files}"
            )

        import asyncio

        sem = asyncio.Semaphore(4)

        # _one: implementation
        async def _one(fp: str) -> dict[str, Any]:
            """Analyze a single file in batch mode."""
            async with sem:
                # Conditional check
                if not isinstance(fp, str) or not fp.strip():
                    return {
                        "file_path": fp,
                        "error": "file_path must be a non-empty string",
                    }
                # Error handling
                try:
                    resolved = self.resolve_and_validate_file_path(fp)
                except ValueError as e:
                    return {
                        "file_path": fp,
                        "error": safe_error_message(e, self.project_root),
                    }

                # Conditional check
                if not Path(resolved).exists():
                    return {
                        "file_path": fp,
                        "resolved_path": resolved,
                        "error": "Invalid file path: file does not exist",
                    }

                lang: str | None = detect_language_from_file(
                    resolved, project_root=self.project_root
                )
                # Conditional check
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

        # One-line headline for batch mode — surface the success ratio at a glance.
        summary_line = (
            f"batch metrics: {len(ok)}/{len(file_paths)} files ok, {len(errors)} errors"
        )
        # Issue 2: echo ``mode`` + ``output_format`` so agents can audit
        # which dispatch path ran without re-reading their own call site.
        # Issue 3: ``summary_line`` lives only on ``agent_summary`` in batch
        # mode — the previous top-level mirror duplicated tokens for no win.
        # F12: keep ``format`` as a back-compat alias of ``output_format``
        # so the JSON and TOON paths expose the same key everywhere.
        response: dict[str, Any] = {
            "success": len(ok) > 0,
            "mode": "batch_metrics" if metrics_only else "batch",
            "output_format": output_format,
            "format": output_format,
            "count_files": len(file_paths),
            "count_ok": len(ok),
            "count_errors": len(errors),
            "limits": {"max_files": max_files, "concurrency": 4},
            "results": per_file,
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": (
                    "analyze_code_structure on the highest-line files for deeper inspection"
                ),
                # M9: analyze_scale is a measurement tool — emit ``INFO``
                # so every dispatch mode (single + batch) exposes the
                # same ``verdict`` key.
                "verdict": "INFO",
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
                "Analyze (use FIRST): file size, element counts, complexity. "
                "Batch supported. Use before analyze_code_structure."
            ),
            "inputSchema": self.get_tool_schema(),
        }


# Tool instance for easy access
analyze_scale_tool = AnalyzeScaleTool()
