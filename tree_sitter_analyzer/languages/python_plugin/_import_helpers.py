"""Import and query helpers for the Python language extractor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...models import Import
from ...utils.tree_sitter_compat import TreeSitterQueryCompat, get_node_text_safe


@dataclass(slots=True)
class ImportExtractionRuntime:
    tree: Any
    source_code: str
    import_query: str
    extract_import_info: Callable[[Any, str, str], Import | None]
    extract_imports_manual: Callable[[Any, str], list[Import]]
    log_debug_fn: Callable[[str], None]
    log_warning_fn: Callable[[str], None]


@dataclass(slots=True)
class ClassBodyQueryRuntime:
    tree: Any
    class_query: str
    log_debug_fn: Callable[[str], None]
    log_warning_fn: Callable[[str], None]


@dataclass(slots=True)
class ImportNodeContext:
    source_code: str
    start_line: int
    end_line: int
    raw_text: str


def import_node_context(node: Any, source_code: str) -> ImportNodeContext:
    # ``node.start_byte``/``end_byte`` are UTF-8 byte offsets. Slicing a Python
    # ``str`` by those offsets is off-by-N whenever the source contains any
    # multi-byte character (e.g. an em-dash in a docstring), which mangles every
    # downstream import literal. ``get_node_text_safe`` decodes via bytes.
    raw_text = (
        get_node_text_safe(node, source_code) if hasattr(node, "start_byte") else ""
    )
    return ImportNodeContext(
        source_code=source_code,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
    )


def parse_simple_import(
    node: Any, context: ImportNodeContext, imports: list[Import]
) -> None:
    """Handle: import os, sys, json."""
    for child in node.children:
        if child.type not in ("dotted_name", "identifier"):
            continue
        module_name = _node_source_text(child, context.source_code)
        if module_name and module_name != "import":
            imports.append(
                Import(
                    name=module_name,
                    start_line=context.start_line,
                    end_line=context.end_line,
                    raw_text=context.raw_text,
                    module_name=module_name,
                    imported_names=[module_name],
                    element_type="import",
                )
            )


def parse_from_import(
    node: Any, context: ImportNodeContext, imports: list[Import]
) -> None:
    """Handle: from abc import ABC, abstractmethod."""
    module_name, imported_items = _parse_from_import_parts(node, context.source_code)
    if not module_name:
        return

    imports.append(
        Import(
            name=(
                f"from {module_name} import {', '.join(imported_items)}"
                if imported_items
                else f"from {module_name}"
            ),
            start_line=context.start_line,
            end_line=context.end_line,
            raw_text=context.raw_text,
            module_name=module_name,
            imported_names=imported_items,
            element_type="import",
        )
    )


def parse_from_import_parts(node: Any, source_code: str) -> tuple[str, list[str]]:
    """Public alias for :func:`_parse_from_import_parts` (J6).

    Plugins that consume tree-sitter query captures (rather than walking
    the AST themselves) need to recover ``(module_name, bound_names)``
    from a raw ``import_from_statement`` node — the public name keeps
    that helper reachable without importing a leading-underscore symbol.
    """
    return _parse_from_import_parts(node, source_code)


def _parse_from_import_parts(node: Any, source_code: str) -> tuple[str, list[str]]:
    """Pick apart a ``from X import (A, B as b, C)`` statement node.

    Returns ``(module_name, bound_names)`` where ``bound_names`` is the
    list of identifiers the import actually introduces into the local
    namespace — i.e. the alias when one is present, otherwise the
    imported symbol itself. J6: previously this routine collapsed the
    entire parenthesised block (including newlines and trailing
    comments) into a single ``name`` field.
    """
    children = list(node.children)
    # Tree-sitter normally emits an explicit ``import`` keyword child that
    # separates the module from the imported items. Some legacy callers
    # (and the older mock-based tests) hand-build children without that
    # keyword — in that case fall back to "first dotted_name = module,
    # rest = imports".
    has_import_keyword = any(child.type == "import" for child in children)
    if has_import_keyword:
        return _split_from_import_with_keyword(children, source_code)
    return _split_from_import_without_keyword(children, source_code)


def _split_from_import_with_keyword(
    children: list[Any], source_code: str
) -> tuple[str, list[str]]:
    module_name = ""
    imported_items: list[str] = []
    saw_import_keyword = False

    for child in children:
        if child.type == "import":
            saw_import_keyword = True
            continue
        if not saw_import_keyword:
            if child.type in ("dotted_name", "relative_import"):
                child_text = _node_source_text(child, source_code)
                if child_text and not module_name:
                    module_name = child_text
            continue
        if child.type == "import_list":
            imported_items.extend(_collect_import_list_items(child, source_code))
        elif child.type == "aliased_import":
            bound = _bound_name_from_aliased_import(child, source_code)
            if bound:
                imported_items.append(bound)
        elif child.type in ("dotted_name", "identifier"):
            child_text = _node_source_text(child, source_code)
            if child_text:
                imported_items.append(child_text)
        elif child.type == "wildcard_import":
            imported_items.append("*")

    return module_name, imported_items


def _split_from_import_without_keyword(
    children: list[Any], source_code: str
) -> tuple[str, list[str]]:
    """Legacy heuristic: first ``dotted_name`` is the module, rest are imports.

    Preserved for callers (and tests) that synthesize import nodes by
    hand without an explicit ``import`` keyword child.
    """
    module_name = ""
    imported_items: list[str] = []
    for child in children:
        if child.type == "dotted_name":
            child_text = _node_source_text(child, source_code)
            if not module_name:
                module_name = child_text
            elif child_text:
                imported_items.append(child_text)
        elif child.type == "import_list":
            imported_items.extend(_collect_import_list_items(child, source_code))
        elif child.type == "aliased_import":
            bound = _bound_name_from_aliased_import(child, source_code)
            if bound:
                imported_items.append(bound)
    return module_name, imported_items


def _bound_name_from_aliased_import(node: Any, source_code: str) -> str:
    """Return the locally bound identifier for an ``aliased_import`` node.

    For ``X as Y`` the bound name is ``Y``; we return the identifier
    that appears after the ``as`` keyword. Fall back to the first
    ``dotted_name``/``identifier`` child when the alias is absent
    (defensive — tree-sitter should always emit the alias).
    """
    seen_as = False
    for child in node.children:
        if child.type == "as":
            seen_as = True
            continue
        if seen_as and child.type == "identifier":
            return _node_source_text(child, source_code)
    # Defensive fallback — return the original symbol.
    for child in node.children:
        if child.type in ("dotted_name", "identifier"):
            return _node_source_text(child, source_code)
    return ""


def _collect_import_list_items(import_list_node: Any, source_code: str) -> list[str]:
    imported_items: list[str] = []
    for child in import_list_node.children:
        if child.type == "aliased_import":
            bound = _bound_name_from_aliased_import(child, source_code)
            if bound:
                imported_items.append(bound)
            continue
        if child.type not in ("dotted_name", "identifier"):
            continue
        item = _node_source_text(child, source_code)
        if item and item not in (",", "(", ")"):
            imported_items.append(item)
    return imported_items


def _node_source_text(node: Any, source_code: str) -> str:
    # Byte-aware slice (see ``import_node_context`` above) — required for files
    # containing any multi-byte character.
    if not hasattr(node, "start_byte"):
        return ""
    return get_node_text_safe(node, source_code)


def query_class_body_nodes(runtime: ClassBodyQueryRuntime) -> list[Any]:
    try:
        language = runtime.tree.language if hasattr(runtime.tree, "language") else None
        if not language:
            return []
        return _query_class_body_nodes(runtime, language)
    except Exception as exc:
        runtime.log_warning_fn(f"Could not extract Python class attributes: {exc}")
        return []


def _query_class_body_nodes(runtime: ClassBodyQueryRuntime, language: Any) -> list[Any]:
    try:
        captures = TreeSitterQueryCompat.safe_execute_query(
            language,
            runtime.class_query,
            runtime.tree.root_node,
            fallback_result=[],
        )
        return [node for node, capture_name in captures if capture_name == "class.body"]
    except Exception as exc:
        runtime.log_debug_fn(
            f"Could not extract Python class attributes using query: {exc}"
        )
        return []


def extract_imports_from_tree(runtime: ImportExtractionRuntime) -> list[Import]:
    imports: list[Import] = []

    try:
        language = runtime.tree.language if hasattr(runtime.tree, "language") else None
        if language:
            imports.extend(_query_imports(runtime, language))
    except Exception as exc:
        runtime.log_warning_fn(f"Could not extract Python imports: {exc}")
        imports.extend(
            runtime.extract_imports_manual(runtime.tree.root_node, runtime.source_code)
        )

    return imports


def _query_imports(runtime: ImportExtractionRuntime, language: Any) -> list[Import]:
    imports: list[Import] = []

    try:
        captures = TreeSitterQueryCompat.safe_execute_query(
            language,
            runtime.import_query,
            runtime.tree.root_node,
            fallback_result=[],
        )
        _extend_imports_from_captures(runtime, captures, imports)
    except Exception as query_error:
        runtime.log_debug_fn(
            f"Query execution failed, using manual extraction: {query_error}"
        )
        imports.extend(
            runtime.extract_imports_manual(runtime.tree.root_node, runtime.source_code)
        )

    return imports


def _extend_imports_from_captures(
    runtime: ImportExtractionRuntime, captures: Any, imports: list[Import]
) -> None:
    processed_positions: set[tuple[int, int]] = set()

    for node, capture_name in captures:
        position_key = (node.start_point[0], node.end_point[0])
        if position_key in processed_positions:
            continue

        processed_positions.add(position_key)
        import_type = "from_import" if "from" in capture_name else "import"
        imported = runtime.extract_import_info(node, runtime.source_code, import_type)
        if imported:
            imports.append(imported)
