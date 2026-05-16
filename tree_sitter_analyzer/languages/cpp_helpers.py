"""C++ include, namespace, and visibility helpers — extracted from cpp_plugin.py."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_debug, log_error, log_warning


# Extract elements from AST: extract_cpp_imports
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
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


# Extract elements from AST: extract_cpp_namespaces
def extract_cpp_namespaces(
    tree: Any,
    get_node_text: Callable[..., str],
) -> list[Any]:
    """Extract C++ namespace declarations."""

    packages: list[Any] = []

    # Search for patterns or elements: find_namespaces
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


# Extract elements from AST: _extract_include_info
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


# Extract elements from AST: _extract_namespace_info
def _extract_namespace_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> Any:
    """Extract namespace information."""
    from ..models import Package

    try:
        namespace_name = None

        for child in node.children:
            # Check: child.type in ("identifier", "namespace_
            if child.type in ("identifier", "namespace_identifier"):
                namespace_name = get_node_text(child)

        # Check: namespace_name
        if namespace_name:
            # Return result
            return Package(
                name=namespace_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=get_node_text(node),
                language="cpp",
            )
    except Exception as e:
        log_debug(f"Failed to extract namespace info: {e}")

    # Return result
    return None


# Process: is_global_scope
def is_global_scope(node: Any) -> bool:
    """Check if a node is in global scope (not inside a class/struct/union)."""
    current = node.parent
    while current is not None:
        if current.type in (
            "class_specifier",
            "struct_specifier",
            "union_specifier",
        ):
            # Return result
            return False
        current = current.parent
    # Return result
    return True


# Process: get_access_specifier
def get_access_specifier(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Get the current access specifier for a class member."""
    parent = node.parent
    # Check: not parent or parent.type != "field_decl
    if not parent or parent.type != "field_declaration_list":
        # Return result
        return None

    siblings = list(parent.children)
    try:
        node_index = siblings.index(node)
    except ValueError:
        # Return result
        return None

    # Iterate over i
    for i in range(node_index - 1, -1, -1):
        sibling = siblings[i]
        # Check: sibling.type == "access_specifier"
        if sibling.type == "access_specifier":
            spec_text = get_node_text(sibling).strip().rstrip(":")
            # Check: spec_text in ("public", "private", "prot
            if spec_text in ("public", "private", "protected"):
                # Return result
                return spec_text

    class_node = parent.parent
    # Check: class_node
    if class_node:
        # Check: class_node.type == "class_specifier"
        if class_node.type == "class_specifier":
            # Return result
            return "private"
        elif class_node.type in ("struct_specifier", "union_specifier"):
            # Return result
            return "public"

    # Return result
    return None


# Process: determine_visibility
def determine_visibility(
    modifiers: list[str],
    is_global: bool = False,
    node: Any = None,
    get_node_text: Callable[..., str] | None = None,
) -> str:
    """Determine visibility from modifiers and context."""
    # Check: "public" in modifiers
    if "public" in modifiers:
        # Return result
        return "public"
    elif "private" in modifiers:
        # Return result
        return "private"
    elif "protected" in modifiers:
        # Return result
        return "protected"

    # Check: "static" in modifiers and is_global
    if "static" in modifiers and is_global:
        # Return result
        return "private"

    # Check: node and not is_global and get_node_text
    if node and not is_global and get_node_text:
        access_spec = get_access_specifier(node, get_node_text)
        # Check: access_spec
        if access_spec:
            # Return result
            return access_spec

    # Return result
    return "public" if is_global else "private"


# Process: calculate_complexity
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

    # Process: count_decisions
    def count_decisions(n: Any) -> int:
        count = 0
        # Check: hasattr(n, "type") and n.type in decisio
        if hasattr(n, "type") and n.type in decision_nodes:
            count += 1
        # Check: hasattr(n, "children")
        if hasattr(n, "children"):
            try:
                # Iterate over child
                for child in n.children:
                    count += count_decisions(child)
            except (TypeError, AttributeError):
                pass
        # Return result
        return count

    # Return result
    return 1 + count_decisions(node)


