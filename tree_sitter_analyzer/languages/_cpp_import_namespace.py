"""C++ include and namespace helpers."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Import
from ..utils import log_debug


def extract_cpp_imports(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract C++ include directives and using/alias declarations."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        import_info = _import_from_top_level_node(child, source_code, get_node_text)
        if import_info:
            imports.append(import_info)

    if not imports and "#include" in source_code:
        log_debug("No includes found via tree-sitter, trying regex fallback")
        imports.extend(_extract_includes_fallback(source_code))

    log_debug(f"Extracted {len(imports)} C++ includes")
    return imports


def _import_from_top_level_node(
    node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> Import | None:
    if node.type == "preproc_include":
        return _extract_include_info(node, source_code, get_node_text)
    if node.type in ("using_declaration", "alias_declaration"):
        return _declaration_import(node, get_node_text)
    return None


def _declaration_import(node: Any, get_node_text: Callable[..., str]) -> Import:
    import_text = get_node_text(node)
    line_num = node.start_point[0] + 1
    return Import(
        name=import_text,
        start_line=line_num,
        end_line=line_num,
        raw_text=import_text,
        language="cpp",
        module_name="",
        import_statement=import_text,
    )


def _extract_include_info(
    node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract include directive information."""
    try:
        include_text = get_node_text(node)
        line_num = node.start_point[0] + 1
        return _include_from_line(line_num, include_text)
    except Exception as exc:
        log_debug(f"Failed to extract include info: {exc}")
        return None


def _extract_includes_fallback(source_code: str) -> list[Import]:
    """Fallback include extraction using regex."""
    imports: list[Import] = []
    for line_num, line in enumerate(source_code.split("\n"), 1):
        include = _include_from_line(line_num, line.strip())
        if include:
            imports.append(include)
    return imports


def _include_from_line(line_num: int, line: str) -> Import | None:
    if not line.startswith("#include"):
        return None

    match = re.search(r"#include\s*<([^>]+)>", line)
    if not match:
        match = re.search(r'#include\s*"([^"]+)"', line)
    if not match:
        return None

    include_path = match.group(1)
    return Import(
        name=include_path,
        start_line=line_num,
        end_line=line_num,
        raw_text=line,
        language="cpp",
        module_name=include_path,
        import_statement=line,
    )


def extract_cpp_namespaces(
    tree: Any,
    get_node_text: Callable[..., str],
) -> list[Any]:
    """Extract C++ namespace declarations."""
    packages: list[Any] = []
    _find_namespaces(tree.root_node, get_node_text, packages)
    log_debug(f"Extracted {len(packages)} C++ namespaces")
    return packages


def _find_namespaces(
    node: Any,
    get_node_text: Callable[..., str],
    packages: list[Any],
) -> None:
    if node.type == "namespace_definition":
        info = _extract_namespace_info(node, get_node_text)
        if info:
            packages.append(info)

    for child in node.children:
        _find_namespaces(child, get_node_text, packages)


def _extract_namespace_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> Any:
    """Extract namespace information."""
    from ..models import Package

    try:
        namespace_name = _namespace_name(node, get_node_text)
        if not namespace_name:
            return None

        return Package(
            name=namespace_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="cpp",
        )
    except Exception as exc:
        log_debug(f"Failed to extract namespace info: {exc}")
        return None


def _namespace_name(node: Any, get_node_text: Callable[..., str]) -> str | None:
    for child in node.children:
        if child.type in ("identifier", "namespace_identifier"):
            return get_node_text(child)
    return None
