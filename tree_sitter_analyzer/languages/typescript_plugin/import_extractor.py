"""TypeScript import extraction — extracted from extractor.py."""

import re
from collections.abc import Callable
from typing import Any

from ...models import Import
from ...utils import log_debug

_COMMONJS_REQUIRE_PATTERN = re.compile(
    r"(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
)


# Extract elements from AST: extract_ts_imports
def extract_ts_imports(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract TypeScript import statements with ES6+ and type import support."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "import_statement":
            import_info = _extract_import_info_simple(child, source_code, get_node_text)
            if import_info:
                imports.append(import_info)
        elif child.type == "expression_statement":
            dynamic_import = _extract_dynamic_import(child, get_node_text)
            if dynamic_import:
                imports.append(dynamic_import)

    commonjs_imports = _extract_commonjs_requires(tree, source_code, get_node_text)
    imports.extend(commonjs_imports)

    log_debug(f"Extracted {len(imports)} TypeScript imports")
    return imports


# Extract elements from AST: _extract_import_info_simple
def _extract_import_info_simple(
    node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract import information from import_statement node."""
    try:
        return _build_import_info(node, source_code, get_node_text)

    except Exception as e:
        log_debug(f"Failed to extract import info: {e}")
        return None


def _build_import_info(
    node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> Import | None:
    start_line, end_line = _node_line_range(node)
    raw_text = _extract_node_text(node, source_code, get_node_text)
    import_names, module_path = _extract_import_statement_parts(
        node, source_code, get_node_text
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


# Extract elements from AST: _extract_import_names
def _extract_import_names(
    import_clause_node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract import names from import clause."""
    names: list[str] = []

    try:
        source_bytes = source_code.encode("utf-8") if source_code else b""

        for child in _iter_typed_children(import_clause_node):
            names.extend(
                _extract_import_child_names(child, source_bytes, get_node_text)
            )
    except Exception as e:
        log_debug(f"Failed to extract import names: {e}")

    return names


def _extract_import_statement_parts(
    node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> tuple[list[str], str]:
    import_names: list[str] = []
    module_path = ""

    for child in _iter_typed_children(node):
        if child.type == "import_clause":
            import_names.extend(
                _extract_import_names(child, source_code, get_node_text)
            )
            continue

        if child.type == "string":
            module_path = _extract_string_literal(child, source_code)

    return import_names, module_path


def _extract_import_child_names(
    child: Any, source_bytes: bytes, get_node_text: Callable[..., str]
) -> list[str]:
    if child.type == "import_default_specifier":
        return _extract_identifier_names(child, source_bytes)

    if child.type == "named_imports":
        return _extract_named_import_names(child, source_bytes, get_node_text)

    if child.type == "identifier":
        name_text = _extract_identifier_text(child, source_bytes)
        return [name_text] if name_text else []

    if child.type == "namespace_import":
        return _extract_namespace_import_names(child, source_bytes)

    return []


def _node_line_range(node: Any) -> tuple[int, int]:
    if hasattr(node, "start_point") and hasattr(node, "end_point"):
        return node.start_point[0] + 1, node.end_point[0] + 1
    return 1, 1


def _extract_node_text(
    node: Any, source_code: str, get_node_text: Callable[..., str]
) -> str:
    if hasattr(node, "start_byte") and hasattr(node, "end_byte") and source_code:
        source_bytes = source_code.encode("utf-8")
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8")

    if hasattr(node, "text"):
        text = node.text
        return text.decode("utf-8") if isinstance(text, bytes) else str(text)

    return get_node_text(node)


def _iter_typed_children(node: Any) -> list[Any]:
    if not (hasattr(node, "children") and node.children):
        return []
    return [child for child in node.children if hasattr(child, "type")]


def _extract_string_literal(node: Any, source_code: str) -> str:
    if hasattr(node, "start_byte") and hasattr(node, "end_byte") and source_code:
        source_bytes = source_code.encode("utf-8")
        return (
            source_bytes[node.start_byte : node.end_byte].decode("utf-8").strip("\"'")
        )

    if hasattr(node, "text"):
        text = node.text
        text_value = text.decode("utf-8") if isinstance(text, bytes) else str(text)
        return text_value.strip("\"'")

    return ""


def _extract_identifier_names(node: Any, source_bytes: bytes) -> list[str]:
    names = []
    for child in _iter_typed_children(node):
        if child.type != "identifier":
            continue

        name_text = _extract_identifier_text(child, source_bytes)
        if name_text:
            names.append(name_text)
    return names


def _extract_named_import_names(
    node: Any, source_bytes: bytes, get_node_text: Callable[..., str]
) -> list[str]:
    names = []
    for child in _iter_typed_children(node):
        if child.type == "import_specifier":
            name_text = get_node_text(child)
            if name_text:
                names.append(name_text)
            continue

        names.extend(_extract_identifier_names(child, source_bytes))
    return names


def _extract_namespace_import_names(node: Any, source_bytes: bytes) -> list[str]:
    names = []
    for child in _iter_typed_children(node):
        if child.type != "identifier":
            continue

        name_text = _extract_identifier_text(child, source_bytes)
        if name_text:
            names.append(f"* as {name_text}")
    return names


# Extract elements from AST: _extract_identifier_text
def _extract_identifier_text(node: Any, source_bytes: bytes) -> str:
    """Extract text from an identifier node."""
    if hasattr(node, "start_byte") and hasattr(node, "end_byte") and source_bytes:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8")
    if hasattr(node, "text"):
        text = node.text
        if isinstance(text, bytes):
            return text.decode("utf-8")
        return str(text)
    return ""


# Extract elements from AST: _extract_dynamic_import
def _extract_dynamic_import(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract dynamic import() calls."""
    try:
        node_text = get_node_text(node)
        source = _extract_dynamic_import_source(node_text)
        if not source:
            return None

        return Import(
            name="dynamic_import",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=node_text,
            language="typescript",
            module_name=source,
            module_path=source,
            imported_names=["dynamic_import"],
        )
    except Exception as e:
        log_debug(f"Failed to extract dynamic import: {e}")
        return None


def _extract_dynamic_import_source(node_text: str) -> str:
    import_match = re.search(r"import\s*\(\s*[\"']([^\"']+)[\"']\s*\)", node_text)
    if import_match:
        return import_match.group(1)

    import_match = re.search(r"import\s*\(\s*([^)]+)\s*\)", node_text)
    if import_match:
        return import_match.group(1).strip("\"'")

    return ""


# Extract elements from AST: _extract_commonjs_requires
def _extract_commonjs_requires(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract CommonJS require() statements (for compatibility)."""
    try:
        _touch_root_text(tree, get_node_text)
        return _build_commonjs_require_imports(source_code)

    except Exception as e:
        log_debug(f"Failed to extract CommonJS requires: {e}")
        return []


def _touch_root_text(tree: Any, get_node_text: Callable[..., str]) -> None:
    if tree and hasattr(tree, "root_node") and tree.root_node:
        get_node_text(tree.root_node)


def _build_commonjs_require_imports(source_code: str) -> list[Import]:
    imports: list[Import] = []

    for match in _COMMONJS_REQUIRE_PATTERN.finditer(source_code):
        imports.append(_build_commonjs_require_import(source_code, match))

    return imports


def _build_commonjs_require_import(source_code: str, match: re.Match[str]) -> Import:
    var_name = match.group(1)
    module_path = match.group(2)
    line_num = source_code[: match.start()].count("\n") + 1

    return Import(
        name=var_name,
        start_line=line_num,
        end_line=line_num,
        raw_text=match.group(0),
        language="typescript",
        module_path=module_path,
        module_name=module_path,
        imported_names=[var_name],
    )
