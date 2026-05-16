"""C include, macro, and utility helpers — extracted from c_plugin.py."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_debug, log_error, log_warning


# Extract elements from AST: extract_c_imports
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
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


# Extract elements from AST: extract_parameters
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


# Parse input into structured data: parse_function_signature
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

        # Search for patterns or elements: find_function_declarator
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


# Extract elements from AST: extract_macro_definition
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


# Extract elements from AST: extract_macro_function
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


# Process: calculate_complexity
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

    # Process: count_decisions
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


_TYPE_NODES_FIELD = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "sized_type_specifier",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
    }
)

_TYPE_NODES_VAR = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "sized_type_specifier",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
    }
)


# Extract elements from AST: extract_field_declaration
def extract_field_declaration(
    node: Any, get_node_text: Callable[..., str]
) -> list[Variable]:
    """Extract struct/union field declarations."""
    fields: list[Variable] = []

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        field_type = None
        field_names: list[str] = []
        modifiers: list[str] = []

        for child in node.children:
            if child.type in _TYPE_NODES_FIELD:
                field_type = get_node_text(child)
            elif child.type == "type_qualifier":
                mod = get_node_text(child)
                if mod:
                    modifiers.append(mod)
            elif child.type == "field_identifier":
                field_names.append(get_node_text(child))
            elif child.type == "array_declarator":
                for grandchild in child.children:
                    if grandchild.type == "field_identifier":
                        field_names.append(get_node_text(grandchild))
                field_type = field_type + "[]" if field_type else "[]"
            elif child.type == "field_declaration_list":
                pass
            elif child.type == "init_declarator":
                for grandchild in child.children:
                    if grandchild.type == "field_identifier":
                        field_names.append(get_node_text(grandchild))
                    elif grandchild.type == "identifier":
                        field_names.append(get_node_text(grandchild))
            elif child.type == "pointer_declarator":
                for grandchild in child.children:
                    if grandchild.type == "field_identifier":
                        field_names.append(get_node_text(grandchild))
                        field_type = field_type + "*" if field_type else "*"

        if not field_type or not field_names:
            return fields

        raw_text = get_node_text(node)

        for field_name in field_names:
            fields.append(
                Variable(
                    name=field_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type=field_type,
                    modifiers=modifiers,
                    is_constant="const" in modifiers,
                    visibility="public",
                )
            )
    except Exception as e:
        log_debug(f"Failed to extract field info: {e}")

    return fields


# Extract elements from AST: extract_variable_declaration
def extract_variable_declaration(
    node: Any, get_node_text: Callable[..., str]
) -> list[Variable]:
    """Extract C variable declarations (not struct members)."""
    if node.parent and node.parent.type == "field_declaration_list":
        return []

    variables: list[Variable] = []

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        var_type = None
        var_names: list[str] = []
        modifiers: list[str] = []

        for child in node.children:
            if child.type in _TYPE_NODES_VAR:
                var_type = get_node_text(child)
            elif child.type == "storage_class_specifier":
                mod = get_node_text(child)
                if mod:
                    modifiers.append(mod)
            elif child.type == "type_qualifier":
                mod = get_node_text(child)
                if mod:
                    modifiers.append(mod)
            elif child.type == "identifier":
                var_names.append(get_node_text(child))
            elif child.type == "init_declarator":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        var_names.append(get_node_text(grandchild))
            elif child.type == "pointer_declarator":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        var_names.append(get_node_text(grandchild))
                        var_type = var_type + "*" if var_type else "*"

        if not var_type or not var_names:
            return variables

        raw_text = get_node_text(node)
        visibility = "private" if "static" in modifiers else "public"

        for var_name in var_names:
            variables.append(
                Variable(
                    name=var_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type=var_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
            )
    except Exception as e:
        log_debug(f"Failed to extract variable declaration: {e}")

    return variables


# Extract elements from AST: extract_struct_definition
def extract_struct_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract struct definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        struct_name = None
        for child in node.children:
            if child.type == "type_identifier":
                struct_name = get_node_text(child)

        if not struct_name and node.parent and node.parent.type == "type_definition":
            for sibling in node.parent.children:
                if sibling.type == "type_identifier":
                    struct_name = get_node_text(sibling)
                    start_line = node.parent.start_point[0] + 1
                    end_line = node.parent.end_point[0] + 1
                    break

        if not struct_name:
            struct_name = f"anonymous_struct_{start_line}"

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        docstring = extract_comment_for_line(start_line, content_lines)

        return Class(
            name=struct_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="c",
            class_type="struct",
            full_qualified_name=struct_name,
            docstring=docstring,
        )
    except Exception as e:
        log_debug(f"Failed to extract struct info: {e}")
        return None


# Extract elements from AST: extract_enum_definition
def extract_enum_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract enum definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        enum_name = None
        for child in node.children:
            if child.type == "type_identifier":
                enum_name = get_node_text(child)

        if not enum_name and node.parent and node.parent.type == "type_definition":
            for sibling in node.parent.children:
                if sibling.type == "type_identifier":
                    enum_name = get_node_text(sibling)
                    start_line = node.parent.start_point[0] + 1
                    end_line = node.parent.end_point[0] + 1
                    break

        if not enum_name:
            enum_name = f"anonymous_enum_{start_line}"

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        docstring = extract_comment_for_line(start_line, content_lines)

        return Class(
            name=enum_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="c",
            class_type="enum",
            full_qualified_name=enum_name,
            docstring=docstring,
        )
    except Exception as e:
        log_debug(f"Failed to extract enum info: {e}")
        return None


# Extract elements from AST: extract_comment_for_line
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


# Extract elements from AST: _extract_include_info
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


# Extract elements from AST: _extract_includes_fallback
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


_C_CONTAINER_NODE_TYPES = frozenset(
    {
        "translation_unit",
        "compound_statement",
        "struct_specifier",
        "union_specifier",
        "field_declaration_list",
        "declaration_list",
        "type_definition",
    }
)


# Extract elements from AST: c_traverse_and_extract
def c_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Iterative node traversal and extraction with caching for C."""
    if root_node is None:
        return

    target_node_types = set(extractors.keys())

    node_stack = [(root_node, 0)]
    processed_count = 0
    max_depth = 50

    while node_stack:
        current_node, depth = node_stack.pop()

        if depth > max_depth:
            log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
            continue

        processed_count += 1
        node_type = current_node.type

        if (
            depth > 0
            and node_type not in target_node_types
            and node_type not in _C_CONTAINER_NODE_TYPES
        ):
            continue

        if node_type in target_node_types:
            node_id = id(current_node)

            if node_id in processed_nodes:
                continue

            cache_key = (node_id, element_type)
            if cache_key in element_cache:
                element = element_cache[cache_key]
                if element:
                    if isinstance(element, list):
                        results.extend(element)
                    else:
                        results.append(element)
                processed_nodes.add(node_id)
                continue

            extractor = extractors[node_type]
            element = extractor(current_node)
            element_cache[cache_key] = element
            if element:
                if isinstance(element, list):
                    results.extend(element)
                else:
                    results.append(element)
            processed_nodes.add(node_id)

        if current_node.children:
            for child in reversed(current_node.children):
                node_stack.append((child, depth + 1))

    log_debug(f"Iterative traversal processed {processed_count} nodes")


# Extract elements from AST: extract_c_function
def extract_c_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_function_signature: Callable,
    calculate_complexity: Callable,
    extract_comment_for_line: Callable,
) -> Function | None:
    """Extract C function definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        function_info = parse_function_signature(node)
        if not function_info:
            return None

        name, return_type, parameters, modifiers = function_info

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        complexity_score = calculate_complexity(node)
        docstring = extract_comment_for_line(start_line)

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="c",
            parameters=parameters,
            return_type=return_type or "int",
            modifiers=modifiers,
            is_static="static" in modifiers,
            visibility="public",
            docstring=docstring,
            complexity_score=complexity_score,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug(f"Failed to extract function info: {e}")
        return None
    except Exception as e:
        log_error(f"Unexpected error in function extraction: {e}")
        return None

