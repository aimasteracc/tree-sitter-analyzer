# Helper functions for code scale analysis
"""Extracted helper functions for AnalyzeScaleTool — keeps the main tool under 800 lines."""

from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...utils import setup_logger

logger = setup_logger(__name__)


# Tree-sitter element extraction for structure view
# Converts unified analysis engine results into LLM-consumable dicts
def extract_structural_overview(analysis_result: Any) -> dict[str, Any]:
    """Extract structural overview with position information for LLM guidance."""
    # Initialize overview containers for each element type
    overview: dict[str, Any] = {
        "classes": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "complexity_hotspots": [],
    }

    # Extract class information with position from unified analysis engine
    classes = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_CLASS)
        # Build main analysis result dict
    ]
    for cls in classes:
        # Build class info dict with position and inheritance details
        class_info = {
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
        overview["classes"].append(class_info)

    # Filter methods and extract signature details with complexity scores
    # Extract method information with position and complexity from unified analysis engine
    methods = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
    ]
    for method in methods:
        # Build method info dict with signature and complexity
        method_info = {
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
        overview["methods"].append(method_info)

        # Track complexity hotspots (top methods worth reviewing)
        if method.complexity_score >= 8:
            overview["complexity_hotspots"].append(
                {
                    "type": "method",
                    "name": method.name,
                    "complexity": method.complexity_score,
                    "start_line": method.start_line,
                    "end_line": method.end_line,
                }
            )

    # Extract field information with position
    # Filter fields by variable type and extract type/modifier metadata
    # Build detailed per-element breakdown
    # Extract field information from unified analysis engine
    fields = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
    ]
    for field in fields:
        # Build field info dict with type and modifiers
        field_info = {
            "name": field.name,
            "type": field.field_type,
            "start_line": field.start_line,
            "end_line": field.end_line,
            "visibility": field.visibility,
            "is_static": field.is_static,
            "is_final": field.is_final,
            "annotations": [ann.name for ann in field.annotations],
        }
        overview["fields"].append(field_info)

    # Extract import information
    # Filter imports and extract statement details with static/wildcard flags
    # Extract import information from unified analysis engine
    imports = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
    ]
    for imp in imports:
        # Build import info dict with statement details
        import_info = {
            "name": imp.imported_name,
            "statement": imp.import_statement,
            "line": imp.line_number,
            "is_static": imp.is_static,
            "is_wildcard": imp.is_wildcard,
        }
        overview["imports"].append(import_info)

    return overview


