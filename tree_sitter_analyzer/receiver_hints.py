"""RFC-0038: receiver type hints a Python call site carries into the index.

The extractor cannot resolve a type name (that needs the project's imports), so
it records what the source states about a receiver and leaves resolution to
Synapse (``synapse_resolver/_annotated.py``):

* ``{"source": "param" | "local" | "attribute", "type": "<annotation text>"}``
* ``{"source": "local" | "attribute", "returns_of": "<callee text>"}`` — the
  receiver is the result of a factory call whose return annotation decides it.

Every rule is conservative: any binding of the name the rules cannot classify
(a loop target, tuple unpacking, another call, a comprehension or lambda that
shadows it, ``global`` / ``nonlocal`` / ``del``) withdraws the hint.  A missing
hint only leaves the call where it was before this RFC.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

Hint = dict[str, str]

#: Nodes whose body is a separate scope: bindings inside them are not ours.
_SCOPE_BARRIERS = frozenset({"function_definition", "class_definition", "lambda"})
#: Wrappers between a store target and the statement that binds it.
_PATTERN_WRAPPERS = frozenset(
    {
        "pattern_list",
        "tuple_pattern",
        "list_pattern",
        "list_splat_pattern",
        "parenthesized_expression",
        "expression_list",
    }
)
_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_OWN_RECEIVERS = ("self", "cls")
_PROPERTY_DECORATORS = frozenset(
    {"property", "cached_property", "functools.cached_property"}
)

# A binding's classification: (kind, text). Kinds: "type" (an annotation or an
# annotated parameter), "ctor" (``T(...)``), "call" (``f(...)``), "none"
# (``None``); ``None`` means an unclassifiable binding.
_Binding = tuple[str, str] | None


def _text(node: Any) -> str:
    raw = getattr(node, "text", b"")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw or "")


def _identifiers(node: Any) -> list[str]:
    """Every identifier under ``node`` (inclusive)."""
    found: list[str] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "identifier":
            found.append(_text(current))
        stack.extend(current.children)
    return found


def classify_value(node: Any | None) -> _Binding:
    """Classify the right-hand side of a binding."""
    while node is not None and node.type in ("await", "parenthesized_expression"):
        inner = [c for c in node.children if c.is_named]
        node = inner[-1] if inner else None
    if node is None:
        return None
    if node.type == "none":
        return ("none", "None")
    if node.type == "assignment":  # chained ``a = b = f()``
        return classify_value(node.child_by_field_name("right"))
    if node.type != "call":
        return None
    function = node.child_by_field_name("function")
    text = _text(function) if function is not None else ""
    if not _DOTTED.match(text):
        return None
    if function is not None and function.type == "identifier" and text[0].isupper():
        return ("ctor", text)
    return ("call", text)


@dataclass
class _Scope:
    """Bindings of one function scope, by name."""

    declared: dict[str, list[tuple[str, str]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    assigned: dict[str, list[_Binding]] = field(
        default_factory=lambda: defaultdict(list)
    )
    poisoned: set[str] = field(default_factory=set)
    #: function-local ``import`` bindings (RFC-0038 module receivers)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)

    def untyped(self, names: list[str]) -> None:
        for name in names:
            self.assigned[name].append(None)


def _collect_parameters(params: Any | None, scope: _Scope) -> dict[str, str]:
    """Record parameter bindings; return ``{name: annotation}`` of typed ones."""
    typed: dict[str, str] = {}
    if params is None:
        return typed
    for child in params.children:
        if child.type == "identifier":
            scope.untyped([_text(child)])
        elif child.type in ("typed_parameter", "typed_default_parameter"):
            name_node = child.child_by_field_name("name")
            if name_node is None:
                name_node = next(
                    (c for c in child.children if c.type == "identifier"), None
                )
            type_node = child.child_by_field_name("type")
            if name_node is None or type_node is None:
                scope.untyped(_identifiers(child))
                continue
            name = _text(name_node)
            typed[name] = _text(type_node)
            scope.declared[name].append(("param", typed[name]))
        elif child.type in (
            "default_parameter",
            "list_splat_pattern",
            "dictionary_splat_pattern",
        ):
            name_node = child.child_by_field_name("name")
            names = [_text(name_node)] if name_node is not None else _identifiers(child)
            scope.untyped(names)
    return typed


def _store_identifiers(target: Any) -> list[str]:
    if target.type == "identifier":
        return [_text(target)]
    if target.type in _PATTERN_WRAPPERS:
        return _identifiers(target)
    return []


def _visit_binding_node(node: Any, scope: _Scope) -> None:
    kind = node.type
    if kind == "assignment":
        left = node.child_by_field_name("left")
        if left is None:
            return
        if left.type == "identifier":
            name = _text(left)
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                scope.declared[name].append(("local", _text(type_node)))
            right = node.child_by_field_name("right")
            if right is not None:
                scope.assigned[name].append(classify_value(right))
        else:
            scope.untyped(_store_identifiers(left))
    elif kind == "augmented_assignment":
        left = node.child_by_field_name("left")
        if left is not None:
            scope.untyped(_store_identifiers(left))
    elif kind == "for_statement":
        left = node.child_by_field_name("left")
        if left is not None:
            scope.untyped(_store_identifiers(left))
    elif kind == "named_expression":
        name = node.child_by_field_name("name")
        if name is not None:
            scope.untyped([_text(name)])
    elif kind == "as_pattern_target":
        scope.untyped(_identifiers(node))
    elif kind in (
        "for_in_clause",
        "case_pattern",
        "global_statement",
        "nonlocal_statement",
        "delete_statement",
    ):
        target = node.child_by_field_name("left") if kind == "for_in_clause" else node
        if target is not None:
            scope.poisoned.update(_identifiers(target))
    elif kind in ("import_statement", "import_from_statement"):
        import_bindings(node, scope.imports)


def import_bindings(node: Any, imports: dict[str, tuple[str, str]]) -> None:
    """Record ``local name -> ("module" | "name", module path)`` of an import."""
    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                top = _text(child).split(".", 1)[0]
                imports[top] = ("module", top)
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


def _walk_scope(body: Any, scope: _Scope) -> None:
    stack = list(body.children) if body is not None else []
    while stack:
        node = stack.pop()
        if node.type in _SCOPE_BARRIERS:
            name = node.child_by_field_name("name")
            if name is not None:
                scope.untyped([_text(name)])
            if node.type == "lambda":
                params = node.child_by_field_name("parameters")
                if params is not None:
                    scope.poisoned.update(_identifiers(params))
            continue
        _visit_binding_node(node, scope)
        stack.extend(node.children)


def _decide(scope: _Scope, name: str) -> Hint | None:
    if name in scope.poisoned or name in _OWN_RECEIVERS:
        return None
    declared = scope.declared.get(name)
    if declared:
        texts = {text for _source, text in declared}
        if len(texts) != 1:
            return None
        source = "param" if any(s == "param" for s, _ in declared) else "local"
        return {"source": source, "type": texts.pop()}
    bindings = scope.assigned.get(name, [])
    if not bindings or any(binding is None for binding in bindings):
        return None
    values = {b for b in bindings if b is not None and b[0] != "none"}
    if len(values) != 1:
        return None
    kind, text = values.pop()
    if kind == "call":
        return {"source": "local", "returns_of": text}
    return None  # ``ctor`` keeps the RFC-0002 constructor path.


def function_receiver_hints(func_node: Any) -> dict[str, Hint]:
    """Receiver name -> hint for one Python ``function_definition``."""
    return function_scope_hints(func_node)[0]


def function_scope_hints(
    func_node: Any,
) -> tuple[dict[str, Hint], frozenset[str], dict[str, tuple[str, str]]]:
    """(hints, names bound other than by import, local import bindings)."""
    scope = _Scope()
    _collect_parameters(func_node.child_by_field_name("parameters"), scope)
    _walk_scope(func_node.child_by_field_name("body"), scope)
    names = set(scope.declared) | set(scope.assigned)
    hints: dict[str, Hint] = {}
    for name in names:
        hint = _decide(scope, name)
        if hint is not None:
            hints[name] = hint
    local_imports = {
        name: target for name, target in scope.imports.items() if name not in names
    }
    shadowing = names | scope.poisoned | (set(scope.imports) - set(local_imports))
    return hints, frozenset(shadowing), local_imports


# ---------------------------------------------------------------------------
# Class attributes: ``self.a.m()``
# ---------------------------------------------------------------------------


@dataclass
class _AttributeFacts:
    declared: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    assigned: dict[str, list[_Binding]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _method_nodes(class_body: Any) -> list[tuple[Any, list[str]]]:
    """(function_definition, decorator texts) for each method in a class body."""
    methods: list[tuple[Any, list[str]]] = []
    for child in class_body.children:
        if child.type == "function_definition":
            methods.append((child, []))
        elif child.type == "decorated_definition":
            decorators = [
                _text(c).lstrip("@").strip()
                for c in child.children
                if c.type == "decorator"
            ]
            inner = child.child_by_field_name("definition")
            if inner is not None and inner.type == "function_definition":
                methods.append((inner, decorators))
    return methods


def _first_parameter(func_node: Any) -> str:
    params = func_node.child_by_field_name("parameters")
    for child in params.children if params is not None else []:
        if child.type == "identifier":
            return _text(child)
        if child.type in ("typed_parameter", "default_parameter"):
            return next(
                (_text(c) for c in child.children if c.type == "identifier"), ""
            )
    return ""


def _self_attribute(target: Any, receiver: str) -> str | None:
    if target.type != "attribute":
        return None
    obj = target.child_by_field_name("object")
    attr = target.child_by_field_name("attribute")
    if obj is None or attr is None or obj.type != "identifier":
        return None
    return _text(attr) if _text(obj) == receiver else None


def _collect_method_attributes(
    func_node: Any, facts: _AttributeFacts, typed_params: dict[str, str]
) -> None:
    receiver = _first_parameter(func_node)
    if not receiver:
        return
    body = func_node.child_by_field_name("body")
    stack = list(body.children) if body is not None else []
    while stack:
        node = stack.pop()
        if node.type == "class_definition":
            continue
        if node.type in ("assignment", "augmented_assignment"):
            _record_attribute_assignment(node, receiver, facts, typed_params)
        stack.extend(node.children)


def _record_attribute_assignment(
    node: Any, receiver: str, facts: _AttributeFacts, typed_params: dict[str, str]
) -> None:
    left = node.child_by_field_name("left")
    if left is None:
        return
    attr = _self_attribute(left, receiver)
    if attr is None:
        # ``self.a, self.b = ...``: any own attribute in a pattern is untyped.
        if left.type in _PATTERN_WRAPPERS:
            for child in left.children:
                inner = _self_attribute(child, receiver)
                if inner is not None:
                    facts.assigned[inner].append(None)
        return
    if node.type == "augmented_assignment":
        facts.assigned[attr].append(None)
        return
    type_node = node.child_by_field_name("type")
    if type_node is not None:
        facts.declared[attr].add(_text(type_node))
    right = node.child_by_field_name("right")
    if right is None:
        return
    if right.type == "identifier" and _text(right) in typed_params:
        facts.assigned[attr].append(("type", typed_params[_text(right)]))
    else:
        facts.assigned[attr].append(classify_value(right))


def _class_body_annotations(class_body: Any, facts: _AttributeFacts) -> None:
    for child in class_body.children:
        if child.type != "expression_statement":
            continue
        for node in child.children:
            if node.type != "assignment":
                continue
            left = node.child_by_field_name("left")
            if left is None or left.type != "identifier":
                continue
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                facts.declared[_text(left)].add(_text(type_node))
            right = node.child_by_field_name("right")
            if right is not None and type_node is None:
                facts.assigned[_text(left)].append(classify_value(right))


def _decide_attribute(facts: _AttributeFacts, attr: str) -> Hint | None:
    declared = facts.declared.get(attr)
    if declared:
        return (
            {"source": "attribute", "type": next(iter(declared))}
            if len(declared) == 1
            else None
        )
    bindings = facts.assigned.get(attr, [])
    if not bindings or any(binding is None for binding in bindings):
        return None
    values = {b for b in bindings if b is not None and b[0] != "none"}
    if len(values) != 1:
        return None
    kind, text = values.pop()
    if kind == "call":
        return {"source": "attribute", "returns_of": text}
    return {"source": "attribute", "type": text}


def class_attribute_hints(module_node: Any) -> dict[str, dict[str, Hint]]:
    """Class name -> {attribute: hint} for every class in a Python module."""
    per_class: dict[str, _AttributeFacts] = defaultdict(_AttributeFacts)
    stack = [module_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "class_definition":
            continue
        name = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        if name is None or body is None:
            continue
        facts = per_class[_text(name)]
        _class_body_annotations(body, facts)
        for method, decorators in _method_nodes(body):
            method_name = method.child_by_field_name("name")
            return_type = method.child_by_field_name("return_type")
            if (
                method_name is not None
                and return_type is not None
                and any(d in _PROPERTY_DECORATORS for d in decorators)
            ):
                facts.declared[_text(method_name)].add(_text(return_type))
            scope = _Scope()
            typed = _collect_parameters(method.child_by_field_name("parameters"), scope)
            _collect_method_attributes(method, facts, typed)
    hints: dict[str, dict[str, Hint]] = {}
    for class_name, facts in per_class.items():
        attrs = set(facts.declared) | set(facts.assigned)
        decided = {
            attr: hint
            for attr in attrs
            if (hint := _decide_attribute(facts, attr)) is not None
        }
        if decided:
            hints[class_name] = decided
    return hints


def call_receiver_hint(
    receiver: str | None,
    function_hints: dict[str, Hint] | None,
    attribute_hints: dict[str, dict[str, Hint]] | None,
    enclosing_class: str | None,
) -> Hint | None:
    """The hint for a call whose receiver text is ``receiver``, if any."""
    if not receiver:
        return None
    if function_hints and receiver in function_hints:
        return function_hints[receiver]
    head, _, attr = receiver.partition(".")
    if (
        head in _OWN_RECEIVERS
        and attr
        and "." not in attr
        and enclosing_class
        and attribute_hints
    ):
        return attribute_hints.get(enclosing_class, {}).get(attr)
    return None
