"""JavaScript/TypeScript import extractor."""

from typing import Any

from ._shared import _node_text

_JS_BUILTIN = {
    "fs",
    "path",
    "http",
    "https",
    "os",
    "util",
    "stream",
    "events",
    "crypto",
    "buffer",
    "child_process",
    "cluster",
    "dgram",
    "dns",
    "net",
    "querystring",
    "readline",
    "repl",
    "tls",
    "url",
    "v8",
    "vm",
    "zlib",
    "assert",
    "console",
    "process",
    "timers",
    "module",
    "perf_hooks",
}


def _js_import_module_path(node: Any, source: str) -> str | None:
    """Return the module path of a JS ``import ... from "X"`` statement.

    Skips builtin module names (e.g. ``"fs"``, ``"path"``) so the
    detected dependency list reflects user-space imports only.
    Returns ``None`` when the statement has no string child.
    """
    module_path: str | None = None
    for child in node.children:
        if getattr(child, "type", None) != "string":
            continue
        raw = _node_text(child, source).strip("'\"")
        if not raw.startswith(".") and not raw.startswith("/") and raw in _JS_BUILTIN:
            continue
        module_path = raw
    return module_path


def _collect_require_call_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Walk a JS ``require('mod')`` call node, appending non-builtin imports."""
    func = node.child_by_field_name("function")
    if not (func and _node_text(func, source) == "require"):
        return
    args_node = node.child_by_field_name("arguments")
    if not (args_node and hasattr(args_node, "children")):
        return
    for child in args_node.children:
        if getattr(child, "type", None) != "string":
            continue
        raw = _node_text(child, source).strip("'\"")
        if raw in _JS_BUILTIN:
            continue
        imports.append(
            {
                "module_name": raw,
                "resolved_path": raw,
                "names": [],
                "is_relative": raw.startswith("."),
                "language": "javascript",
            }
        )


def extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        module_path = _js_import_module_path(node, source)
        if module_path:
            is_rel = module_path.startswith(".")
            imports.append(
                {
                    "module_name": module_path,
                    "resolved_path": module_path,
                    "names": [],
                    "is_relative": is_rel,
                    "language": "javascript",
                }
            )

    elif node_type == "call_expression":
        _collect_require_call_imports(node, source, imports)


def _extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    extract_js_imports(node, source, imports)
