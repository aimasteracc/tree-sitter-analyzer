# Helper functions for code scale analysis
"""Extracted helper functions for AnalyzeScaleTool — keeps the main tool under 800 lines."""

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

# ---------------------------------------------------------------------------
# Output size cap for the methods list (Bug #755).
# A large file can have tens of thousands of methods — emitting all of them
# inline produces multi-MB JSON that can crash agents. Cap the list and emit
# metadata so callers know the full count without the payload cost.
# ---------------------------------------------------------------------------
METHODS_OUTPUT_CAP = 50
HOTSPOTS_OUTPUT_CAP = 50


# Tree-sitter element extraction for structure view
# Converts unified analysis engine results into LLM-consumable dicts
def extract_structural_overview(
    analysis_result: Any,
    *,
    method_cap: int = METHODS_OUTPUT_CAP,
    hotspot_cap: int = HOTSPOTS_OUTPUT_CAP,
) -> dict[str, Any]:
    """Extract structural overview with position information for LLM guidance.

    r37bd (dogfood): tool flagged this at 112 lines. Split into 4
    per-element-type extractors that each return a list of dicts.
    Behaviour preserved (complexity_score >= 8 hotspot threshold,
    same shape for each element category).
    """
    elements = analysis_result.elements
    overview: dict[str, Any] = {
        "classes": _extract_class_infos(elements),
        "methods": [],  # filled below alongside complexity_hotspots
        "fields": _extract_field_infos(elements),
        "imports": _extract_import_infos(elements),
        "complexity_hotspots": [],
    }
    all_methods, hotspots = _extract_method_infos(elements)
    _apply_hotspot_cap(overview, hotspots, hotspot_cap)
    total_methods = len(all_methods)
    overview["total_methods"] = total_methods
    if total_methods > method_cap:
        overview["methods"] = all_methods[:method_cap]
        overview["methods_truncated"] = True
    else:
        overview["methods"] = all_methods
    return overview


