"""Signatures (lightweight method-directory) table rendering for the TypeScript formatter.

``signatures`` mode is the first step of the "directory → pick → batch-read"
large-file strategy.  It lists every method/function in ``name →returnType(Np)
startLine-endLine`` form (N = parameter count, *not* full types) grouped by
class/interface.  The resulting output is ~25% of full-mode token cost, letting
an agent scan all method names before choosing which bodies to fetch via
``action=read``.

Mirrors the shape of ``_python_formatter_signatures_table`` and
``_java_formatter_signatures_mixin`` but uses TypeScript naming conventions
(interface/class grouping; module-level functions in a ``<module functions>``
block; void default return rather than None).

Overload convention: each overload declaration appears as a separate line with
its own line range.  This matches what the TypeScript structure extractor
produces — each overload entry is a distinct method dict — and mirrors the
Java/Python convention of listing every callable entry once per occurrence.
There is no folding because folding would require comparing signatures which is
out-of-scope for a lightweight directory mode.
"""

from __future__ import annotations

from typing import Any


def format_typescript_signatures_table(data: dict[str, Any]) -> str:
    """Render a lightweight method-directory for the given TypeScript structure data.

    Output shape::

        # module_name [signatures]

        methods: N  classes: M

        ## ClassName (startLine-endLine)  [N methods]
          methodName →returnType(Np) startLine-endLine
          ...

        ## <module functions>  [N functions]
          funcName →returnType(Np) startLine-endLine
          ...

        next_step: Pick methods by name, then use action=read to get bodies.
    """
    lines: list[str] = []
    file_path = data.get("file_path", "")
    module_name = _module_name(file_path)
    classes = data.get("classes") or []
    all_methods = data.get("methods") or data.get("functions") or []
    stats = data.get("statistics") or {}

    # Header
    lines.append(f"# {module_name} [signatures]")
    lines.append("")

    total_methods = stats.get("method_count", len(all_methods))
    total_classes = stats.get("class_count", len(classes))
    lines.append(f"methods: {total_methods}  classes: {total_classes}")
    lines.append("")

    if classes:
        ownership = _assign_methods_to_classes(all_methods, classes)
        for idx, cls in enumerate(classes):
            _append_class_block(lines, cls, ownership.get(idx, []))
        # Module-level functions (not belonging to any class)
        module_funcs = _module_level_functions(all_methods, classes)
        if module_funcs:
            _append_module_functions_block(lines, module_funcs)
    else:
        # No classes — flat module with only top-level functions
        _append_module_functions_block(lines, all_methods)

    # Agent hint
    lines.append("")
    lines.append("next_step: Pick methods by name, then use action=read to get bodies.")

    _trim_trailing_blank_lines(lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_name(file_path: str) -> str:
    """Extract a short module name from a file path (strips .ts/.tsx/.d.ts)."""
    if not file_path:
        return "module"
    basename = str(file_path).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    for ext in (".d.ts", ".tsx", ".ts"):
        if basename.endswith(ext):
            basename = basename[: -len(ext)]
            break
    return basename or "module"


def _append_class_block(
    lines: list[str],
    cls: dict[str, Any],
    class_methods: list[dict[str, Any]],
) -> None:
    """Emit one class/interface block: header + method lines."""
    name = cls.get("name", "?")
    # Real analysis data stores the container kind under "type"
    # (_convert_class); "class_type" is the raw-element spelling.
    class_type = cls.get("class_type") or cls.get("type") or "class"
    lr = cls.get("line_range") or {}
    start = lr.get("start", 0)
    end = lr.get("end", 0)
    n_methods = len(class_methods)

    lines.append(f"## {name} ({start}-{end}) [{class_type}, {n_methods} methods]")
    _append_method_lines(lines, class_methods)
    lines.append("")


def _append_module_functions_block(
    lines: list[str],
    functions: list[dict[str, Any]],
) -> None:
    """Emit the module-level functions block."""
    n = len(functions)
    lines.append(f"## <module functions> [{n} functions]")
    _append_method_lines(lines, functions)
    lines.append("")


def _append_method_lines(
    lines: list[str],
    methods: list[dict[str, Any]],
) -> None:
    """Emit one line per method: ``name →returnType(Np) start-end``."""
    for method in methods:
        lines.append(_method_sig_line(method))


def _method_sig_line(method: dict[str, Any]) -> str:
    """Format ``  methodName →returnType(Np) startLine-endLine``."""
    name = method.get("name", "?")
    return_type = method.get("return_type", "") or "void"
    params = method.get("parameters") or []
    n_params = len(params)
    lr = method.get("line_range") or {}
    start = lr.get("start", 0)
    end = lr.get("end", 0)
    short_ret = _shorten_return_type(return_type)
    return f"  {name} →{short_ret}({n_params}p) {start}-{end}"


_RETURN_ABBREVS: dict[str, str] = {
    "void": "void",
    "string": "string",
    "number": "number",
    "boolean": "boolean",
    "any": "any",
    "never": "never",
    "unknown": "unknown",
    "undefined": "undefined",
    "null": "null",
    "object": "object",
    "symbol": "symbol",
    "bigint": "bigint",
}


def _shorten_return_type(ret: str) -> str:
    """Abbreviate common return types; strip generics to base name."""
    if not ret:
        return "void"
    # For generics like Promise<User[]> keep base type name only
    bracket = ret.find("<")
    simple = ret[:bracket] if bracket != -1 else ret
    simple = simple.strip()
    return _RETURN_ABBREVS.get(simple, simple)


def _assign_methods_to_classes(
    methods: list[dict[str, Any]],
    classes: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """Assign each method to exactly ONE class — the innermost containing one.

    A method inside a nested class falls inside both the outer and inner
    class line ranges; listing it under both overstates the outer API.
    The smallest containing span wins (single-ownership rule).
    """
    ownership: dict[int, list[dict[str, Any]]] = {}
    for m in methods:
        m_start = (m.get("line_range") or {}).get("start", 0)
        best_idx: int | None = None
        best_span: int | None = None
        for idx, cls in enumerate(classes):
            lr = cls.get("line_range") or {}
            c_start = lr.get("start", 0)
            c_end = lr.get("end", 0)
            if not c_start and not c_end:
                continue
            if c_start <= m_start <= c_end:
                span = c_end - c_start
                if best_span is None or span < best_span:
                    best_span = span
                    best_idx = idx
        if best_idx is not None:
            ownership.setdefault(best_idx, []).append(m)
    return ownership


def _module_level_functions(
    methods: list[dict[str, Any]],
    classes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return methods that don't fall inside any class/interface range."""
    class_ranges = [cls.get("line_range") or {} for cls in classes if cls is not None]
    result = []
    for method in methods:
        method_start = (method.get("line_range") or {}).get("start", 0)
        in_class = any(
            rng.get("start", 0) <= method_start <= rng.get("end", 0)
            for rng in class_ranges
        )
        if not in_class:
            result.append(method)
    return result


def _trim_trailing_blank_lines(lines: list[str]) -> None:
    """Remove trailing blank lines in-place."""
    while lines and lines[-1] == "":
        lines.pop()
