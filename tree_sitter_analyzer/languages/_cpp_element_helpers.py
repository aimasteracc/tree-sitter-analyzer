"""C++ Function and Class model builders."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..models import Class, Function
from ..utils import log_debug, log_error


@dataclass(frozen=True)
class CppFunctionExtractionContext:
    content_lines: list[str]
    parse_function_signature: Callable[
        [Any], tuple[str, str, list[str], list[str]] | None
    ]
    calculate_complexity: Callable[[Any], int]
    is_global_scope: Callable[[Any], bool]
    determine_visibility: Callable[..., str]
    extract_comment_for_line: Callable[[int], str | None]


@dataclass(frozen=True)
class CppClassExtractionContext:
    get_node_text: Callable[..., str]
    content_lines: list[str]
    current_namespace: str
    extract_base_classes: Callable[[Any], list[str]]
    extract_comment_for_line: Callable[[int], str | None]


_CPP_CLASS_NODE_TYPES = frozenset({"class_specifier", "struct_specifier"})
_CPP_CLASS_PARENT_WALK_LIMIT = 12
_CPP_NAMESPACE_PARENT_WALK_LIMIT = 16
_CPP_NAMESPACE_NAME_NODE_TYPES = frozenset(
    {"namespace_identifier", "nested_namespace_specifier", "identifier"}
)


def _cpp_containing_class_name(node: Any) -> str | None:
    """Walk the parent chain (capped) to find the enclosing C++ class name.

    Returns the ``type_identifier`` text of the nearest ``class_specifier``
    or ``struct_specifier`` ancestor, or ``None`` when the function is not
    inside a class body.  The depth cap prevents infinite walks on mocked
    or malformed nodes.
    """
    current = getattr(node, "parent", None)
    depth = 0
    while current is not None and depth < _CPP_CLASS_PARENT_WALK_LIMIT:
        if getattr(current, "type", "") in _CPP_CLASS_NODE_TYPES:
            for child in getattr(current, "children", ()):
                if getattr(child, "type", "") == "type_identifier":
                    text = getattr(child, "text", b"")
                    if isinstance(text, bytes):
                        return text.decode("utf-8", errors="replace")
                    return str(text)
            return None
        current = getattr(current, "parent", None)
        depth += 1
    return None


def _is_cpp_constructor(name: str, node: Any, qualifier: str | None = None) -> bool:
    """Return True when ``name`` matches the enclosing class name (constructor).

    Destructor names start with ``~``, so ``~Rectangle != Rectangle`` → False.
    For qualified out-of-class definitions (#590) the owner comes from the
    declarator (``math::Foo::Foo``), not the parent chain — the constructor
    test is then ``qualifier tail == name``.
    """
    if not name or name.startswith("~"):
        return False
    if qualifier is not None:
        return qualifier.rsplit("::", 1)[-1] == name
    class_name = _cpp_containing_class_name(node)
    return class_name is not None and name == class_name


def _cpp_namespace_name(ns_node: Any) -> str | None:
    """Name of a ``namespace_definition`` node (None for anonymous namespaces)."""
    for child in getattr(ns_node, "children", ()):
        if getattr(child, "type", "") in _CPP_NAMESPACE_NAME_NODE_TYPES:
            text = getattr(child, "text", b"")
            if isinstance(text, bytes):
                return text.decode("utf-8", errors="replace")
            return str(text)
    return None


def _cpp_enclosing_namespace(node: Any) -> str | None:
    """Join enclosing namespace names outer→inner (``a::b``), or None.

    Walks the parent chain with a depth cap (same MagicMock/malformed-node
    rationale as ``_cpp_containing_class_name``).
    """
    parts: list[str] = []
    current = getattr(node, "parent", None)
    depth = 0
    while current is not None and depth < _CPP_NAMESPACE_PARENT_WALK_LIMIT:
        if getattr(current, "type", "") == "namespace_definition":
            name = _cpp_namespace_name(current)
            if name:
                parts.append(name)
        current = getattr(current, "parent", None)
        depth += 1
    if not parts:
        return None
    return "::".join(reversed(parts))


def _cpp_split_qualified_name(name: str) -> tuple[str | None, str]:
    """Split ``math::Foo::bar`` → (``math::Foo``, ``bar``).

    Conversion-operator names (``operator std::string``) are never split —
    their ``::`` belongs to the cast-target type, not an owner qualifier.
    """
    if "::" in name and not name.startswith("operator "):
        qualifier, bare = name.rsplit("::", 1)
        return qualifier, bare
    return None, name


def _cpp_receiver_type(node: Any, qualifier: str | None) -> str | None:
    """Owner of a function: declarator qualifier + enclosing namespaces (#590).

    In-class members keep ``None`` — their owner already travels through the
    class section nesting (existing convention), so a namespace-only receiver
    (``math`` for a method of ``math::Foo``) would be misleading.
    """
    if _cpp_containing_class_name(node) is not None:
        return qualifier
    namespace = _cpp_enclosing_namespace(node)
    if not namespace:
        return qualifier
    return f"{namespace}::{qualifier}" if qualifier else namespace


def extract_cpp_function(
    node: Any,
    context: CppFunctionExtractionContext | Callable[..., str],
    *legacy_args: Any,
) -> Function | None:
    """Extract a C++ function definition."""
    try:
        ctx = _function_context(context, *legacy_args)
        function_info = ctx.parse_function_signature(node)
        if not function_info:
            return None

        name, return_type, parameters, modifiers = function_info
        # #590: names stay bare, the owner travels in receiver_type (same
        # convention as Go/Rust receivers #429/#474). ``int math::max(...)``
        # outside the namespace block and ``int max(...)`` inside it converge
        # to the same representation: name="max", receiver_type="math".
        qualifier, name = _cpp_split_qualified_name(name)
        receiver_type = _cpp_receiver_type(node, qualifier)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        is_global = ctx.is_global_scope(node)
        visibility = ctx.determine_visibility(modifiers, is_global=is_global, node=node)

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_source_slice(ctx.content_lines, start_line, end_line),
            language="cpp",
            parameters=parameters,
            return_type=return_type or "void",
            modifiers=modifiers,
            is_static="static" in modifiers,
            is_private="private" in modifiers,
            is_public="public" in modifiers,
            visibility=visibility,
            docstring=ctx.extract_comment_for_line(start_line),
            complexity_score=ctx.calculate_complexity(node),
            is_constructor=_is_cpp_constructor(name, node, qualifier),
            receiver_type=receiver_type,
        )
    except (AttributeError, ValueError, TypeError) as exc:
        log_debug(f"Failed to extract function info: {exc}")
        return None
    except Exception as exc:
        log_error(f"Unexpected error in function extraction: {exc}")
        return None


def extract_cpp_class(
    node: Any,
    context: CppClassExtractionContext | Callable[..., str],
    *legacy_args: Any,
) -> Class | None:
    """Extract C++ class, struct, or union information."""
    try:
        ctx = _class_context(context, *legacy_args)
        class_name, superclasses = _class_parts(
            node, ctx.get_node_text, ctx.extract_base_classes
        )
        if not class_name:
            return None

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        full_qualified_name = (
            f"{ctx.current_namespace}::{class_name}"
            if ctx.current_namespace
            else class_name
        )

        return Class(
            name=class_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_source_slice(ctx.content_lines, start_line, end_line),
            language="cpp",
            class_type="class",
            full_qualified_name=full_qualified_name,
            package_name=ctx.current_namespace,
            superclass=superclasses[0] if superclasses else None,
            interfaces=superclasses[1:] if len(superclasses) > 1 else [],
            modifiers=[],
            docstring=ctx.extract_comment_for_line(start_line),
        )
    except Exception as exc:
        log_debug(f"Failed to extract class info: {exc}")
        return None


def _function_context(
    context: CppFunctionExtractionContext | Callable[..., str],
    *legacy_args: Any,
) -> CppFunctionExtractionContext:
    if isinstance(context, CppFunctionExtractionContext):
        return context
    if len(legacy_args) != 7:
        raise TypeError("Expected CppFunctionExtractionContext or legacy arguments")
    return CppFunctionExtractionContext(
        content_lines=legacy_args[0],
        parse_function_signature=legacy_args[2],
        calculate_complexity=legacy_args[3],
        is_global_scope=legacy_args[4],
        determine_visibility=legacy_args[5],
        extract_comment_for_line=legacy_args[6],
    )


def _class_context(
    context: CppClassExtractionContext | Callable[..., str],
    *legacy_args: Any,
) -> CppClassExtractionContext:
    if isinstance(context, CppClassExtractionContext):
        return context
    if len(legacy_args) != 4:
        raise TypeError("Expected CppClassExtractionContext or legacy arguments")
    return CppClassExtractionContext(
        get_node_text=context,
        content_lines=legacy_args[0],
        current_namespace=legacy_args[1],
        extract_base_classes=legacy_args[2],
        extract_comment_for_line=legacy_args[3],
    )


def _class_parts(
    node: Any,
    get_node_text: Callable[..., str],
    extract_base_classes: Callable,
) -> tuple[str | None, list[str]]:
    class_name = None
    superclasses: list[str] = []
    for child in node.children:
        if child.type == "type_identifier":
            class_name = get_node_text(child)
        elif child.type == "base_class_clause":
            superclasses = extract_base_classes(child)
    return class_name, superclasses


def _source_slice(content_lines: list[str], start_line: int, end_line: int) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])
