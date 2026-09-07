"""Java Code Element construction helpers."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Variable
from ._java_element_common import (
    _build_java_class,
    _extract_javadoc_from_node,
    _extract_node_annotations,
    _node_line_span,
    _qualified_class_name,
    _raw_text_for_span,
)
from ._java_modern import extract_compact_constructor


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
    docstring = _extract_javadoc_from_node(node, get_node_text)
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
            docstring=docstring,
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
    # 紧凑构造器的协议错误由插件边界报告，不进入旧方法路径的容错捕获。
    if node.type == "compact_constructor_declaration":
        constructor = extract_compact_constructor(
            node,
            get_node_text,
            content_lines,
            log_debug_func=log_debug_func,
            log_error_func=log_error_func,
        )
        constructor.complexity_score = calculate_complexity(node)
        return constructor
    docstring = _extract_javadoc_from_node(node, get_node_text)
    try:
        start_line, end_line = _node_line_span(node)
        method_info = parse_method_signature(node)
        if not method_info:
            return None

        method_name, return_type, parameters, modifiers, throws = method_info
        # Step 6 (2026-09-01): Use AST-based annotation extraction so only
        # annotations that truly belong to this declaration are attributed to it
        # (avoids proximity-based false positives).  ``find_annotations_for_line``
        # is kept as a parameter for backward-compatibility but is no longer called.
        annotations = _extract_node_annotations(node, get_node_text)
        # Step 7 (2026-09-01): Use AST sibling-based JavaDoc.
        # The line-scan heuristic is intentionally NOT used here: it searches
        # backwards up to 10 lines and therefore incorrectly attributes a
        # preceding method's JavaDoc to the next method when they are close
        # together.  The AST-based approach (prev_sibling block_comment) is
        # the authoritative source and covers all normal cases.
        # compact_constructor_declaration is also a constructor form (Java 16+ records).
        is_constructor = node.type in {
            "constructor_declaration",
            "compact_constructor_declaration",
        }
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
            docstring=docstring,
            annotations=annotations,
            throws=throws,
            complexity_score=calculate_complexity(node),
            is_abstract="abstract" in modifiers,
            is_final="final" in modifiers,
            is_method=True,
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
        # Step 6 (2026-09-01): AST-based annotations instead of proximity scan.
        annotations = _extract_node_annotations(node, get_node_text)
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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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
    # Each part may still contain leading keyword text from the node;
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
        elif child.type == "permits":
            # sealed class Foo permits Bar, Baz (Java 17+).
            # Store permitted subtypes in interfaces for discoverability.
            raw = get_node_text(child)
            body = re.sub(r"^\s*permits\s*", "", raw)
            permits_types = _split_respecting_generics(body)
            implements_interfaces.extend(permits_types)
    return extends_class, implements_interfaces


def _extract_superclass(node: Any, get_node_text: Callable[..., str]) -> str | None:
    match = re.search(r"\b[A-Z]\w*", get_node_text(node))
    return match.group(0) if match else None


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
