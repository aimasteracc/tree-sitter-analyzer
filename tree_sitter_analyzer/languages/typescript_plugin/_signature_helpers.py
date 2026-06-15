"""Signature parsing helpers for the TypeScript extractor."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
ParameterExtractor: TypeAlias = Callable[["tree_sitter.Node"], list[str]]
GenericsExtractor: TypeAlias = Callable[["tree_sitter.Node"], list[str]]
FunctionSignature: TypeAlias = tuple[
    str | None, list[str], bool, bool, str | None, list[str]
]
MethodSignature: TypeAlias = tuple[
    str | None,
    list[str],
    bool,
    bool,
    bool,
    bool,
    bool,
    str | None,
    str,
    list[str],
]


@dataclass
class _FunctionSignatureParts:
    name: str | None = None
    parameters: list[str] = field(default_factory=list)
    is_async: bool = False
    is_generator: bool = False
    return_type: str | None = None
    generics: list[str] = field(default_factory=list)

    def as_tuple(self) -> FunctionSignature:
        return (
            self.name,
            self.parameters,
            self.is_async,
            self.is_generator,
            self.return_type,
            self.generics,
        )


@dataclass
class _MethodSignatureParts:
    name: str | None = None
    parameters: list[str] = field(default_factory=list)
    is_async: bool = False
    is_static: bool = False
    is_getter: bool = False
    is_setter: bool = False
    is_constructor: bool = False
    return_type: str | None = None
    visibility: str = "public"
    generics: list[str] = field(default_factory=list)

    def as_tuple(self) -> MethodSignature:
        return (
            self.name,
            self.parameters,
            self.is_async,
            self.is_static,
            self.is_getter,
            self.is_setter,
            self.is_constructor,
            self.return_type,
            self.visibility,
            self.generics,
        )


def parse_function_signature(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
    extract_generics: GenericsExtractor,
) -> FunctionSignature | None:
    """Parse a TypeScript function signature."""
    try:
        node_text = get_node_text(node)
        parts = _FunctionSignatureParts(
            is_async="async" in node_text,
            is_generator=node.type == "generator_function_declaration",
        )

        for child in node.children:
            _apply_function_child(
                parts, child, get_node_text, extract_parameters, extract_generics
            )

        return parts.as_tuple()
    except Exception:
        return None


def parse_method_signature(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
    extract_generics: GenericsExtractor,
) -> MethodSignature | None:
    """Parse a TypeScript class or interface method signature."""
    try:
        node_text = get_node_text(node)
        parts = _MethodSignatureParts(
            is_async=_is_async_from_node(node),
            is_static=_is_static_from_node(node),
            visibility=_visibility_from_node(node),
        )

        for child in node.children:
            _apply_method_child(
                parts, child, get_node_text, extract_parameters, extract_generics
            )

        if parts.name is None:
            parts.name = _method_name_from_text(node_text)

        if parts.name:
            parts.is_constructor = parts.name == "constructor"

        parts.is_getter, parts.is_setter = _accessor_flags_from_text(node_text)

        return parts.as_tuple()
    except Exception:
        return None


def _apply_function_child(
    parts: _FunctionSignatureParts,
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
    extract_generics: GenericsExtractor,
) -> None:
    if child.type == "identifier":
        parts.name = child.text.decode("utf8") if child.text else None
    elif child.type == "formal_parameters":
        parts.parameters = extract_parameters(child)
    elif child.type == "type_annotation":
        parts.return_type = get_node_text(child).lstrip(": ")
    elif child.type == "type_parameters":
        parts.generics = extract_generics(child)


def _apply_method_child(
    parts: _MethodSignatureParts,
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
    extract_generics: GenericsExtractor,
) -> None:
    if child.type in ["property_identifier", "identifier"]:
        parts.name = _method_name_from_child(child, get_node_text)
        parts.is_constructor = parts.name == "constructor"
    elif child.type == "formal_parameters":
        parts.parameters = extract_parameters(child)
    elif child.type == "type_annotation":
        parts.return_type = get_node_text(child).lstrip(": ")
    elif child.type == "type_parameters":
        parts.generics = extract_generics(child)


def _visibility_from_node(node: tree_sitter.Node) -> str:
    """Read visibility from the ``accessibility_modifier`` AST child.

    Inspecting direct children avoids false positives from string literals,
    comments, or variable names in the method body that contain 'private'
    or 'protected' (#772).
    """
    for child in node.children:
        if child.type == "accessibility_modifier" and child.text:
            text = (
                child.text.decode("utf-8")
                if isinstance(child.text, bytes)
                else child.text
            )
            if "private" in text:
                return "private"
            if "protected" in text:
                return "protected"
            if "public" in text:
                return "public"
    return "public"


def _is_async_from_node(node: tree_sitter.Node) -> bool:
    """Check for ``async`` keyword as a direct AST child of the method node.

    Text search on the full node text causes false positives when the method
    body contains the word 'async' in a string literal, comment, or call
    expression (#774).
    """
    for child in node.children:
        if child.type == "async":
            return True
    return False


def _is_static_from_node(node: tree_sitter.Node) -> bool:
    """Check for ``static`` keyword as a direct AST child of the method node."""
    for child in node.children:
        if child.type == "static":
            return True
    return False


def _visibility_from_text(node_text: str) -> str:
    if "private" in node_text:
        return "private"
    if "protected" in node_text:
        return "protected"
    return "public"


def _accessor_flags_from_text(node_text: str) -> tuple[bool, bool]:
    if "get " in node_text:
        return True, False
    if "set " in node_text:
        return False, True
    return False, False


def _method_name_from_child(
    child: tree_sitter.Node, get_node_text: TextExtractor
) -> str | None:
    name = get_node_text(child)
    if name:
        return name

    if not hasattr(child, "text") or not child.text:
        return None

    if isinstance(child.text, bytes):
        return child.text.decode("utf-8")
    return str(child.text)


def _method_name_from_text(node_text: str) -> str | None:
    match = re.search(
        r"(?:async\s+)?(?:static\s+)?(?:public\s+|private\s+|protected\s+)?(\w+)\s*\(",
        node_text,
    )
    return match.group(1) if match else None
