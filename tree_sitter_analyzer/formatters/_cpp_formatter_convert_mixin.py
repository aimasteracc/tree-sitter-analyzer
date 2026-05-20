"""Conversion helpers for C/C++ table formatter input."""

from typing import Any

from ..constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
)
from ..models import Package

COMMON_NON_NAMESPACE_NAMES = {
    "int",
    "double",
    "float",
    "char",
    "bool",
    "void",
}


def _valid_namespace_name(element: Package) -> str | None:
    element_name = getattr(element, "name", None)
    raw_text = getattr(element, "raw_text", "")
    if not element_name:
        return None

    is_likely_namespace = not raw_text or "namespace" in raw_text.lower()
    if not is_likely_namespace:
        return None

    namespace_name = str(element_name).strip()
    if len(namespace_name) == 1:
        return None
    if namespace_name.lower() in COMMON_NON_NAMESPACE_NAMES:
        return None
    if namespace_name and namespace_name.isidentifier() and len(namespace_name) >= 2:
        return namespace_name
    return None


def _namespace_entry(namespace_name: str, element: Package) -> dict[str, Any]:
    return {
        "name": namespace_name,
        "line_range": {
            "start": getattr(element, "start_line", 0),
            "end": getattr(element, "end_line", 0),
        },
    }


def _append_converted_cpp_element(
    formatter: Any,
    element: Any,
    index: int,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> None:
    element_type = get_element_type(element)
    if element_type == ELEMENT_TYPE_CLASS:
        classes.append(formatter._convert_class_element(element, index))
    elif element_type == ELEMENT_TYPE_FUNCTION:
        methods.append(formatter._convert_function_element(element))
    elif element_type == ELEMENT_TYPE_VARIABLE:
        fields.append(formatter._convert_variable_element(element))
    elif element_type == ELEMENT_TYPE_IMPORT:
        imports.append(formatter._convert_import_element(element))


def _parse_cpp_parameter(param: Any) -> dict[str, Any]:
    if isinstance(param, str):
        return _parse_cpp_parameter_string(param)
    if isinstance(param, dict):
        return param
    return {"name": str(param), "type": "Any"}


def _parse_cpp_parameter_string(param: str) -> dict[str, str]:
    cleaned_param = param.strip()
    last_space_idx = cleaned_param.rfind(" ")
    if last_space_idx == -1:
        return {"name": "param", "type": cleaned_param}

    param_type = cleaned_param[:last_space_idx].strip()
    param_name = cleaned_param[last_space_idx + 1 :].strip()
    if "[]" in param_name:
        param_type += "[]"
        param_name = param_name.replace("[]", "")

    if param_type and param_name:
        return {"name": param_name, "type": param_type}
    return {"name": "param", "type": cleaned_param}


def _build_cpp_format_result(
    analysis_result: Any,
    package_name: str,
    packages: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "file_path": analysis_result.file_path,
        "language": analysis_result.language,
        "line_count": analysis_result.line_count,
        "package": {"name": package_name},
        "packages": packages,
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


class CppTableFormatterConvertMixin:
    """Convert analyzer models into the dict shape used by C/C++ formatters."""

    def _convert_analysis_result_to_format(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        classes: list[dict[str, Any]] = []
        methods: list[dict[str, Any]] = []
        fields: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        packages: list[dict[str, Any]] = []
        package_name = "unknown"

        for index, element in enumerate(analysis_result.elements):
            try:
                if isinstance(element, Package):
                    namespace_name = _valid_namespace_name(element)
                    if namespace_name:
                        package_name = namespace_name
                        packages.append(_namespace_entry(namespace_name, element))
                    continue

                _append_converted_cpp_element(
                    self,
                    element,
                    index,
                    classes,
                    methods,
                    fields,
                    imports,
                )
            except Exception:  # nosec
                continue

        return _build_cpp_format_result(
            analysis_result,
            package_name,
            packages,
            classes,
            methods,
            fields,
            imports,
        )

    def _convert_class_element(self, element: Any, index: int) -> dict[str, Any]:
        """Convert class element to table format."""
        element_name = getattr(element, "name", None)
        final_name = element_name if element_name else f"UnknownClass_{index}"
        class_type = getattr(element, "class_type", "class")
        visibility = getattr(element, "visibility", "public")

        return {
            "name": final_name,
            "type": class_type,
            "visibility": visibility,
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
        }

    def _convert_function_element(self, element: Any) -> dict[str, Any]:
        """Convert function element to table format."""
        processed_params = [
            _parse_cpp_parameter(param) for param in getattr(element, "parameters", [])
        ]
        visibility = getattr(element, "visibility", "public")

        return {
            "name": getattr(element, "name", str(element)),
            "visibility": visibility,
            "return_type": getattr(element, "return_type", "Any"),
            "parameters": processed_params,
            "is_constructor": getattr(element, "is_constructor", False),
            "is_static": getattr(element, "is_static", False),
            "complexity_score": getattr(element, "complexity_score", 1),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": "",
        }

    def _convert_variable_element(self, element: Any) -> dict[str, Any]:
        """Convert variable element to table format."""
        field_type = getattr(element, "variable_type", "")
        visibility = getattr(element, "visibility", "public")

        return {
            "name": getattr(element, "name", str(element)),
            "type": field_type,
            "visibility": visibility,
            "modifiers": getattr(element, "modifiers", []),
            "line_range": {
                "start": getattr(element, "start_line", 0),
                "end": getattr(element, "end_line", 0),
            },
            "javadoc": "",
        }

    def _convert_import_element(self, element: Any) -> dict[str, Any]:
        """Convert import element to table format."""
        raw_text = getattr(element, "raw_text", "")
        statement = (
            raw_text
            if raw_text
            else f"#include {getattr(element, 'name', str(element))}"
        )

        return {
            "statement": statement,
            "raw_text": statement,
            "name": getattr(element, "name", str(element)),
            "module_name": getattr(element, "module_name", ""),
        }