# Extract elements from AST: extract_comment_for_line
def extract_comment_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract comment (documentation) for a specific line."""
    try:
        # Iterate over i
        for i in range(max(0, line - 5), line):
            # Check: i < len(content_lines)
            if i < len(content_lines):
                line_content = content_lines[i].strip()
                # Check: line_content.startswith("/**")
                if line_content.startswith("/**"):
                    comment_lines = []
                    # Iterate over j
                    for j in range(i, min(len(content_lines), line)):
                        doc_line = content_lines[j].strip()
                        comment_lines.append(doc_line)
                        # Check: doc_line.endswith("*/")
                        if doc_line.endswith("*/"):
                            break
                    # Return result
                    return "\n".join(comment_lines)
                elif line_content.startswith("///"):
                    # Return result
                    return line_content
    except Exception as e:
        log_debug(f"Failed to extract comment: {e}")

    # Return result
    return None


# Extract elements from AST: extract_parameters
def extract_parameters(
    params_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract function parameters."""
    parameters: list[str] = []
    # Iterate over child
    for child in params_node.children:
        if child.type in (
            "parameter_declaration",
            "optional_parameter_declaration",
        ):
            parameters.append(get_node_text(child))
        elif child.type == "variadic_parameter_declaration":
            parameters.append("...")
    # Return result
    return parameters


# Parse input into structured data: parse_function_signature
def parse_function_signature(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str, str, list[str], list[str]] | None:
    """Parse C++ function signature."""
    try:
        name = None
        return_type = "void"
        parameters: list[str] = []
        modifiers: list[str] = []

        # Iterate over child
        for child in node.children:
            # Check: child.type == "function_declarator"
            if child.type == "function_declarator":
                # Iterate over grandchild
                for grandchild in child.children:
                    if grandchild.type in (
                        "identifier",
                        "qualified_identifier",
                        "field_identifier",
                        "operator_name",
                        "destructor_name",
                    ):
                        name = get_node_text(grandchild)
                    elif grandchild.type == "parameter_list":
                        parameters = extract_params_fn(grandchild)
            elif child.type == "reference_declarator":
                return_type = return_type + "&" if return_type else "&"
                # Iterate over grandchild
                for grandchild in child.children:
                    # Check: grandchild.type == "function_declarator"
                    if grandchild.type == "function_declarator":
                        # Iterate over ggchild
                        for ggchild in grandchild.children:
                            if ggchild.type in (
                                "identifier",
                                "field_identifier",
                                "operator_name",
                                "destructor_name",
                            ):
                                name = get_node_text(ggchild)
                            elif ggchild.type == "parameter_list":
                                parameters = extract_params_fn(ggchild)
            elif child.type == "pointer_declarator":
                return_type = return_type + "*" if return_type else "*"
                # Iterate over grandchild
                for grandchild in child.children:
                    # Check: grandchild.type == "function_declarator"
                    if grandchild.type == "function_declarator":
                        # Iterate over ggchild
                        for ggchild in grandchild.children:
                            if ggchild.type in (
                                "identifier",
                                "field_identifier",
                                "operator_name",
                            ):
                                name = get_node_text(ggchild)
                            elif ggchild.type == "parameter_list":
                                parameters = extract_params_fn(ggchild)
            elif child.type in (
                "primitive_type",
                "type_identifier",
                "qualified_identifier",
                "template_type",
            ):
                return_type = get_node_text(child)
            elif child.type == "storage_class_specifier":
                mod = get_node_text(child)
                # Check: mod
                if mod:
                    modifiers.append(mod)
            elif child.type == "type_qualifier":
                mod = get_node_text(child)
                # Check: mod
                if mod:
                    modifiers.append(mod)
            elif child.type == "virtual":
                modifiers.append("virtual")
            elif child.type == "delete_method_clause":
                # Check: "deleted" not in modifiers
                if "deleted" not in modifiers:
                    modifiers.append("deleted")
            elif child.type == "default_method_clause":
                # Check: "default" not in modifiers
                if "default" not in modifiers:
                    modifiers.append("default")

        # Check: not name
        if not name:
            # Return result
            return None

        # Return result
        return name, return_type, parameters, modifiers
    except Exception:
        # Return result
        return None


