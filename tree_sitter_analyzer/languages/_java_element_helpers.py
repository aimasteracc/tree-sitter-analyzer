"""Java Code Element construction helpers."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Variable

_CLASS_TYPE_MAP = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    # Theme-I (2026-06-10): record / annotation-type containers.
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}


def extract_javadoc_for_line(
    line: int,
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None],
) -> str | None:
    """Extract JavaDoc comment for a specific line."""
    try:
        search_start = max(0, line - 10)
        search_end = min(len(content_lines), line)
        for index in range(search_start, search_end):
            if content_lines[index].strip().startswith("/**"):
                return _collect_javadoc(content_lines, index, search_end)
    except Exception as e:
        log_debug_func(f"Failed to extract JavaDoc: {e}")
    return None


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
    *,
    log_debug_func: Callable[[str], None],
    log_error_func: Callable[[str], None],
) -> Class | None:
    """Extract Java class/interface/enum information."""
    try:
        start_line, end_line = _node_line_span(node)
        class_name = _extract_identifier(node, get_node_text)
        if not class_name:
            return None

        extends_class, implements_interfaces = _extract_class_relationships(
            node, get_node_text
        )
        modifiers = extract_modifiers(node)
        is_nested = is_nested_class(node)
        return _build_java_class(
            node,
            class_name,
            start_line,
            end_line,
            _raw_text_for_span(content_lines, start_line, end_line),
            _qualified_class_name(current_package, class_name),
            current_package,
            extends_class,
            implements_interfaces,
            modifiers,
            determine_visibility(modifiers),
            _extract_node_annotations(node, get_node_text),
            is_nested,
            find_parent_class(node) if is_nested else None,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug_func(f"Failed to extract class info: {e}")
        return None
    except Exception as e:
        log_error_func(f"Unexpected error in class extraction: {e}")
        return None


def extract_java_method(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_method_signature: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    calculate_complexity: Callable,
    extract_javadoc: Callable,
    *,
    log_debug_func: Callable[[str], None],
    log_error_func: Callable[[str], None],
) -> Function | None:
    """Extract Java method/constructor information."""
    try:
        start_line, end_line = _node_line_span(node)
        method_info = parse_method_signature(node)
        if not method_info:
            return None

        method_name, return_type, parameters, modifiers, throws = method_info
        is_constructor = node.type == "constructor_declaration"
        return Function(
            name=method_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_raw_text_for_span(content_lines, start_line, end_line),
            language="java",
            parameters=parameters,
            return_type=return_type if not is_constructor else "void",
            modifiers=modifiers,
            is_static="static" in modifiers,
            is_private="private" in modifiers,
            is_public="public" in modifiers,
            is_constructor=is_constructor,
            visibility=determine_visibility(modifiers),
            docstring=extract_javadoc(start_line),
            annotations=find_annotations_for_line(start_line),
            throws=throws,
            complexity_score=calculate_complexity(node),
            is_abstract="abstract" in modifiers,
            is_final="final" in modifiers,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug_func(f"Failed to extract method info: {e}")
        return None
    except Exception as e:
        log_error_func(f"Unexpected error in method extraction: {e}")
        return None


def extract_java_field(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_field_declaration: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    extract_javadoc: Callable,
    *,
    log_debug_func: Callable[[str], None],
    log_error_func: Callable[[str], None],
) -> list[Variable]:
    """Extract Java field declarations."""
    fields: list[Variable] = []
    try:
        start_line, end_line = _node_line_span(node)
        field_info = parse_field_declaration(node)
        if not field_info:
            return fields

        field_type, variable_names, modifiers = field_info
        raw_text = _raw_text_for_span(content_lines, start_line, end_line)
        visibility = determine_visibility(modifiers)
        annotations = find_annotations_for_line(start_line)
        javadoc = extract_javadoc(start_line)

        fields.extend(
            _build_java_fields(
                variable_names,
                start_line,
                end_line,
                raw_text,
                field_type,
                modifiers,
                visibility,
                annotations,
                javadoc,
            )
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug_func(f"Failed to extract field info: {e}")
    except Exception as e:
        log_error_func(f"Unexpected error in field extraction: {e}")

    return fields


def _collect_javadoc(
    content_lines: list[str],
    start_index: int,
    end_index: int,
) -> str:
    javadoc_lines = []
    for index in range(start_index, end_index):
        doc_line = content_lines[index].strip()
        javadoc_lines.append(doc_line)
        if doc_line.endswith("*/"):
            break
    return "\n".join(javadoc_lines)


def _node_line_span(node: Any) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


_ANNOTATION_NODE_TYPES = frozenset({"annotation", "marker_annotation"})


def _extract_node_annotations(
    node: Any, get_node_text: Callable[..., str]
) -> list[dict[str, Any]]:
    """Extract annotations directly from a node's modifiers subtree.

    Reads only the direct ``modifiers`` child of *node* — so only annotations
    that actually belong to this declaration are returned, not annotations that
    happen to be nearby (which the proximity-based fallback can confuse).
    """
    annotations: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "modifiers":
            continue
        for modifier in child.children:
            if modifier.type not in _ANNOTATION_NODE_TYPES:
                continue
            ann_text = get_node_text(modifier)
            ann_name = None
            for sub in modifier.children:
                if sub.type == "identifier":
                    ann_name = get_node_text(sub)
                    break
            if not ann_name:
                import re as _re

                m = _re.search(r"@(\w+)", ann_text)
                if m:
                    ann_name = m.group(1)
            if ann_name:
                annotations.append(
                    {
                        "name": ann_name,
                        "line": modifier.start_point[0] + 1,
                        "text": ann_text,
                        "type": "annotation",
                    }
                )
        break  # only one modifiers child per declaration
    return annotations


def _extract_identifier(node: Any, get_node_text: Callable[..., str]) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            return get_node_text(child)
    return None


def _split_respecting_generics(text: str) -> list[str]:
    """Split a comma-separated interface list while preserving generic type arguments.

    'LocalCache<K, V>, Runnable' → ['LocalCache<K, V>', 'Runnable']
    Naive re.findall(r'\\b[A-Z]\\w*') would split '<K, V>' into separate items.
    """
    depth = 0
    current: list[str] = []
    parts: list[str] = []
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
        else:
            current.append(ch)
    token = "".join(current).strip()
    if token:
        parts.append(token)
    # Each part may still contain leading 'implements ' keyword text from the node;
    # strip everything before the first capital-letter word start.
    result = []
    for part in parts:
        m = re.search(r"[A-Z]\w*.*", part, re.DOTALL)
        if m:
            result.append(m.group(0).strip())
    return result


def _extract_class_relationships(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, list[str]]:
    extends_class = None
    implements_interfaces: list[str] = []
    for child in node.children:
        if child.type == "superclass":
            extends_class = _extract_superclass(child, get_node_text)
        elif child.type == "super_interfaces":
            raw = get_node_text(child)
            # Strip the leading 'implements' keyword before splitting.
            body = re.sub(r"^\s*implements\s*", "", raw)
            implements_interfaces = _split_respecting_generics(body)
        elif child.type == "extends_interfaces":
            # interface Foo extends Bar, Baz<T> — uses extends_interfaces node,
            # not super_interfaces. Store in implements_interfaces so callers
            # find all extended types in one place regardless of class/interface.
            raw = get_node_text(child)
            body = re.sub(r"^\s*extends\s*", "", raw)
            implements_interfaces = _split_respecting_generics(body)
    return extends_class, implements_interfaces


def _extract_superclass(node: Any, get_node_text: Callable[..., str]) -> str | None:
    match = re.search(r"\b[A-Z]\w*", get_node_text(node))
    return match.group(0) if match else None


def _qualified_class_name(package_name: str, class_name: str) -> str:
    return f"{package_name}.{class_name}" if package_name else class_name


def _raw_text_for_span(
    content_lines: list[str],
    start_line: int,
    end_line: int,
) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])


def _build_java_class(
    node: Any,
    class_name: str,
    start_line: int,
    end_line: int,
    raw_text: str,
    full_qualified_name: str,
    package_name: str,
    extends_class: str | None,
    implements_interfaces: list[str],
    modifiers: list[str],
    visibility: str,
    annotations: list[dict[str, Any]],
    is_nested: bool,
    parent_class: str | None,
) -> Class:
    return Class(
        name=class_name,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language="java",
        class_type=_CLASS_TYPE_MAP.get(node.type, "class"),
        full_qualified_name=full_qualified_name,
        package_name=package_name,
        superclass=extends_class,
        interfaces=implements_interfaces,
        modifiers=modifiers,
        visibility=visibility,
        annotations=annotations,
        is_nested=is_nested,
        parent_class=parent_class,
        extends_class=extends_class,
        implements_interfaces=implements_interfaces,
    )


def _build_java_fields(
    variable_names: list[str],
    start_line: int,
    end_line: int,
    raw_text: str,
    field_type: str,
    modifiers: list[str],
    visibility: str,
    annotations: list[dict[str, Any]],
    javadoc: str | None,
) -> list[Variable]:
    return [
        _build_java_field(
            var_name,
            start_line,
            end_line,
            raw_text,
            field_type,
            modifiers,
            visibility,
            annotations,
            javadoc,
        )
        for var_name in variable_names
    ]


def _build_java_field(
    var_name: str,
    start_line: int,
    end_line: int,
    raw_text: str,
    field_type: str,
    modifiers: list[str],
    visibility: str,
    annotations: list[dict[str, Any]],
    javadoc: str | None,
) -> Variable:
    return Variable(
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
        docstring=javadoc,
        annotations=annotations,
        is_final="final" in modifiers,
        field_type=field_type,
    )
