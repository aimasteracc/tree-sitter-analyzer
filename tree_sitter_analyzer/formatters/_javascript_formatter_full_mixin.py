"""Full table rendering for the JavaScript formatter."""

from typing import Any


class JavaScriptTableFormatterFullMixin:
    """Full-format rendering helpers."""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for JavaScript - matches golden master format"""
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        lines: list[str] = []
        classes = _list_or_empty(data.get("classes", []))
        methods = _list_or_empty(data.get("methods", []))

        lines.append(f"# {_title(data, classes)}")
        lines.append("")

        if classes:
            _append_classes_overview(lines, classes, methods)
            for class_info in classes:
                lines.extend(self._format_class_section(class_info, data))

        _trim_trailing_blank_lines(lines)
        return "\n".join(lines)

    def _format_class_section(
        self, class_info: dict[str, Any], data: dict[str, Any]
    ) -> list[str]:
        """Format a single class section with its methods"""
        lines: list[str] = []
        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)
        methods = _list_or_empty(data.get("methods", []))
        class_methods = _items_in_range(methods, start, end)

        lines.append(f"## {name} ({start}-{end})")
        _append_method_section(
            lines,
            "### Constructors",
            "| Constructor | Signature | Vis | Lines | Cx | Doc |",
            "|-------------|-----------|-----|-------|----|----|",
            [method for method in class_methods if method.get("is_constructor", False)],
            self._format_method_table_row,
        )
        _append_method_section(
            lines,
            "### Public Methods",
            "| Method | Signature | Vis | Lines | Cx | Doc |",
            "|--------|-----------|-----|-------|----|----|",
            [
                method
                for method in class_methods
                if not method.get("is_constructor", False)
            ],
            self._format_method_table_row,
        )
        return lines

    def _format_method_table_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for JavaScript (golden master format)"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 1)
        return f"| {name} | {signature} | + | {lines_str} | {complexity} | - |"

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create full method signature for JavaScript"""
        params = method.get("parameters", [])
        if not params or isinstance(params, str):
            return "():unknown"

        param_strs = []
        for param in params:
            if isinstance(param, dict):
                param_name = param.get("name", "")
                param_type = param.get("type", "Any")
                param_strs.append(f"{param_name}:{param_type}")
            else:
                param_strs.append(f"{param}:Any")

        params_str = ", ".join(param_strs)
        return_type = method.get("return_type", "unknown")
        return f"({params_str}):{return_type}"


def _list_or_empty(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _title(data: dict[str, Any], classes: list[dict[str, Any]]) -> str:
    if classes:
        return str(classes[0].get("name", "Unknown"))

    file_path = data.get("file_path", "Unknown")
    if file_path is None:
        file_path = "Unknown"
    file_name = str(file_path).split("/")[-1].split("\\")[-1]
    return file_name.replace(".js", "").replace(".jsx", "").replace(".mjs", "")


def _append_classes_overview(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
) -> None:
    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")

    for class_info in classes:
        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        class_methods = _items_in_range(
            methods, line_range.get("start", 0), line_range.get("end", 0)
        )
        lines.append(
            f"| {name} | class | public | {lines_str} | {len(class_methods)} | 0 |"
        )
    lines.append("")


def _items_in_range(
    items: list[dict[str, Any]], start: int, end: int
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if start <= item.get("line_range", {}).get("start", 0) <= end
    ]


def _append_method_section(
    lines: list[str],
    title: str,
    header: str,
    separator: str,
    methods: list[dict[str, Any]],
    row_formatter: Any,
) -> None:
    if not methods:
        return

    lines.append(title)
    lines.append(header)
    lines.append(separator)
    for method in methods:
        lines.append(row_formatter(method))
    lines.append("")


def _trim_trailing_blank_lines(lines: list[str]) -> None:
    while lines and lines[-1] == "":
        lines.pop()