# Extract elements from AST: extract_function_from_field_declaration
def extract_function_from_field_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
    is_global_fn: Callable[[Any], bool],
    determine_vis_fn: Callable[..., str],
    extract_comment_fn: Callable[[int], str | None],
) -> Function | None:
    """Extract function from field_declaration (pure virtual, deleted, etc)."""
    try:
        has_function_declarator = False
        # Iterate over child
        for child in node.children:
            # Check: child.type == "function_declarator"
            if child.type == "function_declarator":
                has_function_declarator = True
                break

        # Check: not has_function_declarator
        if not has_function_declarator:
            # Return result
            return None

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        name = None
        return_type = "void"
        parameters: list[str] = []
        modifiers: list[str] = []

        # Iterate over child
        for child in node.children:
            # Check: child.type == "virtual"
            if child.type == "virtual":
                modifiers.append("virtual")
            elif child.type in (
                "primitive_type",
                "type_identifier",
                "qualified_identifier",
                "template_type",
            ):
                return_type = get_node_text(child)
            elif child.type == "function_declarator":
                # Iterate over grandchild
                for grandchild in child.children:
                    if grandchild.type in (
                        "field_identifier",
                        "identifier",
                        "destructor_name",
                        "operator_name",
                    ):
                        name = get_node_text(grandchild)
                    elif grandchild.type == "parameter_list":
                        parameters = extract_params_fn(grandchild)
                    elif grandchild.type == "type_qualifier":
                        mod = get_node_text(grandchild)
                        # Check: mod
                        if mod:
                            modifiers.append(mod)
            elif child.type == "number_literal" and get_node_text(child) == "0":
                # Check: "pure_virtual" not in modifiers
                if "pure_virtual" not in modifiers:
                    modifiers.append("pure_virtual")
            elif child.type == "delete_method_clause":
                # Check: "deleted" not in modifiers
                if "deleted" not in modifiers:
                    modifiers.append("deleted")
            elif child.type == "default_method_clause":
                # Check: "default" not in modifiers
                if "default" not in modifiers:
                    modifiers.append("default")

        # Check: not name
        if not name:
            # Return result
            return None

        raw_text = get_node_text(node)
        is_global = is_global_fn(node)
        visibility = determine_vis_fn(modifiers, is_global=is_global, node=node)
        docstring = extract_comment_fn(start_line)

        # Return result
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="cpp",
            parameters=parameters,
            return_type=return_type,
            modifiers=modifiers,
            visibility=visibility,
            docstring=docstring,
            complexity_score=1,
        )
    except Exception as e:
        log_debug(f"Failed to extract function from field declaration: {e}")
        # Return result
        return None


# Extract elements from AST: extract_function_declaration
def extract_function_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> Function | None:
    """Extract function declaration (prototype)."""
    # Check: node.parent and node.parent.type == "fun
    if node.parent and node.parent.type == "function_definition":
        # Return result
        return None

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        name = None
        parameters: list[str] = []

        # Iterate over child
        for child in node.children:
            # Check: child.type in ("identifier", "qualified_
            if child.type in ("identifier", "qualified_identifier"):
                name = get_node_text(child)
            elif child.type == "parameter_list":
                parameters = extract_params_fn(child)

        # Check: not name
        if not name:
            # Return result
            return None

        raw_text = get_node_text(node)

        # Return result
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="cpp",
            parameters=parameters,
            return_type="void",
            modifiers=[],
        )
    except Exception as e:
        log_debug(f"Failed to extract function declaration: {e}")
        # Return result
        return None


# Extract elements from AST: extract_base_classes
def extract_base_classes(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    """Extract base class names from base_class_clause."""
    base_classes: list[str] = []
    # Iterate over child
    for child in node.children:
        # Check: child.type == "base_specifier"
        if child.type == "base_specifier":
            # Iterate over grandchild
            for grandchild in child.children:
                # Check: grandchild.type in ("type_identifier", "
                if grandchild.type in ("type_identifier", "template_type"):
                    base_classes.append(get_node_text(grandchild))
    # Return result
    return base_classes


_TYPE_NODES_CPP = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "qualified_identifier",
        "template_type",
    }
)


