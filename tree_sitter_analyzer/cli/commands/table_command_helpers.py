"""Helpers for table command data conversion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_SQL_FUNCTION,
    ELEMENT_TYPE_SQL_INDEX,
    ELEMENT_TYPE_SQL_PROCEDURE,
    ELEMENT_TYPE_SQL_TABLE,
    ELEMENT_TYPE_SQL_TRIGGER,
    ELEMENT_TYPE_SQL_VIEW,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
)

TYPE_SUFFIX_LANGUAGES = {
    "python",
    "rust",
    "kotlin",
    "swift",
    "typescript",
    "ts",
    "scala",
}

PACKAGED_LANGUAGES = {"java", "kotlin", "scala", "csharp", "cpp", "c++"}
STRUCTURE_SQL_ELEMENT_TYPES = {
    ELEMENT_TYPE_SQL_TABLE,
    ELEMENT_TYPE_SQL_VIEW,
    ELEMENT_TYPE_SQL_PROCEDURE,
    ELEMENT_TYPE_SQL_FUNCTION,
    ELEMENT_TYPE_SQL_TRIGGER,
    ELEMENT_TYPE_SQL_INDEX,
}


@dataclass(frozen=True)
class StructureConverters:
    """Callable adapters used to preserve TableCommand conversion behavior."""

    class_element: Callable[[Any, int, str], dict[str, Any]]
    function_element: Callable[[Any, str], dict[str, Any]]
    variable_element: Callable[[Any, str], dict[str, Any]]
    import_element: Callable[[Any], dict[str, Any]]
    sql_element: Callable[[Any, str], dict[str, Any]]


def convert_to_toon_format(analysis_result: Any) -> dict[str, Any]:
    """Convert AnalysisResult to TOON-friendly format with position info."""
    classes: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    for element in analysis_result.elements:
        _append_toon_element(element, classes, methods, fields, imports)

    return {
        "file_path": analysis_result.file_path,
        "language": analysis_result.language,
        "package": _toon_package_info(analysis_result.elements),
        "classes": classes,
        "methods": methods,
        "fields": fields,
        "imports": imports,
        "statistics": {
            "class_count": len(classes),
            "method_count": len(methods),
            "field_count": len(fields),
            "import_count": len(imports),
            "total_lines": analysis_result.line_count,
        },
    }


def get_default_package_name(language: str) -> str:
    """Return the default package name for language-specific table output."""
    return "unknown" if language.lower() in PACKAGED_LANGUAGES else ""


def resolve_structure_package_name(analysis_result: Any, language: str) -> str:
    """Resolve the package name for table formatter structure output."""
    package_obj = getattr(analysis_result, "package", None)
    if package_obj and hasattr(package_obj, "name"):
        return str(package_obj.name)
    return get_default_package_name(language)


def collect_structure_elements(
    analysis_result: Any,
    language: str,
    package_name: str,
    converters: StructureConverters,
    report_error: Callable[[str], None],
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Collect classes, methods, fields, and imports for table structure output."""
    classes: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    for index, element in enumerate(analysis_result.elements):
        try:
            package_name = _append_structure_element(
                element,
                index,
                language,
                package_name,
                converters,
                classes,
                methods,
                fields,
                imports,
            )
        except Exception as element_error:
            report_error(f"ERROR: Element {index} processing failed: {element_error}")

    return package_name, classes, methods, fields, imports


