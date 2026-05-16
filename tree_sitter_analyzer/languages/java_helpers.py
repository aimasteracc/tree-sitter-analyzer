"""Java import, package, and utility helpers — extracted from java_plugin.py."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Package, Variable
from ..utils import log_debug, log_error, log_warning


# Extract elements from AST: extract_java_imports
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
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


# Extract elements from AST: extract_java_packages
def extract_java_packages(
    tree: Any,
    get_node_text: Callable[..., str],
) -> list[Package]:
    """Extract Java package declarations."""

    packages: list[Any] = []

    # Search for patterns or elements: find_packages
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


# Extract elements from AST: _extract_package_name
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


# Extract elements from AST: _extract_package_element
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


# Extract elements from AST: _extract_import_info
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


# Extract elements from AST: _extract_imports_fallback
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


# Process: determine_visibility
def determine_visibility(modifiers: list[str]) -> str:
    """Determine visibility from Java modifiers."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"
    return "package"


# Process: is_nested_class
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


# Search for patterns or elements: find_parent_class
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


# Extract elements from AST: extract_class_name
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


_MODIFIER_KEYWORDS = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "final",
        "abstract",
        "synchronized",
        "volatile",
        "transient",
    }
)

_RETURN_TYPE_NODES = frozenset(
    {
        "type_identifier",
        "void_type",
        "primitive_type",
        "integral_type",
        "boolean_type",
        "floating_point_type",
        "array_type",
        "generic_type",
    }
)

_FIELD_TYPE_NODES = frozenset(
    {
        "type_identifier",
        "primitive_type",
        "integral_type",
        "generic_type",
        "boolean_type",
        "floating_point_type",
        "array_type",
    }
)


# Extract elements from AST: extract_modifiers
def extract_modifiers(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    """Extract modifiers from a declaration node."""
    modifiers: list[str] = []
    for child in node.children:
        if child.type == "modifiers":
            for mod_child in child.children:
                if mod_child.type in _MODIFIER_KEYWORDS:
                    modifiers.append(mod_child.type)
                elif mod_child.type != "marker_annotation":
                    mod_text = get_node_text(mod_child)
                    if mod_text in _MODIFIER_KEYWORDS:
                        modifiers.append(mod_text)
    return modifiers


# Parse input into structured data: parse_method_signature
def parse_method_signature(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, str, list[str], list[str], list[str]] | None:
    """Parse method signature into (name, return_type, parameters, modifiers, throws)."""
    try:
        method_name = None
        for child in node.children:
            if child.type == "identifier":
                method_name = get_node_text(child)
                break

        if not method_name:
            return None

        return_type = "void"
        for child in node.children:
            if child.type in _RETURN_TYPE_NODES:
                return_type = get_node_text(child)
                break

        parameters: list[str] = []
        for child in node.children:
            if child.type == "formal_parameters":
                for param in child.children:
                    if param.type == "formal_parameter":
                        parameters.append(get_node_text(param))

        modifiers = extract_modifiers(node, get_node_text)

        throws: list[str] = []
        for child in node.children:
            if child.type == "throws":
                throws_text = get_node_text(child)
                exceptions = re.findall(r"\b[A-Z]\w*Exception\b", throws_text)
                throws.extend(exceptions)

        return method_name, return_type, parameters, modifiers, throws
    except Exception:
        return None


# Parse input into structured data: parse_field_declaration
def parse_field_declaration(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, list[str], list[str]] | None:
    """Parse field declaration into (type, variable_names, modifiers)."""
    try:
        field_type = None
        for child in node.children:
            if child.type in _FIELD_TYPE_NODES:
                field_type = get_node_text(child)
                break

        if not field_type:
            return None

        variable_names: list[str] = []
        for child in node.children:
            if child.type == "variable_declarator":
                for grandchild in child.children:
                    if grandchild.type == "identifier":
                        variable_names.append(get_node_text(grandchild))

        if not variable_names:
            return None

        modifiers = extract_modifiers(node, get_node_text)

        return field_type, variable_names, modifiers
    except Exception:
        return None


# Extract elements from AST: extract_annotation
def extract_annotation(
    node: Any,
    get_node_text: Callable[..., str],
) -> dict[str, Any] | None:
    """Extract annotation information from annotation node."""
    try:
        annotation_text = get_node_text(node)
        start_line = node.start_point[0] + 1

        annotation_name = None
        for child in node.children:
            if child.type == "identifier":
                annotation_name = get_node_text(child)
                break

        if not annotation_name:
            match = re.search(r"@(\w+)", annotation_text)
            if match:
                annotation_name = match.group(1)

        if annotation_name:
            return {
                "name": annotation_name,
                "line": start_line,
                "text": annotation_text,
                "type": "annotation",
            }
    except Exception as e:
        log_debug(f"Failed to extract annotation: {e}")

    return None


# Process: calculate_complexity
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


# Extract elements from AST: extract_javadoc_for_line
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


_CLASS_TYPE_MAP = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
}

_JAVA_CONTAINER_NODES = {
    "program",
    "class_body",
    "interface_body",
    "enum_body",
    "enum_body_declarations",
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "method_declaration",
    "constructor_declaration",
    "block",
    "modifiers",
}


