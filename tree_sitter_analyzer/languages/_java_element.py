"""Java Code Element construction helpers."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Package, Variable

_CLASS_TYPE_MAP = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    # Theme-I (2026-06-10): record / annotation-type containers.
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
    # Modern Java (2026-09-01): anonymous classes created via new Foo() { ... }.
    "anonymous_class_body": "anonymous",
}

# Modifier keywords recognised in Java declarations.
_JAVA_MODIFIER_KEYWORDS = frozenset(
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


# ---------------------------------------------------------------------------
# AST-based JavaDoc helper (Step 7)
# ---------------------------------------------------------------------------


def _extract_javadoc_from_node(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Try to extract a JavaDoc comment from the preceding AST sibling.

    Walks backwards through the direct siblings of *node* looking for a
    ``block_comment`` whose text starts with ``/**``.  Stops as soon as a
    non-comment, non-line-comment sibling is found so that unrelated block
    comments are not mistakenly attributed.

    Returns the raw comment text or ``None`` if no JavaDoc sibling exists.
    """
    try:
        prev = node.prev_sibling
        while prev is not None:
            if prev.type == "block_comment":
                text = get_node_text(prev)
                if text.strip().startswith("/**"):
                    return text
                # A plain /* ... */ comment — not a JavaDoc; stop searching.
                return None
            elif prev.type == "line_comment":
                # Skip over single-line comments and keep searching.
                prev = prev.prev_sibling
                continue
            else:
                # Some other sibling (e.g. another declaration) — stop.
                return None
        return None
    except Exception:
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
            docstring=_extract_javadoc_from_node(node, get_node_text),
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
        docstring = _extract_javadoc_from_node(node, get_node_text)
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
# New node-type extractors (Step 8, 2026-09-01)
# ---------------------------------------------------------------------------


