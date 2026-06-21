"""Swift model element builders."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error
from ._swift_plugin_nodes import (
    base_element_fields,
    binding_kind,
    class_type,
    inherited_types,
    interfaces,
    modifier_words,
    named_child_text,
    superclass,
    type_annotation,
    type_name,
    variable_name,
    visibility,
)

if TYPE_CHECKING:
    import tree_sitter


# ---------------------------------------------------------------------------
# Cyclomatic complexity for Swift
# ---------------------------------------------------------------------------

# Non-leaf AST node types that each add one decision point.
# conjunction_expression / disjunction_expression are non-leaf container nodes
# (not bare && / || tokens), so the non-leaf check is redundant but harmless.
_SWIFT_DECISION_NODE_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "guard_statement",
        "switch_statement",
        "for_statement",
        "while_statement",
        "repeat_while_statement",
        "catch_block",
        "ternary_expression",
        "conjunction_expression",  # x && y
        "disjunction_expression",  # x || y
    }
)


def _safe_children(node: object) -> list[object]:
    """Return children list from a tree-sitter node, empty list on any error."""
    try:
        children = getattr(node, "children", None)
        if children is None:
            return []
        return list(children)
    except (TypeError, AttributeError):
        return []


def _swift_calculate_complexity(node: object) -> int:
    """Return cyclomatic complexity for a Swift function node.

    complexity = 1 + (number of decision points).

    Decision points are non-leaf AST nodes whose type is in
    _SWIFT_DECISION_NODE_TYPES (if/guard/switch/for/while/repeat-while/
    catch_block/ternary_expression/conjunction_expression/disjunction_expression).
    """
    decisions = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        children = _safe_children(cur)
        if getattr(cur, "type", None) in _SWIFT_DECISION_NODE_TYPES and children:
            decisions += 1
        stack.extend(children)
    return 1 + decisions


def extract_swift_function(extractor: Any, node: tree_sitter.Node) -> Function | None:
    """Extract one Swift function-like declaration."""
    try:
        raw_text = extractor.get_node_text(node)
        return _swift_function(
            node,
            raw_text,
            _function_name(extractor, node),
            modifier_words(node),
        )
    except Exception as e:
        log_error(f"Error extracting Swift function: {e}")
        return None


def extract_swift_class(extractor: Any, node: tree_sitter.Node) -> Class | None:
    """Extract one Swift type declaration."""
    try:
        raw_text = extractor.get_node_text(node)
        declaration_kind = class_type(node)
        return _swift_class(
            node,
            raw_text,
            type_name(extractor, node),
            declaration_kind,
            modifier_words(node),
        )
    except Exception as e:
        log_error(f"Error extracting Swift type declaration: {e}")
        return None


def extract_swift_variable(extractor: Any, node: tree_sitter.Node) -> Variable | None:
    """Extract one Swift property declaration."""
    try:
        raw_text = extractor.get_node_text(node)
        binding = binding_kind(node, raw_text)
        return _swift_variable(
            node,
            raw_text,
            variable_name(extractor, node),
            type_annotation(extractor, node),
            modifier_words(node),
            binding,
        )
    except Exception as e:
        log_error(f"Error extracting Swift variable: {e}")
        return None


def extract_swift_import(extractor: Any, node: tree_sitter.Node) -> Import | None:
    """Extract one Swift import declaration."""
    try:
        raw_text = extractor.get_node_text(node)
        module_path = _import_module_path(raw_text)
        return Import(**_swift_import_fields(node, raw_text, module_path))
    except Exception as e:
        log_error(f"Error extracting Swift import: {e}")
        return None


def _function_name(extractor: Any, node: tree_sitter.Node) -> str:
    if node.type == "init_declaration":
        return "init"
    return named_child_text(extractor, node, ("simple_identifier", "identifier"))


def _swift_function(
    node: tree_sitter.Node,
    raw_text: str,
    name: str,
    modifiers: list[str],
) -> Function:
    found_visibility = visibility(modifiers)
    fields = base_element_fields(node, raw_text, name)
    fields.update(_swift_function_fields(node, raw_text, modifiers, found_visibility))
    return Function(**fields)


def _swift_function_fields(
    node: tree_sitter.Node,
    raw_text: str,
    modifiers: list[str],
    found_visibility: str,
) -> dict[str, Any]:
    return {
        "parameters": _parameter_names(raw_text),
        "return_type": _return_type(raw_text),
        "modifiers": modifiers,
        "visibility": found_visibility,
        "is_constructor": node.type == "init_declaration",
        "complexity_score": _swift_calculate_complexity(node),
        **_swift_function_flags(modifiers, raw_text, found_visibility),
    }


def _swift_function_flags(
    modifiers: list[str],
    raw_text: str,
    found_visibility: str,
) -> dict[str, bool]:
    modifier_set = set(modifiers)
    return {
        "is_async": "async" in modifiers or _has_word(raw_text, "async"),
        "is_static": bool({"static", "class"} & modifier_set),
        "is_private": bool({"private", "fileprivate"} & modifier_set),
        "is_public": found_visibility in {"open", "public"},
    }


def _swift_class(
    node: tree_sitter.Node,
    raw_text: str,
    name: str,
    declaration_kind: str,
    modifiers: list[str],
) -> Class:
    inherited = inherited_types(raw_text)
    parent_type = superclass(declaration_kind, inherited)
    fields = _swift_class_fields(
        node,
        raw_text,
        name,
        declaration_kind,
        modifiers,
        inherited,
        parent_type,
    )
    return Class(**fields)


def _swift_class_fields(
    node: tree_sitter.Node,
    raw_text: str,
    name: str,
    declaration_kind: str,
    modifiers: list[str],
    inherited: list[str],
    parent_type: str | None,
) -> dict[str, Any]:
    return {
        **base_element_fields(node, raw_text, name),
        **_swift_type_fields(declaration_kind, modifiers, inherited, parent_type, name),
    }


def _swift_type_fields(
    declaration_kind: str,
    modifiers: list[str],
    inherited: list[str],
    parent_type: str | None,
    name: str,
) -> dict[str, Any]:
    return {
        "class_type": declaration_kind,
        "full_qualified_name": name,
        "superclass": parent_type,
        "interfaces": interfaces(inherited, parent_type),
        "modifiers": modifiers,
        "visibility": visibility(modifiers),
    }


def _swift_variable(
    node: tree_sitter.Node,
    raw_text: str,
    name: str,
    annotation: str | None,
    modifiers: list[str],
    binding: str,
) -> Variable:
    is_constant = binding == "let"
    fields = base_element_fields(node, raw_text, name)
    fields.update(_swift_variable_fields(annotation, modifiers, is_constant))
    return Variable(**fields)


def _swift_variable_fields(
    annotation: str | None,
    modifiers: list[str],
    is_constant: bool,
) -> dict[str, Any]:
    return {
        "variable_type": annotation,
        "modifiers": modifiers,
        "is_constant": is_constant,
        "is_static": bool({"static", "class"} & set(modifiers)),
        "visibility": visibility(modifiers),
        "is_final": is_constant,
    }


def _swift_import_fields(
    node: tree_sitter.Node,
    raw_text: str,
    module_path: str,
) -> dict[str, Any]:
    fields = base_element_fields(node, raw_text, module_path)
    fields.update(
        {
            "module_name": module_path,
            "module_path": module_path,
            "imported_names": [module_path] if module_path else [],
            "import_statement": raw_text,
            "line_number": node.start_point[0] + 1,
        }
    )
    return fields


def _parameter_names(raw_text: str) -> list[str]:
    clause = _parameter_clause(raw_text)
    if clause is None:
        return []
    return [_parameter(part) for part in _split_top_level(clause) if part.strip()]


def _parameter_clause(raw_text: str) -> str | None:
    """Return the text inside the parameter parentheses, matched with
    balanced parens so tuple/closure types keep their own ``)``."""
    start = raw_text.find("(")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(raw_text)):
        char = raw_text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return raw_text[start + 1 : index]
    return raw_text[start + 1 :]


def _split_top_level(text: str) -> list[str]:
    """Split on commas that sit outside any (), [], or <> nesting, so a
    tuple ``(Int, String)``, dictionary, or generic ``Result<Int, Error>``
    stays in one parameter. The ``>`` of a ``->`` arrow is not a closer."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    prev = ""
    for char in text:
        if char in "([<":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif char == ">" and prev != "-":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        prev = char
    parts.append("".join(current))
    return parts