def build_structure_format(
    analysis_result: Any,
    package_name: str,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the final table formatter structure payload."""
    return {
        "file_path": analysis_result.file_path,
        "language": analysis_result.language,
        "line_count": analysis_result.line_count,
        "package": {"name": package_name},
        "classes": classes,
        "methods": methods,
        "fields": fields,
        "imports": imports,
        "statistics": {
            "method_count": len(methods),
            "field_count": len(fields),
            "class_count": len(classes),
            "import_count": len(imports),
        },
    }


def process_parameters(params: Any, language: str) -> list[dict[str, str]]:
    """Process parameters based on language syntax."""
    if isinstance(params, str):
        return _process_string_parameters(params)
    if isinstance(params, list):
        return [_process_single_parameter(param, language) for param in params]
    return []


def _append_toon_element(
    element: Any,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> None:
    """Append one element to the matching TOON collection."""
    element_type = get_element_type(element)
    if element_type == ELEMENT_TYPE_CLASS:
        classes.append(_toon_class(element))
    elif element_type == ELEMENT_TYPE_FUNCTION:
        methods.append(_toon_method(element))
    elif element_type == ELEMENT_TYPE_VARIABLE:
        fields.append(_toon_field(element))
    elif element_type == ELEMENT_TYPE_IMPORT:
        imports.append(_toon_import(element))


def _append_structure_element(
    element: Any,
    index: int,
    language: str,
    package_name: str,
    converters: StructureConverters,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> str:
    """Append one parsed element to the matching table structure collection."""
    element_type = get_element_type(element)
    if element_type == ELEMENT_TYPE_PACKAGE:
        return str(getattr(element, "name", None))
    if element_type == ELEMENT_TYPE_CLASS:
        classes.append(converters.class_element(element, index, language))
    elif element_type == ELEMENT_TYPE_FUNCTION:
        methods.append(converters.function_element(element, language))
    elif element_type == ELEMENT_TYPE_VARIABLE:
        fields.append(converters.variable_element(element, language))
    elif element_type == ELEMENT_TYPE_IMPORT:
        imports.append(converters.import_element(element))
    elif element_type in STRUCTURE_SQL_ELEMENT_TYPES:
        methods.append(converters.sql_element(element, language))
    return package_name


def _toon_class(element: Any) -> dict[str, Any]:
    """Convert a class element to TOON shape."""
    return {
        "name": getattr(element, "name", "unknown"),
        "visibility": getattr(element, "visibility", "public"),
        "line_range": _line_range_tuple(element),
    }


def _toon_method(element: Any) -> dict[str, Any]:
    """Convert a function element to TOON shape."""
    return {
        "name": getattr(element, "name", "unknown"),
        "visibility": getattr(element, "visibility", "public"),
        "line_range": _line_range_tuple(element),
    }


def _toon_field(element: Any) -> dict[str, Any]:
    """Convert a variable element to TOON shape."""
    return {
        "name": getattr(element, "name", "unknown"),
        "type": getattr(element, "type_annotation", ""),
        "line_range": _line_range_tuple(element),
    }


def _toon_import(element: Any) -> dict[str, Any]:
    """Convert an import element to TOON shape.

    K2 canonical shape — matches ``TableCommand._convert_import_element``
    key-for-key so an agent switching ``--format json`` ↔ ``--format toon``
    sees the same schema.
    """
    raw_text_attr = getattr(element, "raw_text", "")
    import_statement_attr = getattr(element, "import_statement", "")
    if isinstance(raw_text_attr, str) and raw_text_attr:
        statement = raw_text_attr
    elif isinstance(import_statement_attr, str) and import_statement_attr:
        statement = import_statement_attr
    else:
        statement = f"import {getattr(element, 'name', 'unknown')}"
    return {
        "name": getattr(element, "name", "unknown"),
        "module_name": getattr(element, "module_name", "") or "",
        "statement": statement,
        "is_static": bool(getattr(element, "is_static", False)),
        "is_wildcard": bool(getattr(element, "is_wildcard", False)),
        "line_range": [
            int(getattr(element, "start_line", 0)),
            int(getattr(element, "end_line", 0)),
        ],
        "imported_names": list(getattr(element, "imported_names", []) or []),
        # Backward-compat alias retained for parity with JSON output.
        "raw_text": statement,
    }


def _toon_package_info(elements: list[Any]) -> dict[str, Any] | None:
    """Return the first package element in TOON shape."""
    packages = [e for e in elements if get_element_type(e) == ELEMENT_TYPE_PACKAGE]
    if not packages:
        return None
    package = packages[0]
    return {
        "name": getattr(package, "name", ""),
        "line_range": _line_range_tuple(package),
    }


def _line_range_tuple(element: Any) -> tuple[int, int]:
    """Return tuple line range used by TOON output."""
    return (
        getattr(element, "start_line", 0),
        getattr(element, "end_line", 0),
    )


def _process_string_parameters(params: str) -> list[dict[str, str]]:
    """Split comma-delimited parameter text into Any-typed names."""
    if not params.strip():
        return []
    param_names = [param.strip() for param in params.split(",") if param.strip()]
    return [{"name": name, "type": "Any"} for name in param_names]


def _process_single_parameter(param: Any, language: str) -> dict[str, str]:
    """Process one parameter item from parser output."""
    if isinstance(param, dict):
        return param
    if not isinstance(param, str):
        return {"name": str(param), "type": "Any"}

    stripped = param.strip()
    if language.lower() in TYPE_SUFFIX_LANGUAGES:
        return _process_type_suffix_parameter(stripped)
    return _process_type_prefix_parameter(stripped)


def _process_type_suffix_parameter(param: str) -> dict[str, str]:
    """Process name-first parameter syntax, such as Python or TypeScript."""
    if ":" not in param:
        return {"name": param, "type": "Any"}
    name, param_type = param.split(":", 1)
    return {"name": name.strip(), "type": param_type.strip() or "Any"}


def _process_type_prefix_parameter(param: str) -> dict[str, str]:
    """Process type-first parameter syntax, such as Java."""
    # Destructuring patterns must not be split; preserve whole as name (#745).
    if param.startswith("{") or param.startswith("["):
        return {"name": param, "type": ""}
    last_space_idx = param.rfind(" ")
    if last_space_idx == -1:
        return {"name": param, "type": "Any"}

    param_type = param[:last_space_idx].strip()
    param_name = param[last_space_idx + 1 :].strip()
    if not param_type or not param_name:
        return {"name": param, "type": "Any"}
    return {"name": param_name, "type": param_type}
