"""RFC-0038: module-level receivers (``REGISTRY = IndexSnapshotRegistry(...)``).

A module-level name whose every top-level binding agrees on one type (an
annotation, a constructor or a factory call; ``None`` ignored) gets a hint.
No function may rebind it through ``global``. Three call shapes use it:

* ``NAME.m()`` in the defining module, where no enclosing function binds
  ``NAME``. The hint is attached directly.
* ``alias.NAME.m()`` after ``import pkg.mod as alias``, and
* ``NAME.m()`` after ``from pkg.mod import NAME``. For these two, the extractor
  only records where to look. Synapse reads the defining module's
  ``module_types`` (persisted in its ``symbols_json``) and resolves the hint
  there.

Stdlib modules are skipped: their attributes are never project types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .receiver_hints import Hint, _Scope, _visit_binding_node
from .synapse_resolver._constants import STDLIB_NAMES_PY

_DEFINITIONS = frozenset({"function_definition", "class_definition"})


@dataclass(frozen=True)
class ModuleHints:
    """Module-level receiver facts of one Python file."""

    variables: dict[str, Hint] = field(default_factory=dict)
    #: local name -> ("module" | "name", imported module path)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)


def _text(node: Any) -> str:
    raw = getattr(node, "text", b"")
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)


def _import_bindings(node: Any, imports: dict[str, tuple[str, str]]) -> None:
    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                path = _text(child)
                imports[path.split(".", 1)[0]] = ("module", path.split(".", 1)[0])
            elif child.type == "aliased_import":
                name = child.child_by_field_name("name")
                alias = child.child_by_field_name("alias")
                if name is not None and alias is not None:
                    imports[_text(alias)] = ("module", _text(name))
        return
    module = node.child_by_field_name("module_name")
    module_path = _text(module) if module is not None else ""
    for index, child in enumerate(node.children):
        if node.field_name_for_child(index) != "name":
            continue
        if child.type == "dotted_name":
            imports[_text(child)] = ("name", module_path)
        elif child.type == "aliased_import":
            alias = child.child_by_field_name("alias")
            if alias is not None:
                imports[_text(alias)] = ("name", module_path)


def _global_names(root: Any) -> set[str]:
    names: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "global_statement":
            names.update(
                _text(child) for child in node.children if child.type == "identifier"
            )
        stack.extend(node.children)
    return names


def module_hints(root: Any) -> ModuleHints:
    """Collect module-level variable hints and import bindings of a module."""
    scope = _Scope()
    imports: dict[str, tuple[str, str]] = {}
    stack = list(root.children)
    while stack:
        node = stack.pop()
        if node.type in _DEFINITIONS:
            name = node.child_by_field_name("name")
            if name is not None:
                scope.untyped([_text(name)])
            continue
        if node.type == "decorated_definition":
            stack.extend(c for c in node.children if c.type in _DEFINITIONS)
            continue
        if node.type == "lambda":
            # A lambda parameter shadows a module name inside the lambda body,
            # whose calls are extracted in module scope: never type that name.
            params = node.child_by_field_name("parameters")
            if params is not None:
                scope.poisoned.update(
                    _text(c) for c in params.children if c.type == "identifier"
                )
        if node.type in ("import_statement", "import_from_statement"):
            _import_bindings(node, imports)
        _visit_binding_node(node, scope)
        stack.extend(node.children)
    scope.poisoned |= _global_names(root)
    variables: dict[str, Hint] = {}
    for name in set(scope.declared) | set(scope.assigned):
        hint = _decide_module(scope, name)
        if hint is not None and name not in imports:
            variables[name] = hint
    return ModuleHints(variables=variables, imports=imports)


def _decide_module(scope: _Scope, name: str) -> Hint | None:
    if name in scope.poisoned:
        return None
    declared = scope.declared.get(name)
    if declared:
        texts = {text for _source, text in declared}
        return {"source": "module", "type": texts.pop()} if len(texts) == 1 else None
    bindings = scope.assigned.get(name, [])
    if not bindings or any(binding is None for binding in bindings):
        return None
    values = {b for b in bindings if b is not None and b[0] != "none"}
    if len(values) != 1:
        return None
    kind, text = values.pop()
    if kind == "ctor":
        return {"source": "module", "type": text}
    return {"source": "module", "returns_of": text}


def _is_stdlib(module_path: str) -> bool:
    top = module_path.lstrip(".").split(".", 1)[0]
    return bool(top) and not module_path.startswith(".") and top in STDLIB_NAMES_PY


def module_call_hint(
    receiver: str, module: ModuleHints | None, shadowed: frozenset[str]
) -> Hint | None:
    """Hint for ``NAME.m()`` / ``alias.NAME.m()`` through a module-level name."""
    if module is None or not receiver:
        return None
    head, _, rest = receiver.partition(".")
    if head in shadowed:
        return None
    if not rest:
        if head in module.variables:
            return module.variables[head]
        imported = module.imports.get(head)
        if imported and imported[0] == "name" and not _is_stdlib(imported[1]):
            return {"source": "module", "imported": head}
        return None
    imported = module.imports.get(head)
    # ``from . import mod as alias`` binds a submodule as a "name" import too;
    # Synapse decides whether ``alias`` is a module.
    if "." not in rest and imported is not None and not _is_stdlib(imported[1]):
        return {"source": "module", "module_attr": receiver}
    return None


__all__ = ["ModuleHints", "module_call_hint", "module_hints"]
