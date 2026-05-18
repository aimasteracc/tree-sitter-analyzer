"""Import extraction functions for Python and JS/TS — extracted from project_graph.py."""

from typing import Any

_STDLIB_TOP_LEVEL = {
    "os",
    "sys",
    "re",
    "json",
    "math",
    "time",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "typing",
    "io",
    "pathlib",
    "hashlib",
    "random",
    "string",
    "textwrap",
    "logging",
    "argparse",
    "subprocess",
    "shutil",
    "tempfile",
    "unittest",
    "pytest",
    "warnings",
    "traceback",
    "abc",
    "base64",
    "csv",
    "enum",
    "dataclasses",
    "contextlib",
    "copy",
    "configparser",
    "importlib",
    "ast",
    "inspect",
    "operator",
    "struct",
    "weakref",
    "array",
    "queue",
    "socket",
    "http",
    "urllib",
    "email",
    "html",
    "xml",
    "sqlite3",
    "hmac",
    "secrets",
}

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


def walk_imports(
    node: Any, source: str, language: str, imports: list[dict[str, Any]]
) -> None:
    """Walk the AST to collect import statements."""
    try:
        if language in ("python",):
            _extract_python_imports(node, source, imports)
        elif language in ("javascript", "typescript"):
            _extract_js_imports(node, source, imports)
    except Exception:  # nosec B110
        pass

    # Recurse into real tree-sitter child lists. Mock objects can synthesize async
    # attributes here, which creates unawaited coroutine warnings during tests.
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            walk_imports(child, source, language, imports)


# Extract elements from AST: extract_python_import_simple
def extract_python_import_simple(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: import os, sys"""
    for child in node.children:
        if getattr(child, "type", None) != "dotted_name":
            continue
        name = _node_text(child, source)
        if not name or name.split(".")[0] in _STDLIB_TOP_LEVEL:
            continue
        imports.append(
            {
                "module_name": name,
                "resolved_path": name.replace(".", "/") + ".py",
                "names": [name],
                "is_relative": False,
                "language": "python",
            }
        )


# Extract elements from AST: extract_python_import_from
def extract_python_import_from(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: from [.][.]module import name1, name2"""
    module_name = ""
    dots_prefix = ""
    imported_names: list[str] = []

    for child in node.children:
        ct = getattr(child, "type", None)

        if ct == "relative_import":
            for sub in child.children:
                st = getattr(sub, "type", None)
                if st == "import_prefix":
                    dots_prefix = _node_text(sub, source)
                elif st == "dotted_name":
                    module_name = _node_text(sub, source)

        elif ct == "dotted_name":
            if not module_name and not dots_prefix:
                module_name = _node_text(child, source)
            else:
                imported_names.append(_node_text(child, source))

        elif ct == "aliased_import":
            imported_names.extend(_extract_import_names(child, source))

    if not module_name:
        return

    full_module = dots_prefix + module_name
    if not dots_prefix and module_name.split(".")[0] in _STDLIB_TOP_LEVEL:
        return

    imports.append(
        {
            "module_name": full_module,
            "resolved_path": full_module.replace(".", "/") + ".py"
            if full_module
            else "",
            "names": imported_names,
            "is_relative": bool(dots_prefix),
            "language": "python",
        }
    )


# Extract elements from AST: _extract_python_imports
def _extract_python_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Python import statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        extract_python_import_simple(node, source, imports)
    elif node_type == "import_from_statement":
        extract_python_import_from(node, source, imports)


# Extract elements from AST: extract_js_imports
def extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        # import { foo } from './bar'
        module_path = None
        for child in node.children:
            if getattr(child, "type", None) == "string":
                raw = _node_text(child, source).strip("'\"")
                if not raw.startswith(".") and not raw.startswith("/"):
                    if raw in _JS_BUILTIN:
                        continue
                module_path = raw

        if module_path:
            imports.append(
                {
                    "module_name": module_path,
                    "resolved_path": module_path,
                    "names": [],
                    "is_relative": module_path.startswith("."),
                    "language": "javascript",
                }
            )

    elif node_type == "call_expression":
        # require('./foo') or require('fs')
        func = node.child_by_field_name("function")
        if func and _node_text(func, source) == "require":
            args_node = node.child_by_field_name("arguments")
            if args_node and hasattr(args_node, "children"):
                for child in args_node.children:
                    if getattr(child, "type", None) == "string":
                        raw = _node_text(child, source).strip("'\"")

                        # Check if builtin
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


# Extract elements from AST: _extract_import_names
def _extract_import_names(names_node: Any, source: str) -> list[str]:
    """Extract individual names from an import_list or aliased_import node."""
    names = []
    if hasattr(names_node, "children"):
        for child in names_node.children:
            ct = getattr(child, "type", None)
            if ct == "dotted_name" or ct == "identifier":
                text = _node_text(child, source)
                if text and text != ",":
                    names.append(text)
            elif ct == "aliased_import":
                # Handle 'foo as bar'
                for sub in child.children:
                    st = getattr(sub, "type", None)
                    if st in ("dotted_name", "identifier"):
                        names.append(_node_text(sub, source))
    return names


# Extract elements from AST: _extract_js_imports
def _extract_js_imports(node: Any, source: str, imports: list[dict[str, Any]]) -> None:
    """Extract JS/TS import/require statements."""
    extract_js_imports(node, source, imports)


def _node_text(node: Any, source: str) -> str:
    """Safely extract text from a Tree-sitter node."""
    try:
        start = node.start_byte
        end = node.end_byte
        if (
            start is not None
            and end is not None
            and start < end <= len(source.encode("utf-8", errors="replace"))
        ):
            return source.encode("utf-8", errors="replace")[start:end].decode(
                "utf-8", errors="replace"
            )
        return ""
    except Exception:
        return ""
