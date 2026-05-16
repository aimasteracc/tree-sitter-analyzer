"""TypeScript import extraction — extracted from extractor.py."""

import re
from collections.abc import Callable
from typing import Any

from ...models import Import
from ...utils import log_debug


# Extract elements from AST: extract_ts_imports
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
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
        if hasattr(node, "start_point") and hasattr(node, "end_point"):
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
        else:
            start_line = 1
            end_line = 1

        raw_text = ""
        if hasattr(node, "start_byte") and hasattr(node, "end_byte") and source_code:
            source_bytes = source_code.encode("utf-8")
            raw_text = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
        elif hasattr(node, "text"):
            text = node.text
            if isinstance(text, bytes):
                raw_text = text.decode("utf-8")
            else:
                raw_text = str(text)
        else:
            raw_text = get_node_text(node)

        import_names: list[str] = []
        module_path = ""

        if hasattr(node, "children") and node.children:
            for child in node.children:
                if child.type == "import_clause":
                    import_names.extend(
                        _extract_import_names(child, source_code, get_node_text)
                    )
                elif child.type == "string":
                    if (
                        hasattr(child, "start_byte")
                        and hasattr(child, "end_byte")
                        and source_code
                    ):
                        source_bytes = source_code.encode("utf-8")
                        module_text = source_bytes[
                            child.start_byte : child.end_byte
                        ].decode("utf-8")
                        module_path = module_text.strip("\"'")
                    elif hasattr(child, "text"):
                        text = child.text
                        if isinstance(text, bytes):
                            module_path = text.decode("utf-8").strip("\"'")
                        else:
                            module_path = str(text).strip("\"'")

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


# Extract elements from AST: _extract_import_names
def _extract_import_names(
    import_clause_node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract import names from import clause."""
    names: list[str] = []

    try:
        if not (
            hasattr(import_clause_node, "children") and import_clause_node.children
        ):
            return names

        children = import_clause_node.children
        source_bytes = source_code.encode("utf-8") if source_code else b""

        for child in children:
            if child.type == "import_default_specifier":
                if hasattr(child, "children") and child.children:
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            name_text = _extract_identifier_text(
                                grandchild, source_bytes
                            )
                            if name_text:
                                names.append(name_text)
            elif child.type == "named_imports":
                if hasattr(child, "children") and child.children:
                    for grandchild in child.children:
                        if grandchild.type == "import_specifier":
                            name_text = get_node_text(grandchild)
                            if name_text:
                                names.append(name_text)
                        elif hasattr(grandchild, "children") and grandchild.children:
                            for ggchild in grandchild.children:
                                if ggchild.type == "identifier":
                                    name_text = _extract_identifier_text(
                                        ggchild, source_bytes
                                    )
                                    if name_text:
                                        names.append(name_text)
            elif child.type == "identifier":
                name_text = _extract_identifier_text(child, source_bytes)
                if name_text:
                    names.append(name_text)
            elif child.type == "namespace_import":
                if hasattr(child, "children") and child.children:
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            name_text = _extract_identifier_text(
                                grandchild, source_bytes
                            )
                            if name_text:
                                names.append(f"* as {name_text}")
    except Exception as e:
        log_debug(f"Failed to extract import names: {e}")

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

        import_match = re.search(r"import\s*\(\s*[\"']([^\"']+)[\"']\s*\)", node_text)
        if not import_match:
            import_match = re.search(r"import\s*\(\s*([^)]+)\s*\)", node_text)
            if import_match:
                source = import_match.group(1).strip("\"'")
            else:
                return None
        else:
            source = import_match.group(1)

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


# Extract elements from AST: _extract_commonjs_requires
def _extract_commonjs_requires(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract CommonJS require() statements (for compatibility)."""
    imports: list[Import] = []

    try:
        if tree and hasattr(tree, "root_node") and tree.root_node:
            get_node_text(tree.root_node)

        require_pattern = (
            r"(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
        )

        for match in re.finditer(require_pattern, source_code):
            var_name = match.group(1)
            module_path = match.group(2)

            line_num = source_code[: match.start()].count("\n") + 1

            import_obj = Import(
                name=var_name,
                start_line=line_num,
                end_line=line_num,
                raw_text=match.group(0),
                language="typescript",
                module_path=module_path,
                module_name=module_path,
                imported_names=[var_name],
            )
            imports.append(import_obj)

    except Exception as e:
        log_debug(f"Failed to extract CommonJS requires: {e}")
        return []

    return imports

