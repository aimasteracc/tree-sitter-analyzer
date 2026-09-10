"""Tree-sitter node discovery for the state-diagram scanner."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}


def node_text(node: Any, max_len: int = 60) -> str:
    """Decode a tree-sitter node's text, capped at ``max_len`` characters."""
    try:
        raw = node.text
        if raw is None:
            return ""
        text: str = raw.decode("utf-8", errors="replace").strip()
        return text[:max_len] if len(text) > max_len else text
    except Exception:
        return ""


def walk_nodes(root: Any) -> Iterator[Any]:
    """Yield a tree in stable pre-order without recursive call depth."""
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(list(node.children)))


def _enum_class_identity(node: Any) -> tuple[str, bool]:
    """Return the direct class name and whether it has a supported Enum base."""
    name = ""
    has_enum_base = False
    for child in node.children:
        if child.type == "identifier":
            name = node_text(child)
            continue
        if child.type != "argument_list":
            continue
        has_enum_base = any(
            node_text(base).split(".")[-1] in _ENUM_BASES for base in child.children
        )
    return name, has_enum_base


def find_enum_classes(root: Any, class_name_filter: str | None) -> list[dict[str, Any]]:
    """Find Enum class definitions, optionally restricted by exact class name."""
    results: list[dict[str, Any]] = []
    for node in walk_nodes(root):
        if node.type != "class_definition":
            continue
        name, has_enum_base = _enum_class_identity(node)
        if not name or not has_enum_base:
            continue
        if class_name_filter is None or name == class_name_filter:
            results.append({"name": name, "node": node})
    return results


def _assignment_member(assignment: Any) -> str | None:
    """Return a public identifier assignment target, if present."""
    children = list(assignment.children)
    if not children:
        return None
    lhs = children[0]
    if lhs.type != "identifier":
        return None
    name = node_text(lhs)
    return name if name and not name.startswith("_") else None


def _expression_statements(class_node: Any) -> Iterator[Any]:
    for block in (child for child in class_node.children if child.type == "block"):
        yield from (
            statement
            for statement in block.children
            if statement.type == "expression_statement"
        )


def _enum_assignments(class_node: Any) -> Iterator[Any]:
    for statement in _expression_statements(class_node):
        yield from (child for child in statement.children if child.type == "assignment")


def extract_enum_members(class_node: Any) -> list[str]:
    """Extract public Enum assignment names in source order."""
    members: list[str] = []
    for assignment in _enum_assignments(class_node):
        member = _assignment_member(assignment)
        if member is not None:
            members.append(member)
    return members
