"""C++ include, namespace, and visibility helpers — extracted from cpp_plugin.py."""

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
    """Extract C++ include directives."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "preproc_include":
            info = _extract_include_info(child, source_code, get_node_text)
            if info:
                imports.append(info)
        elif child.type == "using_declaration":
            using_text = get_node_text(child)
            line_num = child.start_point[0] + 1
            imports.append(
                Import(
                    name=using_text,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=using_text,
                    language="cpp",
                    module_name="",
                    import_statement=using_text,
                )
            )
        elif child.type == "alias_declaration":
            alias_text = get_node_text(child)
            line_num = child.start_point[0] + 1
            imports.append(
                Import(
                    name=alias_text,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=alias_text,
                    language="cpp",
                    module_name="",
                    import_statement=alias_text,
                )
            )

    if not imports and "#include" in source_code:
        log_debug("No includes found via tree-sitter, trying regex fallback")
        imports.extend(_extract_includes_fallback(source_code))

    log_debug(f"Extracted {len(imports)} C++ includes")
    return imports


def extract_cpp_namespaces(
    tree: Any,
    get_node_text: Callable[..., str],
) -> list[Any]:
    """Extract C++ namespace declarations."""

    packages: list[Any] = []

    def find_namespaces(node: Any) -> None:
        if node.type == "namespace_definition":
            info = _extract_namespace_info(node, get_node_text)
            if info:
                packages.append(info)
        for child in node.children:
            find_namespaces(child)

    find_namespaces(tree.root_node)

    log_debug(f"Extracted {len(packages)} C++ namespaces")
    return packages


def _extract_include_info(
    node: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract include directive information."""
    try:
        include_text = get_node_text(node)
        line_num = node.start_point[0] + 1

        is_system = "<" in include_text
        if is_system:
            match = re.search(r"<([^>]+)>", include_text)
        else:
            match = re.search(r'"([^"]+)"', include_text)

        if match:
            include_path = match.group(1)
            return Import(
                name=include_path,
                start_line=line_num,
                end_line=line_num,
                raw_text=include_text,
                language="cpp",
                module_name=include_path,
                import_statement=include_text,
            )
    except Exception as e:
        log_debug(f"Failed to extract include info: {e}")

    return None


def _extract_includes_fallback(source_code: str) -> list[Import]:
    """Fallback include extraction using regex."""
    imports: list[Import] = []
    lines = source_code.split("\n")

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if line.startswith("#include"):
            system_match = re.search(r"#include\s*<([^>]+)>", line)
            if system_match:
                include_path = system_match.group(1)
                imports.append(
                    Import(
                        name=include_path,
                        start_line=line_num,
                        end_line=line_num,
                        raw_text=line,
                        language="cpp",
                        module_name=include_path,
                        import_statement=line,
                    )
                )
            else:
                local_match = re.search(r'#include\s*"([^"]+)"', line)
                if local_match:
                    include_path = local_match.group(1)
                    imports.append(
                        Import(
                            name=include_path,
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=line,
                            language="cpp",
                            module_name=include_path,
                            import_statement=line,
                        )
                    )

    return imports


def _extract_namespace_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> Any:
    """Extract namespace information."""
    from ..models import Package

    try:
        namespace_name = None

        for child in node.children:
            if child.type in ("identifier", "namespace_identifier"):
                namespace_name = get_node_text(child)

        if namespace_name:
            return Package(
                name=namespace_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=get_node_text(node),
                language="cpp",
            )
    except Exception as e:
        log_debug(f"Failed to extract namespace info: {e}")

    return None


def is_global_scope(node: Any) -> bool:
    """Check if a node is in global scope (not inside a class/struct/union)."""
    current = node.parent
    while current is not None:
        if current.type in (
            "class_specifier",
            "struct_specifier",
            "union_specifier",
        ):
            return False
        current = current.parent
    return True


def get_access_specifier(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Get the current access specifier for a class member."""
    parent = node.parent
    if not parent or parent.type != "field_declaration_list":
        return None

    siblings = list(parent.children)
    try:
        node_index = siblings.index(node)
    except ValueError:
        return None

    for i in range(node_index - 1, -1, -1):
        sibling = siblings[i]
        if sibling.type == "access_specifier":
            spec_text = get_node_text(sibling).strip().rstrip(":")
            if spec_text in ("public", "private", "protected"):
                return spec_text

    class_node = parent.parent
    if class_node:
        if class_node.type == "class_specifier":
            return "private"
        elif class_node.type in ("struct_specifier", "union_specifier"):
            return "public"

    return None


def determine_visibility(
    modifiers: list[str],
    is_global: bool = False,
    node: Any = None,
    get_node_text: Callable[..., str] | None = None,
) -> str:
    """Determine visibility from modifiers and context."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"

    if "static" in modifiers and is_global:
        return "private"

    if node and not is_global and get_node_text:
        access_spec = get_access_specifier(node, get_node_text)
        if access_spec:
            return access_spec

    return "public" if is_global else "private"


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity."""
    decision_nodes = {
        "if_statement",
        "while_statement",
        "for_statement",
        "for_range_loop",
        "switch_statement",
        "case_statement",
        "conditional_expression",
        "catch_clause",
        "do_statement",
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


def extract_comment_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract comment (documentation) for a specific line."""
    try:
        for i in range(max(0, line - 5), line):
            if i < len(content_lines):
                line_content = content_lines[i].strip()
                if line_content.startswith("/**"):
                    comment_lines = []
                    for j in range(i, min(len(content_lines), line)):
                        doc_line = content_lines[j].strip()
                        comment_lines.append(doc_line)
                        if doc_line.endswith("*/"):
                            break
                    return "\n".join(comment_lines)
                elif line_content.startswith("///"):
                    return line_content
    except Exception as e:
        log_debug(f"Failed to extract comment: {e}")

    return None
