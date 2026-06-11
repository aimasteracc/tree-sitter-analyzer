"""Signatures (lightweight method-directory) table rendering for the Python formatter.

``signatures`` mode is the first step of the "directory → pick → batch-read"
large-file strategy.  It lists every method in ``name →returnType(Np)
startLine-endLine`` form (N = parameter count, *not* full types) grouped by
class.  The resulting output is ~25% of full-mode token cost, letting an agent
scan all method names before choosing which bodies to fetch via
``action=read``.

Mirrors the shape of ``_java_formatter_signatures_mixin`` but uses Python
naming conventions (no package line; module-level functions rendered as a
top-level block rather than a flat-file fallback).
"""

from __future__ import annotations

from typing import Any


def format_python_signatures_table(data: dict[str, Any]) -> str:
    """Render a lightweight method-directory for the given Python structure data.

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
    # Python structure uses "methods" for both class methods and module functions
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
        for cls in classes:
            _append_class_block(lines, cls, all_methods)
    else:
        # No classes — flat module with only top-level functions
        _append_module_functions_block(lines, all_methods)

    # Module-level functions (not belonging to any class)
    if classes:
        module_funcs = _module_level_functions(all_methods, classes)
        if module_funcs:
            _append_module_functions_block(lines, module_funcs)

    # Agent hint
    lines.append("")
    lines.append("next_step: Pick methods by name, then use action=read to get bodies.")

    _trim_trailing_blank_lines(lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_name(file_path: str) -> str:
    """Extract a short module name from a file path."""
    if not file_path:
        return "module"
    basename = str(file_path).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    for ext in (".py", ".pyw", ".pyi"):
        if basename.endswith(ext):
            basename = basename[: -len(ext)]
            break
    return basename or "module"


def _append_class_block(
    lines: list[str],
    cls: dict[str, Any],
    all_methods: list[dict[str, Any]],
) -> None:
    """Emit one class block: header + method lines."""
    name = cls.get("name", "?")
    lr = cls.get("line_range") or {}
    start = lr.get("start", 0)
    end = lr.get("end", 0)
    class_methods = _methods_in_range(all_methods, lr)
    n_methods = len(class_methods)

    lines.append(f"## {name} ({start}-{end}) [{n_methods} methods]")
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
    return_type = method.get("return_type", "") or "None"
    params = method.get("parameters") or []
    n_params = len(params)
    lr = method.get("line_range") or {}
    start = lr.get("start", 0)
    end = lr.get("end", 0)
    short_ret = _shorten_return_type(return_type)
    return f"  {name} →{short_ret}({n_params}p) {start}-{end}"


_RETURN_ABBREVS: dict[str, str] = {
    "None": "None",
    "str": "str",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "Any": "Any",
    "list": "list",
    "dict": "dict",
    "tuple": "tuple",
    "set": "set",
    "bytes": "bytes",
}


def _shorten_return_type(ret: str) -> str:
    """Abbreviate common return types; leave complex generics short."""
    if not ret:
        return "None"
    # Strip Optional wrapper: Optional[X] → X
    if ret.startswith("Optional[") and ret.endswith("]"):
        ret = ret[9:-1]
    # For generics like List[str] keep first token for brevity
    bracket = ret.find("[")
    simple = ret[:bracket] if bracket != -1 else ret
    return _RETURN_ABBREVS.get(simple, simple)


def _methods_in_range(
    methods: list[dict[str, Any]],
    line_range: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return methods whose start line falls inside ``line_range``."""
    rng_start = line_range.get("start", 0)
    rng_end = line_range.get("end", 0)
    if not rng_start and not rng_end:
        return []
    return [
        m
        for m in methods
        if rng_start <= (m.get("line_range") or {}).get("start", 0) <= rng_end
    ]


def _module_level_functions(
    methods: list[dict[str, Any]],
    classes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return methods that don't fall inside any class range."""
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
