"""Go import extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Import
from ..utils import log_error


def extract_imports_from_tree(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract Go import declarations."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "import_declaration":
            imps = _extract_import_declaration(child, get_node_text)
            if imps:
                imports.extend(imps)

    return imports


def extract_import_spec(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract single import spec."""
    try:
        alias, path = _extract_import_parts(node, get_node_text)
        if not path:
            return None

        return _build_go_import(node, get_node_text, alias, path)
    except Exception as e:
        log_error(f"Error extracting Go import spec: {e}")
        return None


def _build_go_import(
    node: Any,
    get_node_text: Callable[..., str],
    alias: str | None,
    path: str,
) -> Import:
    raw_text = get_node_text(node)
    name = path.split("/")[-1] if "/" in path else path
    return Import(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        language="go",
        module_name=path,
        import_statement=raw_text,
        alias=alias,
    )


def _extract_import_parts(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None]:
    alias = None
    path = None

    for child in node.children:
        if child.type == "package_identifier":
            alias = get_node_text(child)
            continue
        if child.type == "blank_identifier":
            alias = "_"
            continue
        if child.type == "dot":
            alias = "."
            continue
        if child.type == "interpreted_string_literal":
            path = get_node_text(child).strip('"')

    return alias, path


def _extract_import_declaration(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract import declaration (may contain multiple imports)."""
    imports: list[Import] = []
    try:
        for spec in _iter_import_specs(node):
            imp = extract_import_spec(spec, get_node_text)
            if imp:
                imports.append(imp)
    except Exception as e:
        log_error(f"Error extracting Go import: {e}")
    return imports


def _iter_import_specs(node: Any) -> list[Any]:
    specs = []
    for child in node.children:
        if child.type == "import_spec":
            specs.append(child)
        elif child.type == "import_spec_list":
            specs.extend(spec for spec in child.children if spec.type == "import_spec")
    return specs
