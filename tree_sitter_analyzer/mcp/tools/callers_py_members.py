"""RFC-0043 Phase C: the member declarations of a Python file, per content digest.

The Python supertype gate (:mod:`.callers_py_supertypes`, #1883) and the
subtype gate (:mod:`.callers_py_subtypes`, #1896) both start by finding the
class whose body declares the target on its line (``_owner_class``). That was
an ``ast.walk`` over the whole module on every request, twice per target: on
pydantic about a third of the Python supertype gate's warm cost.

:func:`member_table` keeps, per content digest, every node ``_owner_class``
could pick (a ``def``, or an assignment to a plain name) in ``ast.walk`` order:
its name, line span, ``def`` line and, when its direct parent is a class, the
path of that class from the module root. :func:`owner_path` makes the same
choice ``_owner_class`` made over the same nodes in the same order, and
:func:`node_at` follows the path in the request's own tree.

Trust (RFC-0042 R0/R1, RFC-0043 §1): the table is a pure function of the
bytes the module was parsed from (the caller reads them live on every request
through the stamp-validated evidence file cache); it holds strings, integers
and tuples only, never a syntax tree. With the parse memo off
(``TSA_RESIDENT_PARSE_MEMO=0`` or ``TSA_RESIDENT=off``) it is built for every
call.
"""

from __future__ import annotations

import ast
from collections import deque
from typing import Any

#: One step from a node to a child: ``(field, index)``; index -1 for a single node.
Step = tuple[str, int]
#: The steps from the module root to a node.
NodePath = tuple[Step, ...]
#: ``(name, first line, last line, def line, path of the parent class or None)``.
Member = tuple[str, int, int, int, NodePath | None]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
KIND = "py.members"


def member_table(content_digest: bytes, tree: ast.Module) -> tuple[Member, ...]:
    """Every member declaration of ``tree``, reused per content digest.

    ``content_digest`` must be :func:`...resident.parse_facts.digest` of the
    exact bytes ``tree`` was parsed from; without one (empty) it is built live.
    """
    from ...resident import parse_facts

    if not content_digest:
        return build_member_table(tree)
    return parse_facts.facts_for_digest(
        KIND, "python", content_digest, lambda: build_member_table(tree)
    )


def build_member_table(tree: ast.Module) -> tuple[Member, ...]:
    """The table, breadth first in ``ast.walk`` order (live, no memo)."""
    members: list[Member] = []
    todo: deque[tuple[ast.AST, NodePath, NodePath | None]] = deque([(tree, (), None)])
    while todo:
        node, path, parent_class = todo.popleft()
        own_class = path if isinstance(node, ast.ClassDef) else None
        for name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                todo.append((value, (*path, (name, -1)), own_class))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        todo.append((item, (*path, (name, index)), own_class))
        for name in _declared_names(node):
            members.append(_member(node, name, parent_class))
    return tuple(members)


def _declared_names(node: ast.AST) -> tuple[str, ...]:
    """The names ``node`` declares in ``_declares``'s sense, once each."""
    if isinstance(node, _FUNCTIONS):
        return (node.name,)
    if isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        return tuple(dict.fromkeys(names))
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target.id,)
    return ()


def _member(node: Any, name: str, parent_class: NodePath | None) -> Member:
    first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", ()))])
    last = node.end_lineno or node.lineno
    return (str(name), int(first), int(last), int(node.lineno), parent_class)


def owner_path(table: tuple[Member, ...], line: int, bare: str) -> NodePath | None:
    """The class whose body directly declares ``bare`` on ``line`` (innermost).

    The same choice as a walk over the nodes: the last node, in walk order,
    with the greatest ``def`` line among those that declare ``bare`` and span
    ``line``.
    """
    best: Member | None = None
    for member in table:
        name, first, last, lineno, _parent = member
        if name != bare or not first <= line <= last:
            continue
        if best is None or lineno >= best[3]:
            best = member
    return None if best is None else best[4]


def node_at(tree: ast.AST, path: NodePath) -> Any:
    """The node ``path`` names in ``tree``."""
    node: Any = tree
    for name, index in path:
        value = getattr(node, name)
        node = value if index < 0 else value[index]
    return node


__all__ = ["KIND", "build_member_table", "member_table", "node_at", "owner_path"]