# Universal extraction for non-Java/Python languages using tree-sitter
def extract_structural_overview_universal(
    analysis_result: Any,
) -> dict[str, Any]:
    """Extract structural overview from universal analysis result (non-Java languages)."""
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
        return overview

    # Classify each element by its type and extract metadata
    for e in analysis_result.elements:
        etype = getattr(e, "element_type", "")
        name = getattr(e, "name", "unnamed")
        start_line = getattr(e, "start_line", 0)
        end_line = getattr(e, "end_line", 0)

        if etype == "class":
            # Build class entry with line span
            overview["classes"].append(
                {
                    "name": name,
                    "type": etype,
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_span": end_line - start_line + 1,
                }
            )
        elif etype in ("function", "method"):
            # Build method entry with complexity tracking
            method_info = {
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
                "line_span": end_line - start_line + 1,
                "complexity": getattr(e, "complexity_score", 0),
            }
            overview["methods"].append(method_info)
            complexity = getattr(e, "complexity_score", 0)
            # Flag methods with high complexity as hotspots
            if complexity and complexity >= 8:
                overview["complexity_hotspots"].append(
                    {
                        "type": "method",
                        "name": name,
                        "complexity": complexity,
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                )
        elif etype == "variable":
            # Build field entry with position info
            overview["fields"].append(
                {
                    "name": name,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )
        elif etype == "import":
            # Build import entry (simplified for non-Java files)
            overview["imports"].append(
                # Extract structural overview for non-Python files
                {
                    "name": name,
                    "line": start_line,
                }
            )

    return overview


# AI-oriented suggestions based on file analysis
def generate_llm_guidance(
    file_metrics: dict[str, Any], structural_overview: dict[str, Any]
) -> dict[str, Any]:
    """Generate guidance for LLM on how to efficiently analyze this file."""
    guidance: dict[str, Any] = {
        "analysis_strategy": "",
        "recommended_tools": [],
        "key_areas": [],
        "complexity_assessment": "",
        "size_category": "",
        "suggested_queries": [],
        "workflow_steps": [],
    }

    total_lines = file_metrics["total_lines"]
    language = file_metrics.get("language", "")

    # Determine size category
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
            "This is a very large file. Strongly recommend using structural analysis first, then targeted deep-dives."
        )

    # Recommend tools based on file size and complexity
    if total_lines > 200:
        # Large files benefit from targeted extraction
        guidance["recommended_tools"].append("extract_code_section")
        guidance["recommended_tools"].append("query_code")

    # Ensure all required fields exist in structural_overview
    required_fields = [
        "complexity_hotspots",
        "classes",
        "methods",
        "fields",
        "imports",
    ]
    for field in required_fields:
        if field not in structural_overview:
            structural_overview[field] = []

    # Check for complexity hotspots and recommend structural analysis
    if len(structural_overview["complexity_hotspots"]) > 0:
        guidance["recommended_tools"].append("analyze_code_structure")
        guidance["complexity_assessment"] = (
            f"Found {len(structural_overview['complexity_hotspots'])} complexity hotspots"
        )
    else:
        guidance["complexity_assessment"] = (
            "No significant complexity hotspots detected"
        )

    # Identify key areas for analysis
    if len(structural_overview["classes"]) > 1:
        guidance["key_areas"].append(
            "Multiple classes - consider analyzing class relationships"
        )
    # Compute cyclomatic complexity for a function

    if len(structural_overview["methods"]) > 20:
        guidance["key_areas"].append(
            "Many methods - focus on public interfaces and high-complexity methods"
        )

    if len(structural_overview["imports"]) > 10:
        guidance["key_areas"].append("Many imports - consider dependency analysis")

    # Map each language to its most useful tree-sitter query keys
    lang_queries = {
        "java": ["methods", "classes", "imports", "spring_service", "jpa_entity"],
        "python": [
            "functions",
            "classes",
            "imports",
            "decorator",
            "async_patterns",
        ],
        "javascript": [
            "functions",
            "classes",
            "imports",
            "export",
            "react_component",
        ],
        "typescript": [
            "functions",
            "interfaces",
            "type_aliases",
            "enums",
            "decorators",
        ],
        "go": ["function", "struct", "interface", "goroutine", "channel_send"],
        "rust": ["fn", "struct", "enum", "trait", "impl"],
        "c": ["function", "struct", "enum", "include", "typedef"],
        "cpp": ["class", "function", "namespace", "template", "include"],
        "kotlin": [
            "function",
            "class",
            # Extract element details with line ranges
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
    if language in lang_queries:
        guidance["suggested_queries"] = lang_queries[language]
    # Count elements by type from analysis to build summary

    # Generate SMART workflow steps based on file size
    steps = ["check_code_scale (done)"]
    # Large files: targeted analysis strategy
    if guidance["size_category"] in ("large", "very_large"):
        steps.append("analyze_code_structure with format=compact for overview")
        steps.append("query_code with specific query keys to find target elements")
        # Suggest extracting the top complexity hotspot
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
    else:
        # Small/medium files: full analysis strategy
        steps.append("analyze_code_structure for full structure table")
        steps.append("query_code for specific elements if needed")
        # Flag high-complexity methods for review
        notable = structural_overview.get("methods", [])
        long_methods = [m for m in notable if m.get("complexity", 0) >= 8]
        if long_methods:
            top = long_methods[0]
            start = top.get("start_line", "")
            end = top.get("end_line", "")
            steps.append(
                f"extract_code_section for '{top.get('name', 'method')}' "
                f"(L{start}-{end}) - high complexity"
            )
    guidance["workflow_steps"] = steps

    # Add dependency/health suggestions for deeper analysis
    # Files with many imports may have wide blast radius
    if len(structural_overview.get("imports", [])) > 5:
        steps.append("analyze_dependencies mode=blast_radius to assess change impact")
    steps.append("check_file_health to see if this file needs refactoring")

    # Include available tree-sitter queries for this language (capped at 15 to save tokens)
    from ...query_loader import get_query_loader

    # Query loader provides language-specific tree-sitter queries
    loader = get_query_loader()
    all_queries = loader.list_queries_for_language(language)
    if all_queries:
        priority = [
            q
            for q in all_queries
            if q
            in (
                "classes",
                "methods",
                "functions",
                "imports",
                "variables",
                "interface",
                "trait",
                "namespace",
                "decorator",
            )
        ]
        rest = sorted(q for q in all_queries if q not in priority)[: 15 - len(priority)]
        # Prioritize common queries, fill remaining slots with language-specific ones
        guidance["available_queries"] = sorted(priority) + rest

    return guidance


# validate_scale_arguments: implementation
# Input validation for batch and single-file analysis modes
def validate_scale_arguments(arguments: dict[str, Any]) -> bool:
    """Validate file_path and option arguments for analyze scale tool."""
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
    summary_line = (
        f"{file_path} json {total_lines} lines  "
        "classes=0 methods=0 fields=0 (data file)"
    )
    result: dict[str, Any] = {
        "success": True,
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
    summary_line = (
        f"{file_path} {language} {total_lines if total_lines is not None else 0} lines  "
        f"classes={class_count} methods={method_count} fields={field_count}"
    )
    # Suggest the next step — mirrors the workflow hint in
    # ``generate_llm_guidance`` but kept self-contained so it survives
    # ``include_guidance=False``.
    if total_lines and total_lines >= 500:
        next_step = "analyze_code_structure format=compact then extract_code_section for hotspots"
    else:
        next_step = "analyze_code_structure for full structure table"
    agent_summary: dict[str, Any] = {
        "summary_line": summary_line,
        "next_step": next_step,
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