# Extract elements from AST: extract_cpp_field_declaration
def extract_cpp_field_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    is_global_fn: Callable[[Any], bool],
    determine_vis_fn: Callable[..., str],
) -> list[Variable]:
    """Extract C++ field declarations."""
    fields: list[Variable] = []

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        field_type = None
        field_names: list[str] = []
        modifiers: list[str] = []

        # Iterate over child
        for child in node.children:
            # Check: child.type in _TYPE_NODES_CPP
            if child.type in _TYPE_NODES_CPP:
                field_type = get_node_text(child)
            elif child.type == "storage_class_specifier":
                mod = get_node_text(child)
                # Check: mod
                if mod:
                    modifiers.append(mod)
            elif child.type == "type_qualifier":
                mod = get_node_text(child)
                # Check: mod
                if mod:
                    modifiers.append(mod)
            elif child.type == "field_identifier":
                field_names.append(get_node_text(child))
            elif child.type == "init_declarator":
                # Iterate over grandchild
                for grandchild in child.children:
                    # Check: grandchild.type in ("field_identifier",
                    if grandchild.type in ("field_identifier", "identifier"):
                        field_names.append(get_node_text(grandchild))

        # Check: not field_type or not field_names
        if not field_type or not field_names:
            # Return result
            return fields

        raw_text = get_node_text(node)
        is_global = is_global_fn(node)
        visibility = determine_vis_fn(modifiers, is_global=is_global, node=node)

        # Iterate over field_name
        for field_name in field_names:
            fields.append(
                Variable(
                    name=field_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="cpp",
                    variable_type=field_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
            )
    except Exception as e:
        log_debug(f"Failed to extract field info: {e}")

    # Return result
    return fields


# Extract elements from AST: extract_cpp_variable_declaration
def extract_cpp_variable_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    is_global_fn: Callable[[Any], bool],
    determine_vis_fn: Callable[..., str],
) -> list[Variable]:
    """Extract C++ variable declarations (not class members)."""
    # Check: node.parent and node.parent.type == "fie
    if node.parent and node.parent.type == "field_declaration_list":
        # Return result
        return []

    variables: list[Variable] = []

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        var_type = None
        var_names: list[str] = []
        modifiers: list[str] = []

        # Iterate over child
        for child in node.children:
            # Check: child.type in _TYPE_NODES_CPP
            if child.type in _TYPE_NODES_CPP:
                var_type = get_node_text(child)
            elif child.type == "storage_class_specifier":
                mod = get_node_text(child)
                # Check: mod
                if mod:
                    modifiers.append(mod)
            elif child.type == "type_qualifier":
                mod = get_node_text(child)
                # Check: mod
                if mod:
                    modifiers.append(mod)
            elif child.type == "identifier":
                var_names.append(get_node_text(child))
            elif child.type == "init_declarator":
                # Iterate over grandchild
                for grandchild in child.children:
                    # Check: grandchild.type == "identifier"
                    if grandchild.type == "identifier":
                        var_names.append(get_node_text(grandchild))

        # Check: not var_type or not var_names
        if not var_type or not var_names:
            # Return result
            return variables

        raw_text = get_node_text(node)
        is_global = is_global_fn(node)
        visibility = determine_vis_fn(modifiers, is_global=is_global, node=node)

        # Iterate over var_name
        for var_name in var_names:
            variables.append(
                Variable(
                    name=var_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="cpp",
                    variable_type=var_type,
                    modifiers=modifiers,
                    is_static="static" in modifiers,
                    is_constant="const" in modifiers,
                    visibility=visibility,
                )
            )
    except Exception as e:
        log_debug(f"Failed to extract variable declaration: {e}")

    # Return result
    return variables


_CONTAINER_NODE_TYPES = frozenset(
    {
        "translation_unit",
        "namespace_definition",
        "class_specifier",
        "struct_specifier",
        "union_specifier",
        "declaration_list",
        "field_declaration_list",
        "compound_statement",
        "template_declaration",
        "declaration",
    }
)


