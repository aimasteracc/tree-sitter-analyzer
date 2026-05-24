"""Type and metadata inference helpers for the JavaScript formatter."""

from typing import Any

from ._javascript_formatter_type_helpers import (
    export_type,
    infer_js_type,
    is_method,
    method_class,
    method_function_type,
    method_type,
    variable_kind,
)


class JavaScriptTableFormatterTypeMixin:
    """Classification helpers for JavaScript analysis rows."""

    _get_export_type = staticmethod(export_type)
    _get_method_class = staticmethod(method_class)
    _get_method_type = staticmethod(method_type)
    _get_variable_kind = staticmethod(variable_kind)
    _infer_js_type = staticmethod(infer_js_type)
    _is_method = staticmethod(is_method)

    def _get_function_type(self, func: dict[str, Any]) -> str:
        """Get full function type for JavaScript"""
        if func.get("is_async", False):
            return "async function"
        if func.get("is_generator", False):
            return "generator"
        if func.get("is_arrow", False):
            return "arrow"
        if not self._is_method(func):
            return "function"

        return method_function_type(func)

    def _get_function_type_short(self, func: dict[str, Any]) -> str:
        """Get short function type for JavaScript"""
        if func.get("is_async", False):
            return "async"
        if func.get("is_generator", False):
            return "gen"
        if func.get("is_arrow", False):
            return "arrow"
        if self._is_method(func):
            return "method"
        return "func"

    def _determine_scope(self, var: dict[str, Any]) -> str:
        """Determine variable scope"""
        kind = self._get_variable_kind(var)
        if kind in {"const", "let"}:
            return "block"
        if kind == "var":
            return "function"
        return "unknown"
