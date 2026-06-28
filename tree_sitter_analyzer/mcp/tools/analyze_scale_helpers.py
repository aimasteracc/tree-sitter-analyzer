# Helper functions for code scale analysis
"""Extracted helper functions for AnalyzeScaleTool — keeps the main tool under 800 lines.

Phase 3 REQ-CLEAN-004: structural extraction and guidance builder moved to
utils/scale_structural_extractor.py and utils/scale_guidance_builder.py.
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
from ...utils import setup_logger
from ..utils.error_sanitizer import safe_error_message
from ..utils.file_metrics import compute_file_metrics
from .base_tool import format_summary_line

logger = setup_logger(__name__)


def validate_scale_arguments(arguments: dict[str, Any]) -> bool:
    """Validate file_path and option arguments for analyze scale tool."""
    # Issue 1: ``mode`` is dispatched on ``file_paths`` presence — accepting
    # arbitrary ``mode=`` values silently drops them. Echo back a clear
    # error pointing at the right dispatch contract instead of "passed
    # but ignored". Accept the canonical values for forward-compat.
    if "mode" in arguments and arguments["mode"] is not None:
        mode_value = arguments["mode"]
        if mode_value not in ("single", "batch", "batch_metrics"):
            raise ValueError(
                f"mode={mode_value!r} not supported. AnalyzeScale dispatches "
                "on file_paths presence: pass file_paths=[...] for batch, "
                "file_path='...' for single."
            )

    # Batch mode: file_paths array with metrics_only flag
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

    # Single file mode: file_path string required
    if "file_path" not in arguments:
        raise ValueError("Required field 'file_path' is missing")

    if "file_path" in arguments:
        fp = arguments["file_path"]
        if not isinstance(fp, str):
            raise ValueError("file_path must be a string")
        if not fp.strip():
            raise ValueError("file_path cannot be empty")

    for key in ("language",):
        if key in arguments and not isinstance(arguments[key], str):
            raise ValueError(f"{key} must be a string")

    for key in (
        "include_complexity",
        "include_details",
        "include_guidance",
    ):
        if key in arguments and not isinstance(arguments[key], bool):
            raise ValueError(f"{key} must be a boolean")

    return True


# create_json_file_analysis: extracted from AnalyzeScaleTool
# Produces analysis result for non-source files (JSON, YAML, TOML)
def create_json_file_analysis(
    file_path: str,
    file_metrics: dict[str, Any],
    include_guidance: bool,
    output_format: str = "toon",
) -> dict[str, Any]:
    """Create analysis for non-source files (JSON, YAML, etc.)."""
    from ..utils.format_helper import apply_toon_format_to_response as _apply_toon

    total_lines = file_metrics["total_lines"]
    # J5 (round-22): single-space join via helper.
    summary_line = format_summary_line(
        file_path,
        "json",
        f"{total_lines} lines",
        "classes=0",
        "methods=0",
        "fields=0",
        "(data file)",
    )
    result: dict[str, Any] = {
        "success": True,
        # Issue 2: echo dispatch mode + output_format on JSON-file path too.
        # F12: keep ``format`` as a back-compat alias of ``output_format`` so
        # JSON callers see the same key the TOON envelope already exposes.
        "mode": "single",
        "output_format": output_format,
        "format": output_format,
        "file_path": file_path,
        "language": "json",
        "file_size_bytes": file_metrics["file_size_bytes"],
        "total_lines": total_lines,
        "non_empty_lines": total_lines - file_metrics["blank_lines"],
        "estimated_tokens": file_metrics["estimated_tokens"],
        "complexity_metrics": {
            "total_elements": 0,
            "max_depth": 0,
            "avg_complexity": 0.0,
        },
        "structural_overview": {"classes": [], "methods": [], "fields": []},
        "scale_category": (
            "small"
            if total_lines < 100
            else "medium"
            if total_lines < 1000
            else "large"
        ),
        "analysis_recommendations": {
            "suitable_for_full_analysis": total_lines < 1000,
            "recommended_approach": "JSON files are configuration/data files - structural analysis not applicable",
            "token_efficiency_notes": "JSON files can be read directly without tree-sitter parsing",  # nosec
        },
        # One-line headline + next-step hint for LLM consumers.
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": "read_partial to inspect file content directly",
            # M9: analyze_scale is a measurement tool — emit ``INFO`` so
            # chained agents see a consistent ``verdict`` key across every
            # tool in the suite, even for the data-file fast path.
            "verdict": "INFO",
        },
    }

    if include_guidance:
        # Add LLM-specific guidance for non-source files
        result["llm_analysis_guidance"] = {
            "file_characteristics": "JSON configuration/data file",
            "recommended_workflow": "Direct file reading for content analysis",
            "token_optimization": "Use simple file reading tools for JSON content",  # nosec
            "analysis_focus": "Data structure and configuration values",
        }

    return _apply_toon(result, output_format)


# Assemble metrics, structure, and guidance into result
# Aggregates file metrics with element counts and structural overview
def build_analysis_result(
    file_path: str,
    language: str,
    file_metrics: dict[str, Any],
    analysis_result: Any,
    structural_overview: dict[str, Any],
    count_elements_fn: Any,
) -> dict[str, Any]:
    """Build the main analysis result dict."""
    elements = analysis_result.elements if analysis_result else []
    class_count = count_elements_fn(elements, ELEMENT_TYPE_CLASS, "class")
    method_count = count_elements_fn(elements, ELEMENT_TYPE_FUNCTION, "function")
    field_count = count_elements_fn(elements, ELEMENT_TYPE_VARIABLE, "variable")
    import_count = count_elements_fn(elements, ELEMENT_TYPE_IMPORT, "import")
    total_lines = file_metrics.get("total_lines") if file_metrics else None
    # Build a one-line headline an LLM (or grep) can parse.
    # J5 (round-22): single-space join via helper.
    line_total = total_lines if total_lines is not None else 0
    summary_line = format_summary_line(
        file_path,
        language,
        f"{line_total} lines",
        f"classes={class_count}",
        f"methods={method_count}",
        f"fields={field_count}",
    )
    # Suggest the next step — mirrors the workflow hint in
    # ``generate_llm_guidance`` but kept self-contained so it survives
    # ``include_guidance=False``.
    if total_lines and total_lines >= 500:
        next_step = "analyze_code_structure format=compact then extract_code_section for hotspots"
    else:
        next_step = "analyze_code_structure for full structure table"
    # M9 (round-26 dogfood): analyze_scale missed K12's verdict
    # normalization sweep — every other tool (code_patterns, safe_to_edit,
    # trace_impact, route_detector, build_project_index, ast_cache,
    # call_graph) exposes ``agent_summary.verdict`` so chained agents can
    # branch on a single key. analyze_scale is a pure measurement tool
    # (no safe/unsafe judgement), so the canonical placeholder is
    # ``"INFO"`` — the response describes the file rather than ruling on
    # it.
    agent_summary: dict[str, Any] = {
        "summary_line": summary_line,
        "next_step": next_step,
        "verdict": "INFO",
    }
    # Build result with metrics, element summary, and structural overview
    return {
        "success": True,
        "file_path": file_path,
        "language": language,
        "file_metrics": file_metrics,
        # Determine if file needs structural review
        "summary": {
            "classes": class_count,
            "methods": method_count,
            "fields": field_count,
            "imports": import_count,
            "annotations": len(
                getattr(analysis_result, "annotations", []) if analysis_result else []
            ),
            "package": (
                analysis_result.package.name
                if analysis_result and analysis_result.package
                else None
            ),
        },
        "structural_overview": structural_overview,
        # Top-level count aliases — match the field names used by
        # ``get_code_outline`` / ``file_health`` so callers reading any
        # tool's output find the same vocabulary. ``line_count`` is
        # hoisted from ``file_metrics`` for the same reason.
        "class_count": class_count,
        "method_count": method_count,
        "field_count": field_count,
        "import_count": import_count,
        "line_count": total_lines,
        # Top-level summary_line (mirror of agent_summary.summary_line) for
        # cross-tool consistency with modification_guard / safe_to_edit.
        "summary_line": summary_line,
        # r37x (envelope ratchet): top-level verdict mirror (r37u contract).
        "verdict": agent_summary["verdict"],
        "agent_summary": agent_summary,
    }


# Per-element detailed breakdown with full metadata
def build_detailed_analysis(analysis_result: Any, file_path: str) -> dict[str, Any]:
    """Build the detailed_analysis dict for include_details=True."""
    # Extract elements from analysis result
    elements = analysis_result.elements if analysis_result else []
    return {
        "statistics": (analysis_result.get_statistics() if analysis_result else {}),
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
                e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)
            ]
        ],
        # Format scale rating as human-readable label
        "methods": [
            {
                "name": method.name,
                "file_path": getattr(method, "file_path", file_path),
                "visibility": getattr(method, "visibility", "unknown"),
                "return_type": getattr(method, "return_type", "unknown"),
                "parameters": len(getattr(method, "parameters", [])),
                "annotations": [
                    getattr(ann, "name", str(ann))
                    for ann in getattr(method, "annotations", [])
                ],
                "is_constructor": getattr(method, "is_constructor", False),
                "is_static": getattr(method, "is_static", False),
                "complexity": getattr(method, "complexity_score", 0),
                "lines": f"{method.start_line}-{method.end_line}",
            }
            for method in [
                e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
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
                e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
            ]
        ],
    }


# ---------------------------------------------------------------------------
# Batch mode limits — shared between tool, validator, and response assembler
# ---------------------------------------------------------------------------
BATCH_MAX_FILES = 200
BATCH_CONCURRENCY = 4

# ---------------------------------------------------------------------------
# Tool input schema — module-level to avoid deep nesting inside class
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Argument validation helpers (no self required)
# ---------------------------------------------------------------------------


def validate_mode_argument(arguments: dict[str, Any]) -> None:
    """Reject unknown ``mode`` values early instead of silent no-op."""
    if "mode" not in arguments or arguments["mode"] is None:
        return
    mode_value = arguments["mode"]
    valid = ("single", "batch", "batch_metrics")
    if mode_value not in valid:
        raise ValueError(
            f"mode={mode_value!r} not supported. AnalyzeScale dispatches "
            "on file_paths presence: pass file_paths=[...] for batch, "
            "file_path='...' for single."
        )


def validate_batch_arguments(metrics_only: bool, file_paths: object) -> None:
    """Reject malformed batch inputs early with a precise message."""
    if not metrics_only:
        raise ValueError("metrics_only must be true when using file_paths batch mode")
    if not isinstance(file_paths, list) or not file_paths:
        raise ValueError("file_paths must be a non-empty list of strings")
    n = len(file_paths)
    if n > BATCH_MAX_FILES:
        msg = f"Too many files: {n} > max_files={BATCH_MAX_FILES}"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# File metrics helper — called by the thin class-method wrapper
# ---------------------------------------------------------------------------


def _do_compute_file_metrics(
    file_path: str,
    language: str | None,
    project_root: str | None,
) -> dict[str, Any]:
    """Compute file-level metrics; returns a dict with file_size_kb added."""
    try:
        metrics = compute_file_metrics(
            file_path, language=language, project_root=project_root
        )
        raw_size = metrics.get("file_size_bytes", 0)
        file_size_bytes = int(raw_size)
        return {**metrics, "file_size_kb": round(file_size_bytes / 1024, 2)}
    except Exception as e:
        logger.error("Error calculating file metrics for %s: %s", file_path, e)
        return {
            "total_lines": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 0,
            "file_size_bytes": 0,
            "file_size_kb": 0,
        }


# ---------------------------------------------------------------------------
# Count-elements impl — called by the thin class-method wrapper
# ---------------------------------------------------------------------------


def _count_elements_impl(
    elements: list,
    element_type_const: str,
    element_type_str: str,
) -> int:
    """Count elements matching either a typed constant or a string attribute."""
    count = 0
    for e in elements:
        if is_element_of_type(e, element_type_const):
            count += 1
        elif getattr(e, "element_type", "") == element_type_str:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Batch scatter helpers — extracted from _analyze_one_in_batch
# ---------------------------------------------------------------------------


def _resolve_batch_path(
    fp: str,
    resolve_fn: Any,
    project_root: str | None,
) -> tuple[str | None, str | None]:
    """Try to resolve *fp* via *resolve_fn*; return (resolved, error_msg)."""
    try:
        return resolve_fn(fp), None
    except ValueError as e:
        return None, safe_error_message(e, project_root)


async def _analyze_batch_item_core(
    fp: str,
    sem: Any,
    resolve_fn: Any,
    project_root: str | None,
    calc_fn: Any,
    detect_fn: Any,
) -> dict[str, Any]:
    """One file slot of the batch scatter: validate → resolve → metrics."""
    async with sem:
        if not isinstance(fp, str) or not fp.strip():
            return {"file_path": fp, "error": "file_path must be a non-empty string"}
        resolved, err = _resolve_batch_path(fp, resolve_fn, project_root)
        if err is not None or resolved is None:
            return {"file_path": fp, "error": err or "could not resolve path"}
        if not Path(resolved).exists():
            return {
                "file_path": fp,
                "resolved_path": resolved,
                "error": "Invalid file path: file does not exist",
            }
        lang: str | None = detect_fn(resolved, project_root=project_root)
        if lang == "unknown":
            lang = None
        metrics = calc_fn(resolved, lang)
        return {
            "file_path": fp,
            "resolved_path": resolved,
            "language": lang or "unknown",
            "metrics": metrics,
        }


# ---------------------------------------------------------------------------
# Batch response assembly — extracted from _assemble_batch_response
# ---------------------------------------------------------------------------


def assemble_batch_response(
    per_file: list[dict[str, Any]],
    file_paths: list[str],
    output_format: str,
    metrics_only: bool,
) -> dict[str, Any]:
    """Compose the canonical batch envelope (raw — caller applies TOON format)."""
    errors = [x for x in per_file if "error" in x]
    ok = [x for x in per_file if "error" not in x]
    n_ok = len(ok)
    n_files = len(file_paths)
    n_err = len(errors)
    summary_line = f"batch metrics: {n_ok}/{n_files} files ok, {n_err} errors"
    mode_label = "batch_metrics" if metrics_only else "batch"
    return {
        "success": n_ok > 0,
        "mode": mode_label,
        "output_format": output_format,
        "format": output_format,
        "count_files": n_files,
        "count_ok": n_ok,
        "count_errors": n_err,
        "limits": {
            "max_files": BATCH_MAX_FILES,
            "concurrency": BATCH_CONCURRENCY,
        },
        "results": per_file,
        "verdict": "INFO",
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": (
                "analyze_code_structure on the highest-line files for deeper inspection"
            ),
            "verdict": "INFO",
        },
    }
