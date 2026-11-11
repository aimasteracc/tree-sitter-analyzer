"""PR-4: a registering decorator on the target's own definition is a known use.

``DECORATOR_MAY_REGISTER`` (#1596 / #1623) blocks ``complete`` because a decorator
such as ``@app.get("/items")`` or ``@pytest.fixture`` hands the function to a
framework, which later calls it under another name; the call graph has no edge.
Before this module such an answer said ``unknown`` with 0 callers, although the
decorator itself is certain evidence that the function is used: ``@d`` over
``def f`` evaluates ``d(f)`` when the ``def`` statement runs.

This module lists that use as a caller entry of its own kind, so the answer can
honestly say ``incomplete`` (at least this use; the framework-side callers
cannot be listed). It never makes an answer ``complete``: the decorator gate
still reports its problem code.

Soundness: an entry is produced only when the decorator is applied to **this
target's definition**:

* Python only (Java annotations such as ``@Override`` register nothing; other
  languages keep ``unknown``);
* exactly one declaration row backs the target, in the queried file;
* that row is a ``def`` / ``class`` whose name is the target's bare name and
  whose enclosing class chain matches the queried owner (``Class.method``);
* the definition is a direct statement of the module body or of class bodies
  nested directly in it, so the ``def`` runs at import (a definition inside a
  function, ``if`` or ``try`` is conditional and yields nothing);
* only decorators outside :data:`KNOWN_WRAPPERS` are listed, the same split the
  gate uses.

Any read or parse failure yields no entry, which keeps the answer ``unknown``.
"""

from __future__ import annotations

import ast
import os
from typing import Any

from .callers_confidence import REGISTRATION
from .callers_decorators import KNOWN_WRAPPERS, _parsed_python, _qualify
from .evidence_file_cache import FILE_CACHE

#: ``resolution_kind`` of a registration entry (see ``callers_confidence``).
REGISTRATION_KIND = REGISTRATION
#: Pseudo-caller name: the decorator runs when the module body executes.
REGISTRATION_CALLER = "<module>"

_DEFINITION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def target_registrations(
    project_root: str,
    declarations: list[tuple[str, int, str]],
    func_name: str,
    file_path: str | None,
) -> list[dict[str, Any]]:
    """Registration entries for the target's single definition; ``[]`` if unsure."""
    if len(declarations) != 1:
        return []
    rel_path, line, language = declarations[0]
    if language != "python":
        return []
    if file_path and rel_path.replace("\\", "/") != file_path.replace("\\", "/"):
        return []
    text = FILE_CACHE.read_text(os.path.join(project_root, rel_path))
    if text is None:
        return []
    parsed = _parsed_python(text)
    if parsed is None:
        return []
    tree, bindings = parsed
    owner, _, bare = func_name.rpartition(".")
    node = _definition_at(tree, line, bare, owner)
    if node is None:
        return []
    entries: list[dict[str, Any]] = []
    for item in node.decorator_list:
        if _qualify(item, bindings) in KNOWN_WRAPPERS:
            continue
        segment = ast.get_source_segment(text, item) or ast.unparse(item)
        entries.append(
            {
                "name": REGISTRATION_CALLER,
                "file": rel_path,
                "line": int(item.lineno),
                "language": language,
                "callee_resolution": "local",
                "callee_resolved_file": rel_path,
                "resolution_kind": REGISTRATION_KIND,
                "via": "@" + " ".join(segment.split()),
            }
        )
    return entries


def registration_hint(func_name: str, entries: list[dict[str, Any]]) -> str:
    """next_step for an answer whose only known use is a registration."""
    via = ", ".join(
        f"`{entry['via']}` ({entry['file']}:{entry['line']})" for entry in entries
    )
    return (
        f"{func_name!r} is registered by {via}, listed as `registration` entries. "
        "The framework calls it through that registration, and those "
        "framework-side callers cannot be listed, so the list is incomplete; "
        "direct calls would also appear as call edges."
    )


def _definition_at(
    tree: ast.Module, line: int, bare: str, owner: str
) -> _Definition | None:
    """The unconditional definition whose header holds ``line``; None if unsure."""
    found = [
        (chain, node)
        for chain, node in _unconditional_definitions(tree.body, ())
        if _header_holds(node, line)
    ]
    if len(found) != 1:
        return None
    chain, node = found[0]
    if node.name != bare:
        return None
    if owner and chain[-len(owner.split(".")) :] != tuple(owner.split(".")):
        return None
    return node


def _unconditional_definitions(
    body: list[ast.stmt], chain: tuple[str, ...]
) -> list[tuple[tuple[str, ...], _Definition]]:
    """Definitions that run whenever the module body runs, with their class chain."""
    found: list[tuple[tuple[str, ...], _Definition]] = []
    for statement in body:
        if not isinstance(statement, _DEFINITION_TYPES):
            continue
        found.append((chain, statement))
        if isinstance(statement, ast.ClassDef):
            found.extend(
                _unconditional_definitions(statement.body, (*chain, statement.name))
            )
    return found


def _header_holds(node: _Definition, line: int) -> bool:
    first = min([node.lineno, *(item.lineno for item in node.decorator_list)])
    return first <= line <= node.lineno


__all__ = [
    "REGISTRATION_CALLER",
    "REGISTRATION_KIND",
    "registration_hint",
    "target_registrations",
]