# Extract elements from AST: java_traverse_and_extract
def java_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Iterative node traversal and extraction with batch field processing."""
    if not root_node:
        return

    target_node_types = set(extractors.keys())

    node_stack = [(root_node, 0)]
    processed_count = 0
    max_depth = 50

    field_batch: list[Any] = []

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
            and node_type not in _JAVA_CONTAINER_NODES
        ):
            continue

        if node_type in target_node_types:
            if element_type == "field" and node_type == "field_declaration":
                field_batch.append(current_node)
            else:
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

                extractor = extractors.get(node_type)
                if extractor:
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

        if len(field_batch) >= 10:
            _process_field_batch(
                field_batch, extractors, results, processed_nodes, element_cache
            )
            field_batch.clear()

    if field_batch:
        _process_field_batch(
            field_batch, extractors, results, processed_nodes, element_cache
        )

    log_debug(f"Iterative traversal processed {processed_count} nodes")


# Process data through pipeline: _process_field_batch
def _process_field_batch(
    batch: list[Any],
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Process field nodes with caching."""
    for node in batch:
        node_id = id(node)

        if node_id in processed_nodes:
            continue

        cache_key = (node_id, "field")
        if cache_key in element_cache:
            elements = element_cache[cache_key]
            if elements:
                if isinstance(elements, list):
                    results.extend(elements)
                else:
                    results.append(elements)
            processed_nodes.add(node_id)
            continue

        extractor = extractors.get(node.type)
        if extractor:
            elements = extractor(node)
            element_cache[cache_key] = elements
            if elements:
                if isinstance(elements, list):
                    results.extend(elements)
                else:
                    results.append(elements)
            processed_nodes.add(node_id)


# Extract elements from AST: extract_java_class
def extract_java_class(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    current_package: str,
    extract_modifiers: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    is_nested_class: Callable,
    find_parent_class: Callable,
) -> Class | None:
    """Extract Java class/interface/enum information."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        class_name = None
        for child in node.children:
            if child.type == "identifier":
                class_name = get_node_text(child)
                break

        if not class_name:
            return None

        package_name = current_package
        full_qualified_name = (
            f"{package_name}.{class_name}" if package_name else class_name
        )

        class_type = _CLASS_TYPE_MAP.get(node.type, "class")

        modifiers = extract_modifiers(node)
        visibility = determine_visibility(modifiers)

        extends_class = None
        implements_interfaces: list[str] = []

        for child in node.children:
            if child.type == "superclass":
                extends_text = get_node_text(child)
                match = re.search(r"\b[A-Z]\w*", extends_text)
                if match:
                    extends_class = match.group(0)
            elif child.type == "super_interfaces":
                implements_text = get_node_text(child)
                implements_interfaces = re.findall(r"\b[A-Z]\w*", implements_text)

        class_annotations = find_annotations_for_line(start_line)

        is_nested = is_nested_class(node)
        parent_class = find_parent_class(node) if is_nested else None

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        return Class(
            name=class_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="java",
            class_type=class_type,
            full_qualified_name=full_qualified_name,
            package_name=package_name,
            superclass=extends_class,
            interfaces=implements_interfaces,
            modifiers=modifiers,
            visibility=visibility,
            annotations=class_annotations,
            is_nested=is_nested,
            parent_class=parent_class,
            extends_class=extends_class,
            implements_interfaces=implements_interfaces,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug(f"Failed to extract class info: {e}")
        return None
    except Exception as e:
        log_error(f"Unexpected error in class extraction: {e}")
        return None


# Extract elements from AST: extract_java_method
def extract_java_method(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_method_signature: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    calculate_complexity: Callable,
    extract_javadoc: Callable,
) -> Function | None:
    """Extract Java method/constructor information."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        method_info = parse_method_signature(node)
        if not method_info:
            return None

        method_name, return_type, parameters, modifiers, throws = method_info
        is_constructor = node.type == "constructor_declaration"
        visibility = determine_visibility(modifiers)

        method_annotations = find_annotations_for_line(start_line)
        complexity_score = calculate_complexity(node)
        javadoc = extract_javadoc(start_line)

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        return Function(
            name=method_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="java",
            parameters=parameters,
            return_type=return_type if not is_constructor else "void",
            modifiers=modifiers,
            is_static="static" in modifiers,
            is_private="private" in modifiers,
            is_public="public" in modifiers,
            is_constructor=is_constructor,
            visibility=visibility,
            docstring=javadoc,
            annotations=method_annotations,
            throws=throws,
            complexity_score=complexity_score,
            is_abstract="abstract" in modifiers,
            is_final="final" in modifiers,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug(f"Failed to extract method info: {e}")
        return None
    except Exception as e:
        log_error(f"Unexpected error in method extraction: {e}")
        return None


# Extract elements from AST: extract_java_field
def extract_java_field(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_field_declaration: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    extract_javadoc: Callable,
) -> list[Variable]:
    """Extract Java field declarations."""
    fields: list[Variable] = []
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        field_info = parse_field_declaration(node)
        if not field_info:
            return fields

        field_type, variable_names, modifiers = field_info
        visibility = determine_visibility(modifiers)

        field_annotations = find_annotations_for_line(start_line)
        field_javadoc = extract_javadoc(start_line)

        for var_name in variable_names:
            start_line_idx = max(0, start_line - 1)
            end_line_idx = min(len(content_lines), end_line)
            raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

            field = Variable(
                name=var_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="java",
                variable_type=field_type,
                modifiers=modifiers,
                is_static="static" in modifiers,
                is_constant="final" in modifiers,
                visibility=visibility,
                docstring=field_javadoc,
                annotations=field_annotations,
                is_final="final" in modifiers,
                field_type=field_type,
            )
            fields.append(field)
    except (AttributeError, ValueError, TypeError) as e:
        log_debug(f"Failed to extract field info: {e}")
    except Exception as e:
        log_error(f"Unexpected error in field extraction: {e}")

    return fields


