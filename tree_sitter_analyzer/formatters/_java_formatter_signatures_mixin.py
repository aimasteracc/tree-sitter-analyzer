"""Signatures (lightweight directory) table rendering for the Java formatter.

``signatures`` mode is the first step of the "directory → pick → batch-read"
large-file strategy.  It lists every method in ``name →returnType(Np)
startLine-endLine`` form (N = parameter count, *not* full types) grouped by
class.  The resulting output is ~25% of full-mode token cost, letting an agent
scan all 200-300 method names before choosing which bodies to fetch via
``--partial-read`` or batch-read.

Token budget (IndexShard.java 5142 lines / 288 methods, prototype):
    full ≈ 11 800 tok  |  compact ≈ 5 600 tok  |  signatures ≈ 3 000 tok
"""

from __future__ import annotations

from typing import Any

from ._java_formatter_class_mixin import (
    get_class_fields,
    get_class_methods,
    is_inner_class,
)
from ._java_formatter_full_mixin import _java_title, _trim_trailing_blank_lines


class JavaTableFormatterSignaturesMixin:
    """Signatures-format rendering: name →returnType(Np) L-L per method."""

    def _format_signatures_table(self, data: dict[str, Any]) -> str:
        """Render a lightweight method-directory for the given structure data.

        Output shape (per class block):
            ## ClassName (startLine-endLine)  [N methods, M fields]
            methodName →returnType(Np) startLine-endLine
            ...
            [fields omitted when empty]
            fieldName:type  (one line per field, only if ≤ 20 fields total)
        """
        lines: list[str] = []
        package_name = (data.get("package") or {}).get("name", "")
        classes = data.get("classes", []) or []
        all_methods = data.get("methods", []) or []
        all_fields = data.get("fields", []) or []
        stats = data.get("statistics") or {}

        # Header — lightweight, same style as compact
        title = _java_title(self, data, package_name, classes)
        lines.append(f"# {title} [signatures]")
        lines.append("")

        if package_name:
            lines.append(f"pkg: {package_name}")

        total_methods = stats.get("method_count", len(all_methods))
        total_fields = stats.get("field_count", len(all_fields))
        lines.append(f"methods: {total_methods}  fields: {total_fields}")
        lines.append("")

        if not classes:
            # Flat file (no class grouping) — just emit methods
            _append_method_lines(lines, all_methods)
        else:
            top_level = [c for c in classes if not is_inner_class(c, classes)]
            # If only one top-level class and it happens to be "all", flatten
            for cls in top_level:
                _append_class_block(lines, cls, data, classes, all_methods, all_fields)

        # Next-step hint for agents
        lines.append("")
        lines.append(
            "next_step: Pick methods by name, then use "
            "--partial-read <start>-<end> or batch-read to get bodies."
        )

        _trim_trailing_blank_lines(lines)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level helpers (no access to formatter instance needed)
# ---------------------------------------------------------------------------


def _append_class_block(
    lines: list[str],
    cls: dict[str, Any],
    data: dict[str, Any],
    all_classes: list[dict[str, Any]],
    all_methods: list[dict[str, Any]],
    all_fields: list[dict[str, Any]],
) -> None:
    """Emit one class block: header + method lines + optional field lines."""
    name = cls.get("name", "?")
    lr = cls.get("line_range", {})
    start = lr.get("start", 0)
    end = lr.get("end", 0)
    class_methods = get_class_methods(all_methods, lr)
    class_fields = get_class_fields(all_fields, lr)
    n_methods = len(class_methods)
    n_fields = len(class_fields)

    lines.append(f"## {name} ({start}-{end}) [{n_methods} methods, {n_fields} fields]")
    _append_method_lines(lines, class_methods)

    # Fields: only emit when few enough to be cheap (≤ 30 per class)
    if class_fields and n_fields <= 30:
        lines.append("")
        lines.append("  fields:")
        for field in class_fields:
            fname = field.get("name", "?")
            ftype = field.get("type", "")
            flr = field.get("line_range", {})
            fl = flr.get("start", 0)
            if ftype:
                lines.append(f"    {fname}:{ftype} L{fl}")
            else:
                lines.append(f"    {fname} L{fl}")

    lines.append("")


def _append_method_lines(
    lines: list[str],
    methods: list[dict[str, Any]],
) -> None:
    """Emit one line per method: ``name →returnType(Np) start-end``."""
    for method in methods:
        lines.append(_method_sig_line(method))


def _method_sig_line(method: dict[str, Any]) -> str:
    """Format ``methodName →returnType(Np) startLine-endLine``."""
    name = method.get("name", "?")
    return_type = method.get("return_type", "") or "void"
    params = method.get("parameters", []) or []
    n_params = len(params)
    lr = method.get("line_range", {})
    start = lr.get("start", 0)
    end = lr.get("end", 0)
    # Shorten common return types to save tokens
    short_ret = _shorten_return_type(return_type)
    return f"  {name} →{short_ret}({n_params}p) {start}-{end}"


_RETURN_ABBREVS: dict[str, str] = {
    "void": "void",
    "boolean": "bool",
    "Boolean": "bool",
    "int": "int",
    "Integer": "int",
    "long": "long",
    "Long": "long",
    "double": "double",
    "Double": "double",
    "float": "float",
    "Float": "float",
    "String": "String",
    "Object": "Object",
}


def _shorten_return_type(ret: str) -> str:
    """Abbreviate common return types; leave complex generics intact."""
    if not ret:
        return "void"
    # Strip leading qualifiers (e.g. "java.util.List" → "List")
    simple = ret.rsplit(".", 1)[-1]
    return _RETURN_ABBREVS.get(simple, simple)
