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


def extract_structural_overview(analysis_result: Any) -> dict[str, Any]:
    """Extract structural overview with position information for LLM guidance."""
    overview: dict[str, Any] = {
        "classes": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "complexity_hotspots": [],
    }

    # Extract class information with position from unified analysis engine
    classes = [
        e for e in analysis_result.elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)
    ]
    for cls in classes:
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

    # Extract method information with position and complexity from unified analysis engine
    methods = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
    ]
    for method in methods:
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
    # Extract field information from unified analysis engine
    fields = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
    ]
    for field in fields:
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
    # Extract import information from unified analysis engine
    imports = [
        e
        for e in analysis_result.elements
        if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
    ]
    for imp in imports:
        import_info = {
            "name": imp.imported_name,
            "statement": imp.import_statement,
            "line": imp.line_number,
            "is_static": imp.is_static,
            "is_wildcard": imp.is_wildcard,
        }
        overview["imports"].append(import_info)

    return overview


def extract_structural_overview_universal(
    analysis_result: Any,
) -> dict[str, Any]:
    """Extract structural overview from universal analysis result (non-Java languages)."""
    overview: dict[str, Any] = {
        "classes": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "complexity_hotspots": [],
    }

    if not analysis_result or not hasattr(analysis_result, "elements"):
        return overview

    for e in analysis_result.elements:
        etype = getattr(e, "element_type", "")
        name = getattr(e, "name", "unnamed")
        start_line = getattr(e, "start_line", 0)
        end_line = getattr(e, "end_line", 0)

        if etype == "class":
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
            method_info = {
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
                "line_span": end_line - start_line + 1,
                "complexity": getattr(e, "complexity_score", 0),
            }
            overview["methods"].append(method_info)
            complexity = getattr(e, "complexity_score", 0)
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
            overview["fields"].append(
                {
                    "name": name,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )
        elif etype == "import":
            overview["imports"].append(
                {
                    "name": name,
                    "line": start_line,
                }
            )

    return overview


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
        guidance["recommended_tools"].append("extract_code_section")
        guidance["recommended_tools"].append("query_code")

    # Ensure all required fields exist
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

    if len(structural_overview["methods"]) > 20:
        guidance["key_areas"].append(
            "Many methods - focus on public interfaces and high-complexity methods"
        )

    if len(structural_overview["imports"]) > 10:
        guidance["key_areas"].append("Many imports - consider dependency analysis")

    # Suggest language-specific queries
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

    # Generate SMART workflow steps
    steps = ["check_code_scale (done)"]
    if guidance["size_category"] in ("large", "very_large"):
        steps.append("analyze_code_structure with format=compact for overview")
        steps.append("query_code with specific query keys to find target elements")
        # Add specific hotspot extraction hints
        hotspots = structural_overview.get("complexity_hotspots", [])
        if hotspots:
            top = hotspots[0]
            name = top.get("name", "hotspot")
            lines = top.get("lines", "")
            steps.append(
                f"extract_code_section for '{name}' (lines {lines}) - complexity hotspot"
            )
        else:
            steps.append("extract_code_section for targeted line ranges")
    else:
        steps.append("analyze_code_structure for full structure table")
        steps.append("query_code for specific elements if needed")
        # Suggest extraction for notable methods even in small files
        notable = structural_overview.get("methods", [])
        long_methods = [m for m in notable if m.get("complexity", 0) >= 8]
        if long_methods:
            top = long_methods[0]
            steps.append(
                f"extract_code_section for '{top.get('name', 'method')}' "
                f"(lines {top.get('lines', '')}) - high complexity"
            )
    guidance["workflow_steps"] = steps

    # Add dependency/health suggestions for deeper analysis
    if len(structural_overview.get("imports", [])) > 5:
        steps.append("analyze_dependencies mode=blast_radius to assess change impact")
    steps.append("check_file_health to see if this file needs refactoring")

    # Include available queries for this language (capped at 15 to save tokens)
    from ...query_loader import get_query_loader

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
        guidance["available_queries"] = priority + rest

    return guidance


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
    return {
        "success": True,
        "file_path": file_path,
        "language": language,
        "file_metrics": file_metrics,
        "summary": {
            "classes": count_elements_fn(elements, ELEMENT_TYPE_CLASS, "class"),
            "methods": count_elements_fn(elements, ELEMENT_TYPE_FUNCTION, "function"),
            "fields": count_elements_fn(elements, ELEMENT_TYPE_VARIABLE, "variable"),
            "imports": count_elements_fn(elements, ELEMENT_TYPE_IMPORT, "import"),
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
    }


def build_detailed_analysis(analysis_result: Any, file_path: str) -> dict[str, Any]:
    """Build the detailed_analysis dict for include_details=True."""
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
