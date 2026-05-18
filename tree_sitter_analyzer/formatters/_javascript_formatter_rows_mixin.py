"""Row and signature helpers for the JavaScript formatter."""

from typing import Any


class JavaScriptTableFormatterRowsMixin:
    """Function, method, and metadata row helpers."""

    def _format_function_row(self, func: dict[str, Any]) -> str:
        """Format a function table row for JavaScript"""
        name = str(func.get("name", ""))
        params = self._create_full_params(func)
        func_type = self._get_function_type(func)
        line_range = func.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = func.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(func.get("jsdoc", "")))
        )

        return (
            f"| {name} | {params} | {func_type} | {lines_str} | {complexity} | {doc} |"
        )

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for JavaScript"""
        name = str(method.get("name", ""))
        class_name = self._get_method_class(method)
        params = self._create_full_params(method)
        method_type = self._get_method_type(method)
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(method.get("jsdoc", "")))
        )

        return (
            f"| {name} | {class_name} | {params} | {method_type} | {lines_str} | "
            f"{complexity} | {doc} |"
        )

    def _create_full_params(self, func: dict[str, Any]) -> str:
        """Create full parameter list for JavaScript functions"""
        params = func.get("parameters", [])
        if not params or isinstance(params, str):
            return "()"

        params_str = ", ".join(_full_param_text(param) for param in params)
        if len(params_str) > 50:
            params_str = params_str[:47] + "..."

        return f"({params_str})"

    def _create_compact_params(self, func: dict[str, Any]) -> str:
        """Create compact parameter list for JavaScript functions"""
        params = func.get("parameters", [])
        if not params or isinstance(params, str):
            return "()"

        param_count = len(params)
        if param_count > 3:
            return f"({param_count} params)"

        param_names = [_compact_param_name(param) for param in params]
        return f"({','.join(param_names)})"

    def _get_function_signature(self, func: dict[str, Any]) -> str:
        """Get function signature"""
        name = str(func.get("name", ""))
        params = self._create_full_params(func)
        return_type = func.get("return_type", "")
        if return_type:
            return f"{name}{params} -> {return_type}"
        return f"{name}{params}"

    def _get_class_info(self, cls: dict[str, Any]) -> str:
        """Get class information as formatted string"""
        if cls is None:
            raise TypeError("Cannot format None data")

        if not isinstance(cls, dict):
            raise TypeError(f"Expected dict, got {type(cls)}")

        name = str(cls.get("name", "Unknown"))
        methods = cls.get("methods", [])
        method_count = len(methods) if isinstance(methods, list) else 0

        return f"{name} ({method_count} methods)"


def _full_param_text(param: Any) -> str:
    if not isinstance(param, dict):
        return str(param)

    param_name = param.get("name", "")
    param_type = param.get("type", "")
    if param_type:
        return f"{param_name}: {param_type}"
    return str(param_name)


def _compact_param_name(param: Any) -> str:
    if isinstance(param, dict):
        return param.get("name", str(param))
    return str(param)
