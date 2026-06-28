"""Import-info extraction helpers for the TypeScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from ...models import Import
from ...utils import log_debug
from ..shared.traversal import node_range

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
ImportNameExtractor: TypeAlias = Callable[["tree_sitter.Node"], list[str]]


def extract_import_info_simple(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_import_names: ImportNameExtractor,
) -> Import | None:
    """Extract import information from an import_statement node."""
    try:
        start_line, end_line = _line_span(node)
        raw_text = get_node_text(node)
        import_names, module_path = _import_parts(
            node, get_node_text, extract_import_names
        )

        if not module_path and not import_names:
            return None

        primary_name = import_names[0] if import_names else "unknown"
        return Import(
            name=primary_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="typescript",
            module_path=module_path,
            module_name=module_path,
            imported_names=import_names,
        )
    except Exception as e:
        log_debug(f"Failed to extract import info: {e}")
        return None


def _line_span(node: tree_sitter.Node) -> tuple[int, int]:
    result = node_range(node)
    return result if result != (0, 0) else (1, 1)


def _import_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_import_names: ImportNameExtractor,
) -> tuple[list[str], str]:
    import_names: list[str] = []
    module_path = ""

    for child in getattr(node, "children", []) or []:
        child_type = getattr(child, "type", None)
        if child_type == "import_clause":
            import_names.extend(extract_import_names(child))
        elif child_type == "string":
            module_path = _module_path_from_child(child, get_node_text)

    return import_names, module_path


def _module_path_from_child(
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> str:
    text = getattr(child, "text", "")
    if isinstance(text, bytes):
        return text.decode("utf-8").strip("\"'")
    if isinstance(text, str):
        return text.strip("\"'")
    return get_node_text(child).strip("\"'")
