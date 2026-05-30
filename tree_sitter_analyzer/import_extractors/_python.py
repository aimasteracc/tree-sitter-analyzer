"""Python import extractor."""

from typing import Any

from ._shared import _node_text

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


def _parse_relative_import(child: Any, source: str) -> tuple[str, str]:
    """Return (dots_prefix, module_name) from a ``relative_import`` node."""
    dots = ""
    module = ""
    for sub in child.children:
        st = getattr(sub, "type", None)
        if st == "import_prefix":
            dots = _node_text(sub, source)
        elif st == "dotted_name":
            module = _node_text(sub, source)
    return dots, module


def _collect_aliased_import_names(
    aliased_node: Any, source: str, names: list[str]
) -> None:
    """Append identifiers from ``aliased_import`` (handles ``foo as bar``)."""
    for sub in aliased_node.children:
        st = getattr(sub, "type", None)
        if st in ("dotted_name", "identifier"):
            names.append(_node_text(sub, source))


def _extract_import_names(names_node: Any, source: str) -> list[str]:
    """Extract individual names from an import_list or aliased_import node."""
    names: list[str] = []
    if not hasattr(names_node, "children"):
        return names
    for child in names_node.children:
        ct = getattr(child, "type", None)
        if ct in ("dotted_name", "identifier"):
            text = _node_text(child, source)
            if text and text != ",":
                names.append(text)
        elif ct == "aliased_import":
            _collect_aliased_import_names(child, source, names)
    return names


def _parse_python_from_children(node: Any, source: str) -> tuple[str, str, list[str]]:
    """Walk an ``import_from_statement``'s children; return ``(module, dots, names)``.

    Recognised child types:
    - ``relative_import`` — yields ``dots`` (from ``import_prefix``) and possibly
      ``module`` (from inner ``dotted_name``).
    - ``dotted_name`` — first occurrence (when no module/dots are set yet) is the
      module; subsequent ones are imported symbols.
    - ``aliased_import`` — appends bound names via ``_extract_import_names``.
    """
    module_name = ""
    dots_prefix = ""
    imported_names: list[str] = []
    for child in node.children:
        ct = getattr(child, "type", None)
        if ct == "relative_import":
            dots_prefix, module_name = _parse_relative_import(child, source)
        elif ct == "dotted_name":
            node_text = _node_text(child, source)
            is_module = not module_name and not dots_prefix
            if is_module:
                module_name = node_text
            if not is_module:
                imported_names.append(node_text)
        elif ct == "aliased_import":
            imported_names.extend(_extract_import_names(child, source))
    return module_name, dots_prefix, imported_names


def _emit_relative_submodule_imports(
    dots_prefix: str,
    imported_names: list[str],
    imports: list[dict[str, Any]],
) -> None:
    """Emit one entry per imported name for ``from . import a, b`` shape."""
    for name in imported_names:
        full_module = dots_prefix + name
        imports.append(
            {
                "module_name": full_module,
                "resolved_path": full_module.replace(".", "/") + ".py",
                "names": [name],
                "is_relative": True,
                "language": "python",
            }
        )


def _emit_python_from_import(
    dots_prefix: str,
    module_name: str,
    imported_names: list[str],
    imports: list[dict[str, Any]],
) -> None:
    """Emit a single entry for ``from <prefix>module import a, b`` shape."""
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


def extract_python_import_from(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Handle: from [.][.]module import name1, name2"""
    module_name, dots_prefix, imported_names = _parse_python_from_children(node, source)

    if dots_prefix and not module_name:
        # Case: from . import x, y
        _emit_relative_submodule_imports(dots_prefix, imported_names, imports)
        return

    if not module_name:
        return

    _emit_python_from_import(dots_prefix, module_name, imported_names, imports)


def _extract_python_imports(
    node: Any, source: str, imports: list[dict[str, Any]]
) -> None:
    """Extract Python import statements."""
    node_type = getattr(node, "type", None)

    if node_type == "import_statement":
        extract_python_import_simple(node, source, imports)
    elif node_type == "import_from_statement":
        extract_python_import_from(node, source, imports)