def _extract_class_infos(elements: list[Any]) -> list[dict[str, Any]]:
    """Class element → dict with position + inheritance + annotations."""
    classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
    return [
        {
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
        for cls in classes
    ]


def _extract_method_infos(
    elements: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Method element → (method_infos, complexity_hotspots) with threshold ≥8."""
    method_infos: list[dict[str, Any]] = []
    hotspots: list[dict[str, Any]] = []
    for method in (e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)):
        method_infos.append(
            {
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
        )
        if method.complexity_score >= _COMPLEXITY_HOTSPOT_THRESHOLD:
            hotspots.append(
                {
                    "type": "method",
                    "name": method.name,
                    "complexity": method.complexity_score,
                    "start_line": method.start_line,
                    "end_line": method.end_line,
                }
            )
    return method_infos, hotspots


def _apply_hotspot_cap(
    overview: dict[str, Any], hotspots: list[dict[str, Any]], hotspot_cap: int
) -> None:
    """Cap hotspot payloads and expose metadata only when truncation occurs."""
    total_hotspots = len(hotspots)
    if total_hotspots > hotspot_cap:
        overview["complexity_hotspots"] = hotspots[:hotspot_cap]
        overview["total_complexity_hotspots"] = total_hotspots
        overview["complexity_hotspots_truncated"] = True
    else:
        overview["complexity_hotspots"] = hotspots


def _extract_field_infos(elements: list[Any]) -> list[dict[str, Any]]:
    """Field element → dict with type + modifiers + position."""
    fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
    return [
        {
            "name": field.name,
            "type": field.field_type,
            "start_line": field.start_line,
            "end_line": field.end_line,
            "visibility": field.visibility,
            "is_static": field.is_static,
            "is_final": field.is_final,
            "annotations": [ann.name for ann in field.annotations],
        }
        for field in fields
    ]


def _extract_import_infos(elements: list[Any]) -> list[dict[str, Any]]:
    """Import element → dict with statement + static/wildcard flags."""
    imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
    return [
        {
            "name": imp.imported_name,
            "statement": imp.import_statement,
            "line": imp.line_number,
            "is_static": imp.is_static,
            "is_wildcard": imp.is_wildcard,
        }
        for imp in imports
    ]


# r37bd: complexity threshold for hotspot reporting — extracted from the
# inline ``>= 8`` literal so tests can pin it as a single source of truth.
_COMPLEXITY_HOTSPOT_THRESHOLD = 8


def _make_hotspot_entry(
    name: str, complexity: Any, start_line: int, end_line: int
) -> dict[str, Any]:
    """Build a complexity hotspot dict for a method element."""
    return {
        "type": "method",
        "name": name,
        "complexity": complexity,
        "start_line": start_line,
        "end_line": end_line,
    }


# Universal extraction for non-Java/Python languages using tree-sitter
def extract_structural_overview_universal(
    analysis_result: Any,
    *,
    method_cap: int = METHODS_OUTPUT_CAP,
    hotspot_cap: int = HOTSPOTS_OUTPUT_CAP,
) -> dict[str, Any]:
    """Extract structural overview from universal analysis result (non-Java languages).

    Bug #755: the methods list is capped at ``method_cap`` entries (default
    ``METHODS_OUTPUT_CAP`` = 50) to prevent multi-MB output for large files.
    When the cap fires, two extra fields appear:
      - ``total_methods``: the full method count (always present)
      - ``methods_truncated``: True (only when the list was cut)
    """
    # Initialize empty overview containers
    overview: dict[str, Any] = {
        "classes": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "complexity_hotspots": [],
    }
    # Extract structural overview from tree-sitter elements

    # Guard against empty or invalid analysis results
    if not analysis_result or not hasattr(analysis_result, "elements"):
        overview["total_methods"] = 0
        return overview

    # Pre-bind lists to avoid deep subscript chains inside the loop
    _classes = overview["classes"]
    _all_methods: list[dict[str, Any]] = []
    _fields = overview["fields"]
    _imports = overview["imports"]
    _hotspots: list[dict[str, Any]] = []

    # Classify each element by its type and extract metadata
    for e in analysis_result.elements:
        etype = getattr(e, "element_type", "")
        name = getattr(e, "name", "unnamed")
        start_line = getattr(e, "start_line", 0)
        end_line = getattr(e, "end_line", 0)
        _line_span = end_line - start_line + 1
        _complexity_score = getattr(e, "complexity_score", 0)

        if etype == "class":
            _classes.append(
                {
                    "name": name,
                    "type": etype,
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_span": _line_span,
                }
            )
        elif etype in ("function", "method"):
            method_info = {
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
                "line_span": _line_span,
                "complexity": _complexity_score,
            }
            _all_methods.append(method_info)
            _entry = _make_hotspot_entry(name, _complexity_score, start_line, end_line)
            if _complexity_score and _complexity_score >= _COMPLEXITY_HOTSPOT_THRESHOLD:
                _hotspots.append(_entry)
        elif etype == "variable":
            _fields.append(
                {"name": name, "start_line": start_line, "end_line": end_line}
            )
        elif etype == "import":
            _imports.append({"name": name, "line": start_line})

    # Apply output cap (Bug #755)
    total_methods = len(_all_methods)
    overview["total_methods"] = total_methods
    if total_methods > method_cap:
        overview["methods"] = _all_methods[:method_cap]
        overview["methods_truncated"] = True
    else:
        overview["methods"] = _all_methods
    _apply_hotspot_cap(overview, _hotspots, hotspot_cap)

    return overview


# AI-oriented suggestions based on file analysis
# r37bd: per-language tree-sitter query priorities — extracted from the
# 65-line inline dict that drove a chunk of the long_method smell. New
# languages add a single dict entry; the guidance generator stays small.
_LANG_QUERIES: dict[str, list[str]] = {
    "java": ["methods", "classes", "imports", "spring_service", "jpa_entity"],
    "python": ["functions", "classes", "imports", "decorator", "async_patterns"],
    "javascript": ["functions", "classes", "imports", "export", "react_component"],
    "typescript": ["functions", "interfaces", "type_aliases", "enums", "decorators"],
    "go": ["function", "struct", "interface", "goroutine", "channel_send"],
    "rust": ["fn", "struct", "enum", "trait", "impl"],
    "c": ["function", "struct", "enum", "include", "typedef"],
    "cpp": ["class", "function", "namespace", "template", "include"],
    "kotlin": [
        "function",
        "class",
        "data_class",
        "object",
        "annotation",
        "companion_object",
        "sealed_class",
        "suspend_function",
        "extension_function",
        "when_expression",
    ],
    "csharp": ["class", "method", "property", "interface", "attribute"],
    "ruby": [
        "methods",
        "classes",
        "imports",
        "attr",
        "mixin",
        "inheritance",
        "block",
        "rescue",
        "yield",
    ],
    "php": [
        "methods",
        "classes",
        "imports",
        "namespace",
        "interface",
        "trait",
        "enum",
        "closure",
        "inheritance",
    ],
    "sql": ["functions", "table", "view", "trigger"],
    "html": ["element", "attribute", "form"],
    "css": ["selector", "property", "at_rule"],
    "yaml": ["key", "document", "anchor"],
    "markdown": ["headers", "code_blocks", "tables"],
}

_PRIORITY_QUERIES = frozenset(
    {
        "classes",
        "methods",
        "functions",
        "imports",
        "variables",
        "interface",
        "trait",
        "namespace",
        "decorator",
    }
)

_REQUIRED_OVERVIEW_FIELDS = (
    "complexity_hotspots",
    "classes",
    "methods",
    "fields",
    "imports",
)


def generate_llm_guidance(
    file_metrics: dict[str, Any], structural_overview: dict[str, Any]
) -> dict[str, Any]:
    """Generate guidance for LLM on how to efficiently analyze this file.

    r37bd (dogfood): tool flagged this at 226 lines. Split into 6 phases
    + 3 module-level data tables. Behaviour preserved (size thresholds
    100/500/1500, complexity_hotspot recommendation, dependency/health
    workflow tail).
    """
    total_lines = file_metrics["total_lines"]
    language = file_metrics.get("language", "")

    _ensure_required_overview_fields(structural_overview)

    guidance = _empty_guidance()
    _classify_size(guidance, total_lines)
    _recommend_tools(guidance, total_lines, structural_overview)
    _assess_complexity(guidance, structural_overview)
    _identify_key_areas(guidance, structural_overview)
    guidance["suggested_queries"] = _LANG_QUERIES.get(language, [])
    guidance["workflow_steps"] = _build_workflow_steps(guidance, structural_overview)
    _attach_available_queries(guidance, language)
    return guidance


def _empty_guidance() -> dict[str, Any]:
    """The skeleton guidance dict — 7 named fields, all empty/zero."""
    return {
        "analysis_strategy": "",
        "recommended_tools": [],
        "key_areas": [],
        "complexity_assessment": "",
        "size_category": "",
        "suggested_queries": [],
        "workflow_steps": [],
    }


def _ensure_required_overview_fields(structural_overview: dict[str, Any]) -> None:
    """Fill in missing keys so downstream lookups never KeyError."""
    for field in _REQUIRED_OVERVIEW_FIELDS:
        if field not in structural_overview:
            structural_overview[field] = []


def _classify_size(guidance: dict[str, Any], total_lines: int) -> None:
    """Pick a size_category + matching analysis_strategy from total_lines."""
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
            "This is a large file. Use targeted analysis with extract_code_section."
        )
    else:
        guidance["size_category"] = "very_large"
        guidance["analysis_strategy"] = (
            "This is a very large file. Strongly recommend using structural "
            "analysis first, then targeted deep-dives."
        )


def _recommend_tools(
    guidance: dict[str, Any],
    total_lines: int,
    structural_overview: dict[str, Any],
) -> None:
    """Append tool recommendations based on size + presence of hotspots."""
    if total_lines > 200:
        guidance["recommended_tools"].append("extract_code_section")
        guidance["recommended_tools"].append("query_code")
    if len(structural_overview["complexity_hotspots"]) > 0:
        guidance["recommended_tools"].append("analyze_code_structure")


def _assess_complexity(
    guidance: dict[str, Any], structural_overview: dict[str, Any]
) -> None:
    """Set complexity_assessment based on hotspot count."""
    hotspots = structural_overview["complexity_hotspots"]
    if len(hotspots) > 0:
        guidance["complexity_assessment"] = f"Found {len(hotspots)} complexity hotspots"
    else:
        guidance["complexity_assessment"] = (
            "No significant complexity hotspots detected"
        )


def _identify_key_areas(
    guidance: dict[str, Any], structural_overview: dict[str, Any]
) -> None:
    """Note structural characteristics worth surfacing to the agent."""
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


def _build_workflow_steps(
    guidance: dict[str, Any], structural_overview: dict[str, Any]
) -> list[str]:
    """Compose the ordered workflow_steps list — size-dependent middle, fixed tail."""
    steps = ["check_code_scale (done)"]
    if guidance["size_category"] in ("large", "very_large"):
        steps.extend(_large_file_steps(structural_overview))
    else:
        steps.extend(_small_or_medium_steps(structural_overview))

    if len(structural_overview.get("imports", [])) > 5:
        steps.append("analyze_dependencies mode=blast_radius to assess change impact")
    steps.append("check_file_health to see if this file needs refactoring")
    return steps


def _large_file_steps(structural_overview: dict[str, Any]) -> list[str]:
    """Targeted-analysis steps for files ≥500 lines."""
    steps = [
        "analyze_code_structure with format=compact for overview",
        "query_code with specific query keys to find target elements",
    ]
    hotspots = structural_overview.get("complexity_hotspots", [])
    if hotspots:
        top = hotspots[0]
        name = top.get("name", "hotspot")
        start = top.get("start_line", "")
        end = top.get("end_line", "")
        steps.append(
            f"extract_code_section for '{name}' (L{start}-{end}) - complexity hotspot"
        )
    else:
        steps.append("extract_code_section for targeted line ranges")
    return steps


def _small_or_medium_steps(structural_overview: dict[str, Any]) -> list[str]:
    """Full-analysis steps for files <500 lines."""
    steps = [
        "analyze_code_structure for full structure table",
        "query_code for specific elements if needed",
    ]
    notable = structural_overview.get("methods", [])
    long_methods = [
        m for m in notable if m.get("complexity", 0) >= _COMPLEXITY_HOTSPOT_THRESHOLD
    ]
    if long_methods:
        top = long_methods[0]
        start = top.get("start_line", "")
        end = top.get("end_line", "")
        steps.append(
            f"extract_code_section for '{top.get('name', 'method')}' "
            f"(L{start}-{end}) - high complexity"
        )
    return steps


def _attach_available_queries(guidance: dict[str, Any], language: str) -> None:
    """Look up tree-sitter queries for ``language`` and cap to 15 entries."""
    from ...query_loader import get_query_loader

    loader = get_query_loader()
    all_queries = loader.list_queries_for_language(language)
    if not all_queries:
        return
    priority = [q for q in all_queries if q in _PRIORITY_QUERIES]
    rest = sorted(q for q in all_queries if q not in priority)[: 15 - len(priority)]
    guidance["available_queries"] = sorted(priority) + rest


# validate_scale_arguments: implementation
# Input validation for batch and single-file analysis modes
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
