"""C include, macro, and utility helpers — extracted from c_plugin.py."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Function, Import, Variable
from ..utils import log_debug


def extract_c_imports(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract C include directives."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "preproc_include":
            info = _extract_include_info(child, get_node_text)
            if info:
                imports.append(info)

    if not imports and "#include" in source_code:
        log_debug("No includes found via tree-sitter, trying regex fallback")
        imports.extend(_extract_includes_fallback(source_code))

    log_debug(f"Extracted {len(imports)} C includes")
    return imports


def extract_parameters(
    params_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract function parameters."""
    parameters: list[str] = []
    for child in params_node.children:
        if child.type == "parameter_declaration":
            parameters.append(get_node_text(child))
        elif child.type == "variadic_parameter":
            parameters.append("...")
    return parameters


def parse_function_signature(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str, str, list[str], list[str]] | None:
    """Parse C function signature."""
    try:
        name = None
        return_type = "int"
        parameters: list[str] = []
        modifiers: list[str] = []

        def find_function_declarator(n: Any) -> None:
            nonlocal name, parameters
            for child in n.children:
                if child.type == "function_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "identifier":
                            name = get_node_text(grandchild)
                        elif grandchild.type == "parameter_list":
                            parameters = extract_params_fn(grandchild)
                elif child.type == "pointer_declarator":
                    find_function_declarator(child)

        for child in node.children:
            if child.type == "function_declarator":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        name = get_node_text(grandchild)
                    elif grandchild.type == "parameter_list":
                        parameters = extract_params_fn(grandchild)
            elif child.type == "pointer_declarator":
                find_function_declarator(child)
                if return_type and "*" not in return_type:
                    return_type = return_type + "*"
            elif child.type in (
                "primitive_type",
                "type_identifier",
                "sized_type_specifier",
            ):
                return_type = get_node_text(child)
            elif child.type == "storage_class_specifier":
                mod = get_node_text(child)
                if mod:
                    modifiers.append(mod)
            elif child.type == "type_qualifier":
                mod = get_node_text(child)
                if mod:
                    modifiers.append(mod)

        if not name:
            return None

        return name, return_type, parameters, modifiers
    except Exception:
        return None


def extract_macro_definition(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract macro definitions as constants."""
    variables: list[Variable] = []
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        name = None
        for child in node.children:
            if child.type == "identifier":
                name = get_node_text(child)
                break

        if name:
            raw_text = get_node_text(node)
            variables.append(
                Variable(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type="macro",
                    modifiers=["const", "macro"],
                    is_constant=True,
                    visibility="public",
                )
            )
    except Exception as e:
        log_debug(f"Failed to extract macro: {e}")

    return variables


def extract_macro_function(
    node: Any,
    get_node_text: Callable[..., str],
) -> Function | None:
    """Extract macro function definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        name = None
        params: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                name = get_node_text(child)
            elif child.type == "preproc_params":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        params.append(get_node_text(grandchild))
                    elif grandchild.type == "variadic_parameter":
                        params.append("...")

        if name:
            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=get_node_text(node),
                language="c",
                parameters=params,
                return_type="macro",
                modifiers=["macro"],
                visibility="public",
                complexity_score=1,
            )
    except Exception as e:
        log_debug(f"Failed to extract macro function: {e}")
    return None


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity."""
    decision_nodes = {
        "if_statement",
        "while_statement",
        "for_statement",
        "switch_statement",
        "case_statement",
        "conditional_expression",
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
    """Extract comment for a specific line."""
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
                elif line_content.startswith("/*"):
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


def _extract_include_info(
    node: Any,
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
                language="c",
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
                        language="c",
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
                            language="c",
                            module_name=include_path,
                            import_statement=line,
                        )
                    )

    return imports
