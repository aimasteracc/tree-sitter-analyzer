"""Conversion helpers for the Python formatter."""

from typing import Any

from ..constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
)


def convert_analysis_result_to_python_format(
    formatter: Any, analysis_result: Any
) -> dict[str, Any]:
    """Convert AnalysisResult to Python formatter's expected format"""
    conversion = _new_conversion()
    for element in analysis_result.elements:
        _append_converted_element(conversion, formatter, element)
    return _conversion_result(analysis_result, conversion)


def _new_conversion() -> dict[str, Any]:
    return {
        "classes": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "package_name": "unknown",
    }


def _append_converted_element(
    conversion: dict[str, Any], formatter: Any, element: Any
) -> None:
    element_type = get_element_type(element)
    if element_type == ELEMENT_TYPE_PACKAGE:
        conversion["package_name"] = str(getattr(element, "name", None))
    elif element_type == ELEMENT_TYPE_CLASS:
        conversion["classes"].append(
            formatter._convert_class_element_for_python(element)
        )
    elif element_type == ELEMENT_TYPE_FUNCTION:
        conversion["methods"].append(
            formatter._convert_function_element_for_python(element)
        )
    elif element_type == ELEMENT_TYPE_VARIABLE:
        conversion["fields"].append(
            formatter._convert_variable_element_for_python(element)
        )
    elif element_type == ELEMENT_TYPE_IMPORT:
        conversion["imports"].append(
            formatter._convert_import_element_for_python(element)
        )


def _conversion_result(
    analysis_result: Any, conversion: dict[str, Any]
) -> dict[str, Any]:
    classes = conversion["classes"]
    methods = conversion["methods"]
    fields = conversion["fields"]
    imports = conversion["imports"]
    return {
        "file_path": analysis_result.file_path,
        "language": analysis_result.language,
        "line_count": analysis_result.line_count,
        "package": {"name": conversion["package_name"]},
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


def convert_class_element_for_python(element: Any) -> dict[str, Any]:
    """Convert class element for Python formatter"""
    element_name = getattr(element, "name", None)
    final_name = element_name if element_name else "UnknownClass"

    return {
        "name": final_name,
        "type": getattr(element, "class_type", "class"),
        "visibility": getattr(element, "visibility", "public"),
        "line_range": _element_line_range(element),
    }


def convert_function_element_for_python(formatter: Any, element: Any) -> dict[str, Any]:
    """Convert function element for Python formatter"""
    params = getattr(element, "parameters", [])
    processed_params = formatter._process_python_parameters(params)

    return {
        "name": getattr(element, "name", str(element)),
        "visibility": getattr(element, "visibility", "public"),
        "return_type": getattr(element, "return_type", "Any"),
        "parameters": processed_params,
        "is_constructor": getattr(element, "is_constructor", False),
        "is_static": getattr(element, "is_static", False),
        "is_async": getattr(element, "is_async", False),
        "complexity_score": getattr(element, "complexity_score", 1),
        "line_range": _element_line_range(element),
        "docstring": getattr(element, "docstring", "") or "",
        "decorators": getattr(element, "decorators", []),
        "modifiers": getattr(element, "modifiers", []),
    }


def convert_variable_element_for_python(element: Any) -> dict[str, Any]:
    """Convert variable element for Python formatter"""
    return {
        "name": getattr(element, "name", str(element)),
        "type": getattr(element, "variable_type", "")
        or getattr(element, "field_type", ""),
        "visibility": getattr(element, "visibility", "public"),
        "modifiers": getattr(element, "modifiers", []),
        "line_range": _element_line_range(element),
        "javadoc": getattr(element, "docstring", ""),
    }


def convert_import_element_for_python(element: Any) -> dict[str, Any]:
    """Convert import element for Python formatter"""
    raw_text = getattr(element, "raw_text", "")
    if raw_text:
        statement = raw_text
    else:
        statement = f"import {getattr(element, 'name', str(element))}"

    return {
        "statement": statement,
        "raw_text": statement,
        "name": getattr(element, "name", str(element)),
        "module_name": getattr(element, "module_name", ""),
    }


def _element_line_range(element: Any) -> dict[str, int]:
    return {
        "start": getattr(element, "start_line", 0),
        "end": getattr(element, "end_line", 0),
    }


def process_python_parameters(params: Any) -> list[dict[str, str]]:
    """Process parameters for Python formatter"""
    if isinstance(params, str):
        return _process_parameter_string(params)
    if isinstance(params, list):
        return [_process_parameter_item(param) for param in params]
    return []


def _process_parameter_string(params: str) -> list[dict[str, str]]:
    if not params.strip():
        return []

    param_names = [param.strip() for param in params.split(",") if param.strip()]
    return [{"name": name, "type": "Any"} for name in param_names]


def _process_parameter_item(param: Any) -> dict[str, str]:
    if isinstance(param, str):
        return _process_parameter_text(param)
    if isinstance(param, dict):
        return param
    return {"name": str(param), "type": "Any"}


def _process_parameter_text(param: str) -> dict[str, str]:
    param = param.strip()
    if ":" not in param:
        return {"name": param, "type": "Any"}

    parts = param.split(":", 1)
    param_name = parts[0].strip()
    param_type = parts[1].strip() if len(parts) > 1 else "Any"
    return {"name": param_name, "type": param_type}