def _parameter(parameter_text: str) -> str:
    """Render a Swift parameter as ``name: Type`` (mirrors Rust).

    Drops the external argument label and the ``_`` no-label marker (keeping
    the internal name), strips any default value, and splits on the *first*
    colon only so dictionary types like ``[String: Int]`` stay intact.
    """
    before_type, sep, after_type = parameter_text.partition(":")
    name = _parameter_name(before_type)
    if not sep:
        return name
    type_text = " ".join(after_type.split("=", 1)[0].split())
    if not type_text:
        return name
    return f"{name}: {type_text}" if name else type_text


def _parameter_name(before_type: str) -> str:
    before_type = before_type.strip()
    if not before_type:
        return ""
    tokens = before_type.split()
    return tokens[-1].lstrip("_") or tokens[-1]


def _return_type(raw_text: str) -> str | None:
    """Extract a Swift return type, including bracket/tuple-led types.

    The return arrow is sought *after* the parameter list's closing paren,
    so a closure-typed parameter's own ``->`` is never mistaken for it (a
    function with a closure param and no return type yields None, not the
    malformed ``Void)``). Covers collection shorthand (``[T]``, ``[K: V]``)
    and tuples (``(A, B)``), which the previous letter-anchored regex
    dropped entirely.
    """
    end = _param_list_end(raw_text)
    tail = raw_text[end + 1 :] if end != -1 else raw_text
    tail = tail.split("{", 1)[0]
    arrow = tail.find("->")
    if arrow == -1:
        return None
    return tail[arrow + 2 :].strip() or None


def _param_list_end(raw_text: str) -> int:
    """Index of the parameter list's matching closing paren, or -1."""
    start = raw_text.find("(")
    if start == -1:
        return -1
    depth = 0
    for index in range(start, len(raw_text)):
        char = raw_text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _import_module_path(raw_text: str) -> str:
    text = raw_text.strip()
    text = re.sub(r"^import\s+", "", text)
    text = re.sub(r"^(class|struct|enum|protocol|func|var|typealias)\s+", "", text)
    return text.strip()


def _has_word(raw_text: str, word: str) -> bool:
    return bool(re.search(rf"\b{re.escape(word)}\b", raw_text))