# Extract elements from AST: traverse_and_extract_iterative
def traverse_and_extract_iterative(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Iterative node traversal and extraction with caching."""
    # Check: root_node is None
    if root_node is None:
        return

    target_node_types = set(extractors.keys())

    node_stack = [(root_node, 0)]
    processed_count = 0
    max_depth = 50

    while node_stack:
        current_node, depth = node_stack.pop()

        # Check: depth > max_depth
        if depth > max_depth:
            log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
            continue

        processed_count += 1
        node_type = current_node.type

        if (
            depth > 0
            and node_type not in target_node_types
            and node_type not in _CONTAINER_NODE_TYPES
        ):
            continue

        # Check: node_type in target_node_types
        if node_type in target_node_types:
            node_id = id(current_node)

            # Check: node_id in processed_nodes
            if node_id in processed_nodes:
                continue

            cache_key = (node_id, element_type)
            # Check: cache_key in element_cache
            if cache_key in element_cache:
                element = element_cache[cache_key]
                # Check: element
                if element:
                    # Check: isinstance(element, list)
                    if isinstance(element, list):
                        results.extend(element)
                    else:
                        results.append(element)
                processed_nodes.add(node_id)
                continue

            extractor = extractors[node_type]
            element = extractor(current_node)
            element_cache[cache_key] = element
            # Check: element
            if element:
                # Check: isinstance(element, list)
                if isinstance(element, list):
                    results.extend(element)
                else:
                    results.append(element)
            processed_nodes.add(node_id)

        # Check: current_node.children
        if current_node.children:
            # Iterate over child
            for child in reversed(current_node.children):
                node_stack.append((child, depth + 1))

    log_debug(f"Iterative traversal processed {processed_count} nodes")


# Extract elements from AST: extract_cpp_function
def extract_cpp_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    current_namespace: str,
    parse_function_signature: Callable,
    calculate_complexity: Callable,
    is_global_scope: Callable,
    determine_visibility: Callable,
    extract_comment_for_line: Callable,
) -> Function | None:
    """Extract C++ function definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        function_info = parse_function_signature(node)
        # Check: not function_info
        if not function_info:
            # Return result
            return None

        name, return_type, parameters, modifiers = function_info

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        complexity_score = calculate_complexity(node)

        is_global = is_global_scope(node)
        visibility = determine_visibility(modifiers, is_global=is_global, node=node)

        docstring = extract_comment_for_line(start_line)

        # Return result
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="cpp",
            parameters=parameters,
            return_type=return_type or "void",
            modifiers=modifiers,
            is_static="static" in modifiers,
            is_private="private" in modifiers,
            is_public="public" in modifiers,
            visibility=visibility,
            docstring=docstring,
            complexity_score=complexity_score,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug(f"Failed to extract function info: {e}")
        # Return result
        return None
    except Exception as e:
        log_error(f"Unexpected error in function extraction: {e}")
        # Return result
        return None


# Extract elements from AST: extract_cpp_class
def extract_cpp_class(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    current_namespace: str,
    extract_base_classes: Callable,
    extract_comment_for_line: Callable,
) -> Class | None:
    """Extract C++ class/struct/union information."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        class_name = None
        superclasses: list[str] = []
        modifiers: list[str] = []

        # Iterate over child
        for child in node.children:
            # Check: child.type == "type_identifier"
            if child.type == "type_identifier":
                class_name = get_node_text(child)
            elif child.type == "base_class_clause":
                superclasses = extract_base_classes(child)

        # Check: not class_name
        if not class_name:
            # Return result
            return None

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        docstring = extract_comment_for_line(start_line)

        full_qualified_name = (
            f"{current_namespace}::{class_name}" if current_namespace else class_name
        )

        # Return result
        return Class(
            name=class_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="cpp",
            class_type="class",
            full_qualified_name=full_qualified_name,
            package_name=current_namespace,
            superclass=superclasses[0] if superclasses else None,
            interfaces=superclasses[1:] if len(superclasses) > 1 else [],
            modifiers=modifiers,
            docstring=docstring,
        )
    except Exception as e:
        log_debug(f"Failed to extract class info: {e}")
        # Return result
        return None
