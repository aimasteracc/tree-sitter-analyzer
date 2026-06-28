"""Class-like element extraction helpers for the TypeScript extractor."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

from ...models import Class
from ...utils import log_debug
from ..shared.traversal import node_range

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
GenericsExtractor: TypeAlias = Callable[["tree_sitter.Node"], list[str]]
TsdocExtractor: TypeAlias = Callable[[int], str | None]
ComponentPredicate: TypeAlias = Callable[["tree_sitter.Node", str], bool]
ExportPredicate: TypeAlias = Callable[[str], bool]


@dataclass
class _ClassParts:
    name: str | None = None
    superclass: str | None = None
    interfaces: list[str] = field(default_factory=list)
    is_abstract: bool = False


@dataclass
class _InterfaceParts:
    name: str | None = None
    interfaces: list[str] = field(default_factory=list)


def _extract_decorator_names(node: tree_sitter.Node) -> list[str]:
    """Return decorator names (without '@') from direct decorator children of *node*.

    Handles both bare decorators (``@Singleton``) and call-expression decorators
    (``@Injectable()``).  Only direct ``decorator`` children are inspected so
    that decorators on nested constructs are not double-counted.
    """
    names: list[str] = []
    for child in node.children:
        if child.type == "decorator":
            for grandchild in child.children:
                if grandchild.type == "identifier":
                    text = grandchild.text
                    if text:
                        names.append(
                            text.decode("utf-8") if isinstance(text, bytes) else text
                        )
                    break
                elif grandchild.type == "call_expression":
                    for ggc in grandchild.children:
                        if ggc.type == "identifier":
                            text = ggc.text
                            if text:
                                names.append(
                                    text.decode("utf-8")
                                    if isinstance(text, bytes)
                                    else text
                                )
                        break
                    break
    return names


def _extract_preceding_decorator_names(node: tree_sitter.Node) -> list[str]:
    """Return decorator names that appear as siblings immediately before *node*.

    For method decorators the tree-sitter grammar places ``decorator`` nodes
    as siblings in the enclosing ``class_body``, not as children of the
    ``method_definition`` itself.  We walk backwards from *node* through its
    parent's children, collecting consecutive ``decorator`` siblings.
    """
    parent = node.parent
    if parent is None:
        return []

    children = parent.children
    try:
        idx = children.index(node)
    except ValueError:
        return []

    names: list[str] = []
    for sibling in reversed(children[:idx]):
        if sibling.type != "decorator":
            break
        for child in sibling.children:
            if child.type == "identifier":
                text = child.text
                if text:
                    names.insert(
                        0,
                        text.decode("utf-8") if isinstance(text, bytes) else text,
                    )
                break
            elif child.type == "call_expression":
                for ggc in child.children:
                    if ggc.type == "identifier":
                        text = ggc.text
                        if text:
                            names.insert(
                                0,
                                text.decode("utf-8")
                                if isinstance(text, bytes)
                                else text,
                            )
                    break
                break
    return names


def extract_class(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_generics: GenericsExtractor,
    extract_tsdoc: TsdocExtractor,
    is_framework_component: ComponentPredicate,
    is_exported_class: ExportPredicate,
    framework_type: str,
) -> Class | None:
    """Extract class information with detailed metadata."""
    try:
        start_line, end_line = node_range(node)
        parts = _parse_class_parts(node, get_node_text, extract_generics)

        if not parts.name:
            return None

        return Class(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            class_type="abstract_class" if parts.is_abstract else "class",
            superclass=parts.superclass,
            interfaces=parts.interfaces,
            docstring=extract_tsdoc(start_line),
            is_react_component=is_framework_component(node, parts.name),
            framework_type=framework_type,
            is_exported=is_exported_class(parts.name),
            is_abstract=parts.is_abstract,
            decorators=_extract_decorator_names(node),
        )
    except Exception as e:
        log_debug(f"Failed to extract class info: {e}")
        return None


def extract_interface(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_generics: GenericsExtractor,
    extract_tsdoc: TsdocExtractor,
    is_exported_class: ExportPredicate,
    framework_type: str,
) -> Class | None:
    """Extract interface information."""
    try:
        start_line, end_line = node_range(node)
        parts = _parse_interface_parts(node, get_node_text, extract_generics)

        if not parts.name:
            return None

        return Class(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            class_type="interface",
            interfaces=parts.interfaces,
            docstring=extract_tsdoc(start_line),
            framework_type=framework_type,
            is_exported=is_exported_class(parts.name),
        )
    except Exception as e:
        log_debug(f"Failed to extract interface info: {e}")
        return None


def extract_type_alias(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_generics: GenericsExtractor,
    extract_tsdoc: TsdocExtractor,
    is_exported_class: ExportPredicate,
    framework_type: str,
) -> Class | None:
    """Extract type alias information."""
    try:
        start_line, end_line = node_range(node)

        type_name = None
        for child in node.children:
            if child.type == "type_identifier":
                type_name = child.text.decode("utf8") if child.text else None
            elif child.type == "type_parameters":
                extract_generics(child)

        if not type_name:
            return None

        return Class(
            name=type_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            class_type="type",
            docstring=extract_tsdoc(start_line),
            framework_type=framework_type,
            is_exported=is_exported_class(type_name),
        )
    except Exception as e:
        log_debug(f"Failed to extract type alias info: {e}")
        return None


def extract_enum(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_tsdoc: TsdocExtractor,
    is_exported_class: ExportPredicate,
    framework_type: str,
) -> Class | None:
    """Extract enum information."""
    try:
        start_line, end_line = node_range(node)

        enum_name = None
        for child in node.children:
            if child.type == "identifier":
                enum_name = child.text.decode("utf8") if child.text else None

        if not enum_name:
            return None

        return Class(
            name=enum_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            class_type="enum",
            docstring=extract_tsdoc(start_line),
            framework_type=framework_type,
            is_exported=is_exported_class(enum_name),
        )
    except Exception as e:
        log_debug(f"Failed to extract enum info: {e}")
        return None


def extract_namespace(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_tsdoc: TsdocExtractor,
    is_exported_class: ExportPredicate,
    framework_type: str,
) -> Class | None:
    """Extract a ``namespace X { ... }`` / ``module Y { ... }`` container.

    Theme-I (2026-06-10): ``namespace`` parses as ``internal_module`` (inside
    an ``expression_statement``) and ``module`` as a ``module`` node; both
    carry their name as an ``identifier`` child (or ``string`` for ambient
    ``declare module "name"``). Surfaced as ``class_type="namespace"`` so
    outlines show the container the way they show classes/enums.
    """
    try:
        start_line, end_line = node_range(node)

        ns_name = None
        for child in node.children:
            if child.type in ("identifier", "nested_identifier", "string"):
                ns_name = child.text.decode("utf8") if child.text else None
                break

        if not ns_name:
            return None

        return Class(
            name=ns_name.strip("\"'"),
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            class_type="namespace",
            docstring=extract_tsdoc(start_line),
            framework_type=framework_type,
            is_exported=is_exported_class(ns_name),
        )
    except Exception as e:
        log_debug(f"Failed to extract namespace info: {e}")
        return None


def _parse_class_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_generics: GenericsExtractor,
) -> _ClassParts:
    parts = _ClassParts(is_abstract=node.type == "abstract_class_declaration")

    for child in node.children:
        if child.type == "type_identifier":
            parts.name = child.text.decode("utf8") if child.text else None
        elif child.type == "class_heritage":
            parts.superclass, parts.interfaces = _parse_class_heritage(
                get_node_text(child)
            )
        elif child.type == "type_parameters":
            extract_generics(child)

    return parts


def _parse_interface_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_generics: GenericsExtractor,
) -> _InterfaceParts:
    parts = _InterfaceParts()

    for child in node.children:
        if child.type == "type_identifier":
            parts.name = child.text.decode("utf8") if child.text else None
        elif child.type == "extends_clause":
            parts.interfaces = _parse_extends_clause(get_node_text(child))
        elif child.type == "type_parameters":
            extract_generics(child)

    return parts


def _parse_class_heritage(heritage_text: str) -> tuple[str | None, list[str]]:
    superclass = None
    extends_match = re.search(r"extends\s+(\w+)", heritage_text)
    if extends_match:
        superclass = extends_match.group(1)

    interfaces = []
    implements_matches = re.findall(r"implements\s+([\w,\s]+)", heritage_text)
    if implements_matches:
        interfaces = [iface.strip() for iface in implements_matches[0].split(",")]

    return superclass, interfaces


def _parse_extends_clause(extends_text: str) -> list[str]:
    extends_matches = re.findall(r"extends\s+([\w,\s]+)", extends_text)
    if not extends_matches:
        return []
    return [iface.strip() for iface in extends_matches[0].split(",")]
