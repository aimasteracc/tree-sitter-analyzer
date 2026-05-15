"""Java import, package, and utility helpers — extracted from java_plugin.py."""

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

    packages: list[Any] = []

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

        if "static" in import_text:
            static_match = re.search(r"import\s+static\s+([\w.]+)", import_text)
            if static_match:
                import_name = static_match.group(1)
                if import_text.endswith(".*"):
                    import_name = import_name.replace(".*", "")
                parts = import_name.split(".")
                if len(parts) > 1:
                    import_name = ".".join(parts[:-1])
                return Import(
                    name=import_name,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=import_text,
                    language="java",
                    module_name=import_name,
                    is_static=True,
                    is_wildcard=import_text.endswith(".*"),
                    import_statement=import_text,
                )
        else:
            normal_match = re.search(r"import\s+([\w.]+)", import_text)
            if normal_match:
                import_name = normal_match.group(1)
                if import_text.endswith(".*"):
                    if import_name.endswith(".*"):
                        import_name = import_name[:-2]
                    elif import_name.endswith("."):
                        import_name = import_name[:-1]
                return Import(
                    name=import_name,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=import_text,
                    language="java",
                    module_name=import_name,
                    is_static=False,
                    is_wildcard=import_text.endswith(".*"),
                    import_statement=import_text,
                )
    except Exception as e:
        log_debug(f"Failed to extract import info: {e}")
    return None


def _extract_imports_fallback(source_code: str) -> list[Import]:
    """Fallback import extraction using regex."""
    imports: list[Import] = []
    lines = source_code.split("\n")

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if line.startswith("import ") and line.endswith(";"):
            import_content = line[:-1]

            if "static" in import_content:
                static_match = re.search(r"import\s+static\s+([\w.]+)", import_content)
                if static_match:
                    import_name = static_match.group(1)
                    if import_content.endswith(".*"):
                        import_name = import_name.replace(".*", "")
                    parts = import_name.split(".")
                    if len(parts) > 1:
                        import_name = ".".join(parts[:-1])
                    imports.append(
                        Import(
                            name=import_name,
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=line,
                            language="java",
                            module_name=import_name,
                            is_static=True,
                            is_wildcard=import_content.endswith(".*"),
                            import_statement=import_content,
                        )
                    )
            else:
                normal_match = re.search(r"import\s+([\w.]+)", import_content)
                if normal_match:
                    import_name = normal_match.group(1)
                    if import_content.endswith(".*"):
                        if import_name.endswith(".*"):
                            import_name = import_name[:-2]
                        elif import_name.endswith("."):
                            import_name = import_name[:-1]
                    imports.append(
                        Import(
                            name=import_name,
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=line,
                            language="java",
                            module_name=import_name,
                            is_static=False,
                            is_wildcard=import_content.endswith(".*"),
                            import_statement=import_content,
                        )
                    )

    return imports


def determine_visibility(modifiers: list[str]) -> str:
    """Determine visibility from Java modifiers."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"
    return "package"


def is_nested_class(node: Any) -> bool:
    """Check if a node is inside a class/interface/enum declaration."""
    parent = node.parent
    while parent:
        if parent.type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
        ):
            return True
        parent = parent.parent
    return False


def find_parent_class(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Find parent class name for nested classes."""
    parent = node.parent
    while parent:
        if parent.type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
        ):
            for child in parent.children:
                if child.type == "identifier":
                    return get_node_text(child)
        parent = parent.parent
    return None


def extract_class_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Extract class name from a class declaration node."""
    try:
        for child in node.children:
            if child.type == "identifier":
                return get_node_text(child)
    except Exception as e:
        log_debug(f"Failed to extract class name: {e}")
    return None


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity."""
    decision_nodes = {
        "if_statement",
        "while_statement",
        "for_statement",
        "switch_statement",
        "catch_clause",
        "conditional_expression",
        "enhanced_for_statement",
    }

    def count_decisions(n: Any) -> int:
        count = 0
        if hasattr(n, "type") and n.type in decision_nodes:
            count += 1
        if hasattr(n, "children"):
            try:
                for child in n.children:
                    count += count_decisions(child)
            except (TypeError, AttributeError):
                pass
        return count

    return 1 + count_decisions(node)


def extract_javadoc_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract JavaDoc comment for a specific line."""
    try:
        for i in range(max(0, line - 10), line):
            if i < len(content_lines):
                line_content = content_lines[i].strip()
                if line_content.startswith("/**"):
                    javadoc_lines = []
                    for j in range(i, min(len(content_lines), line)):
                        doc_line = content_lines[j].strip()
                        javadoc_lines.append(doc_line)
                        if doc_line.endswith("*/"):
                            break
                    return "\n".join(javadoc_lines)
    except Exception as e:
        log_debug(f"Failed to extract JavaDoc: {e}")
    return None