def extract_lambda_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Function | None:
    """Extract a ``lambda_expression`` node as a :class:`Function` element.

    The synthetic name ``"<lambda>"`` is used because the variable the lambda
    is assigned to is not unique (the same lambda can be re-assigned) and is
    not available from the lambda node itself.
    """
    try:
        start_line, end_line = _node_line_span(node)
        parameters = _extract_lambda_parameters(node, get_node_text)
        return Function(
            name="<lambda>",
            start_line=start_line,
            end_line=end_line,
            raw_text=_raw_text_for_span(content_lines, start_line, end_line),
            language="java",
            parameters=parameters,
            return_type=None,
            modifiers=[],
            is_method=True,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug_func(f"Failed to extract lambda: {e}")
        return None
    except Exception as e:
        log_error_func(f"Unexpected error in lambda extraction: {e}")
        return None


def extract_static_initializer(
    node: Any,
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Function | None:
    """Extract a ``static_initializer`` node as a :class:`Function` element.

    When multiple static initializers exist in a class, all receive the name
    ``"<static_initializer>"``; callers can distinguish them by ``start_line``.
    """
    try:
        start_line, end_line = _node_line_span(node)
        return Function(
            name="<static_initializer>",
            start_line=start_line,
            end_line=end_line,
            raw_text=_raw_text_for_span(content_lines, start_line, end_line),
            language="java",
            modifiers=["static"],
            is_static=True,
            is_method=True,
        )
    except Exception as e:
        log_error_func(f"Failed to extract static_initializer: {e}")
        return None


def extract_anonymous_class(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    current_package: str,
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Class | None:
    """Extract an ``anonymous_class_body`` as a :class:`Class` element.

    The synthetic class name ``"<anonymous>"`` is used for all anonymous
    classes; the ``class_type`` is set to ``"anonymous"`` for easy filtering.
    """
    try:
        start_line, end_line = _node_line_span(node)
        return _build_java_class(
            node,
            "<anonymous>",
            start_line,
            end_line,
            _raw_text_for_span(content_lines, start_line, end_line),
            _qualified_class_name(current_package, "<anonymous>"),
            current_package,
            None,   # extends_class
            [],     # implements_interfaces
            [],     # modifiers
            "package",  # visibility
            [],     # annotations
            True,   # is_nested (always true for anonymous classes)
            None,   # parent_class
            # Explicit override: tree-sitter-java 0.23.5 represents anonymous
            # class bodies as class_body (inside object_creation_expression)
            # rather than a distinct anonymous_class_body node type, so we
            # cannot rely on _CLASS_TYPE_MAP for the correct class_type.
            class_type="anonymous",
        )
    except Exception as e:
        log_error_func(f"Failed to extract anonymous class: {e}")
        return None


def extract_compact_constructor(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
    log_error_func: Callable[[str], None] = lambda _: None,
) -> Function | None:
    """Extract a ``compact_constructor_declaration`` (Java 16+ record).

    Compact constructors have no ``formal_parameters`` — the parameters come
    from the enclosing record header.  ``is_constructor`` is set to ``True``.
    """
    try:
        start_line, end_line = _node_line_span(node)
        ctor_name = _extract_identifier(node, get_node_text)
        if not ctor_name:
            return None

        modifiers = _extract_inline_modifiers(node, get_node_text)
        return Function(
            name=ctor_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_raw_text_for_span(content_lines, start_line, end_line),
            language="java",
            parameters=[],
            return_type="void",
            modifiers=modifiers,
            is_constructor=True,
            is_static="static" in modifiers,
            is_private="private" in modifiers,
            is_public="public" in modifiers,
            visibility=_determine_visibility_inline(modifiers),
            docstring=_extract_javadoc_from_node(node, get_node_text),
            annotations=_extract_node_annotations(node, get_node_text),
            throws=[],
            complexity_score=1,
            is_abstract=False,
            is_final=False,
            is_method=True,
        )
    except (AttributeError, ValueError, TypeError) as e:
        log_debug_func(f"Failed to extract compact_constructor: {e}")
        return None
    except Exception as e:
        log_error_func(f"Unexpected error in compact_constructor extraction: {e}")
        return None


def extract_module_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    *,
    log_debug_func: Callable[[str], None] = lambda _: None,
) -> Package | None:
    """Extract a ``module_declaration`` node as a :class:`Package` element."""
    try:
        start_line, end_line = _node_line_span(node)
        module_name: str | None = None
        for child in node.children:
            if child.type in ("identifier", "scoped_identifier"):
                module_name = get_node_text(child)
                break
        if not module_name:
            return None
        return Package(
            name=module_name,
            start_line=start_line,
            end_line=end_line,
            language="java",
        )
    except Exception as e:
        log_debug_func(f"Failed to extract module_declaration: {e}")
        return None


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


def _extract_lambda_parameters(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """Extract parameter texts from a ``lambda_expression`` node.

    Handles all three Java lambda parameter forms:
    - ``(x, y) -> ...``  — parenthesised inferred parameters
      (tree-sitter-java 0.23.5: ``inferred_parameters``;
       older grammars: ``inferred_formal_parameters``)
    - ``(Type x, int y) -> ...``  — typed formal parameters
    - ``x -> ...``  — single inferred parameter without parentheses
    """
    for child in node.children:
        if child.type in ("inferred_parameters", "inferred_formal_parameters"):
            # (x, y) -> ...  or  (x) -> ...
            return [
                get_node_text(p)
                for p in child.children
                if p.type == "identifier"
            ]
        if child.type == "formal_parameters":
            # (String x, int y) -> ...
            return [
                get_node_text(p)
                for p in child.children
                if p.type == "formal_parameter"
            ]
        if child.type == "identifier":
            # x -> ...  (single inferred parameter without parentheses)
            return [get_node_text(child)]
    return []


def _extract_inline_modifiers(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """Extract modifier keyword strings from a declaration node's modifiers child."""
    for child in node.children:
        if child.type == "modifiers":
            return [
                get_node_text(gc)
                for gc in child.children
                if get_node_text(gc) in _JAVA_MODIFIER_KEYWORDS
            ]
    return []


def _determine_visibility_inline(modifiers: list[str]) -> str:
    """Simple visibility determination without external dependency."""
    if "public" in modifiers:
        return "public"
    if "private" in modifiers:
        return "private"
    if "protected" in modifiers:
        return "protected"
    return "package"


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
    *,
    docstring: str | None = None,
    class_type: str | None = None,
) -> Class:
    return Class(
        name=class_name,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language="java",
        class_type=class_type if class_type is not None else _CLASS_TYPE_MAP.get(node.type, "class"),
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
        docstring=docstring,
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
