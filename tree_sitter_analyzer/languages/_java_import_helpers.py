"""Java package and import extraction helpers."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Import, Package
from ..utils import log_debug, log_error


def extract_java_imports(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
    set_package: Callable[[str], None],
) -> list[Import]:
    """Extract Java import statements."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "package_declaration":
            pkg = _extract_package_name(child, get_node_text)
            if pkg:
                set_package(pkg)
        elif child.type == "import_declaration":
            info = _extract_import_info(child, get_node_text)
            if info:
                imports.append(info)
        elif child.type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
        ):
            break

    if not imports and "import" in source_code:
        log_debug("No imports found via tree-sitter, trying regex fallback")
        imports.extend(_extract_imports_fallback(source_code))

    log_debug(f"Extracted {len(imports)} Java imports")
    return imports


def extract_java_packages(
    tree: Any,
    get_node_text: Callable[..., str],
) -> list[Package]:
    """Extract Java package declarations."""
    packages: list[Package] = []

    def find_packages(node: Any) -> None:
        if node.type == "package_declaration":
            info = _extract_package_element(node, get_node_text)
            if info:
                packages.append(info)
        for child in node.children:
            find_packages(child)

    find_packages(tree.root_node)

    log_debug(f"Extracted {len(packages)} Java packages")
    return packages


def _extract_package_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Extract package name from a package declaration node."""
    try:
        package_text = get_node_text(node)
        match = re.search(r"package\s+([\w.]+)", package_text)
        if match:
            return match.group(1)
    except (AttributeError, ValueError, IndexError) as e:
        log_debug(f"Failed to extract package name: {e}")
    except Exception as e:
        log_error(f"Unexpected error in package extraction: {e}")
    return None


def _extract_package_element(
    node: Any,
    get_node_text: Callable[..., str],
) -> Package | None:
    """Extract package as a Package model element."""
    try:
        package_text = get_node_text(node)
        match = re.search(r"package\s+([\w.]+)", package_text)
        if match:
            return Package(
                name=match.group(1),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=package_text,
                language="java",
            )
    except (AttributeError, ValueError, IndexError) as e:
        log_debug(f"Failed to extract package element: {e}")
    except Exception as e:
        log_error(f"Unexpected error in package element extraction: {e}")
    return None


def _extract_import_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract import information from import declaration node."""
    try:
        import_text = get_node_text(node)
        line_num = node.start_point[0] + 1
        return _extract_import_from_text(import_text, line_num, import_text)
    except Exception as e:
        log_debug(f"Failed to extract import info: {e}")
    return None


def _extract_imports_fallback(source_code: str) -> list[Import]:
    """Fallback import extraction using regex."""
    imports: list[Import] = []

    for line_num, line in enumerate(source_code.split("\n"), 1):
        import_info = _extract_import_from_line(line, line_num)
        if import_info:
            imports.append(import_info)

    return imports


def _extract_import_from_line(line: str, line_num: int) -> Import | None:
    stripped = line.strip()
    if not stripped.startswith("import ") or not stripped.endswith(";"):
        return None
    import_content = stripped[:-1]
    return _extract_import_from_text(import_content, line_num, stripped)


def _extract_import_from_text(
    import_text: str,
    line_num: int,
    raw_text: str,
) -> Import | None:
    if "static" in import_text:
        return _extract_static_import(import_text, line_num, raw_text)
    return _extract_regular_import(import_text, line_num, raw_text)


def _extract_static_import(
    import_text: str,
    line_num: int,
    raw_text: str,
) -> Import | None:
    static_match = re.search(r"import\s+static\s+([\w.]+)", import_text)
    if not static_match:
        return None
    import_name = _normalize_static_import_name(static_match.group(1), import_text)
    return _build_import(import_name, line_num, raw_text, import_text, is_static=True)


def _extract_regular_import(
    import_text: str,
    line_num: int,
    raw_text: str,
) -> Import | None:
    normal_match = re.search(r"import\s+([\w.]+)", import_text)
    if not normal_match:
        return None
    import_name = _normalize_regular_import_name(normal_match.group(1), import_text)
    return _build_import(import_name, line_num, raw_text, import_text, is_static=False)


def _normalize_static_import_name(import_name: str, import_text: str) -> str:
    if import_text.endswith(".*"):
        import_name = import_name.replace(".*", "")
    parts = import_name.split(".")
    if len(parts) > 1:
        return ".".join(parts[:-1])
    return import_name


def _normalize_regular_import_name(import_name: str, import_text: str) -> str:
    if not import_text.endswith(".*"):
        return import_name
    if import_name.endswith(".*"):
        return import_name[:-2]
    if import_name.endswith("."):
        return import_name[:-1]
    return import_name


def _build_import(
    import_name: str,
    line_num: int,
    raw_text: str,
    import_statement: str,
    *,
    is_static: bool,
) -> Import:
    return Import(
        name=import_name,
        start_line=line_num,
        end_line=line_num,
        raw_text=raw_text,
        language="java",
        module_name=import_name,
        is_static=is_static,
        is_wildcard=import_statement.endswith(".*"),
        import_statement=import_statement,
    )
