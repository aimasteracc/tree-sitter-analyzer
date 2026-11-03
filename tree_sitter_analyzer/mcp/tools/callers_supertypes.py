"""#1882: a JS/TS method whose class chain has a supertype the index cannot follow.

``class V1 extends mix(Proc)`` gets no ``extends`` edge, so ``this.getQuery()`` in
``Proc.run`` is never offered ``V1.getQuery`` as a possible target, and the
override answered ``complete`` with 0 callers. Any member that may override a
supertype member is reachable that way: instance methods, accessors, instance
fields and static methods (``this.build()`` in a static base method dispatches to
a subclass's static ``build``). Constructors are not: they are reached by ``new``.

The gate walks the declaring class's ``extends`` chain from source, never from
inheritance edges, and fails closed on the first clause it cannot follow:

* followed: no ``extends``; ``extends null``; a class declared once in the same
  file; a named import from a relative module that declares (or re-exports) the
  class; ``ns.B`` for a relative ``import * as ns``;
* known external, the walk stops there: a name or namespace imported from a
  package (``react``, ``node:events``), or an ECMAScript / web platform global
  (``Error``, ``Map``, ``HTMLElement``) that the file does not rebind;
* anything else is :data:`DYNAMIC_SUPERTYPE_REASON`, named by its clause: a call
  (``mix(Proc)``), a conditional, a cast, a local value (``const B = mix(P)``), an
  import that does not resolve to one project class, an unknown identifier, a
  name declared twice, a cycle or a chain longer than :data:`_CHAIN_MAX`.

A file that cannot be read or parsed is the same code with ``unchecked`` set.

#1883: Python members get the same check over their class's bases, walked with
:mod:`ast` in :mod:`.callers_py_supertypes`.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from ...graph.read_interrupt import raise_if_interrupted
from .callers_outcomes import CheckOutcome, NotChecked, Scope, checked
from .callers_ts_source import JSTS_SUFFIXES, Source, SourceReader

#: Problem code of the gate (also reported when the gate could not run).
DYNAMIC_SUPERTYPE_REASON = "DYNAMIC_SUPERTYPE"
#: Steps followed along one ``extends`` chain (re-export hops included).
_CHAIN_MAX = 32
_CLASS_TYPES = frozenset({"class_declaration", "abstract_class_declaration", "class"})
#: Class members that may override a supertype member.
_MEMBER_TYPES = frozenset(
    {
        "method_definition",
        "method_signature",
        "abstract_method_signature",
        "public_field_definition",
        "field_definition",
    }
)
#: Wrappers that do not change the value of an ``extends`` expression.
_PARENTHESIZED = "parenthesized_expression"
#: Globals of the ECMAScript and web platform: external classes, like a package.
KNOWN_GLOBALS = frozenset(
    {
        "AbortController",
        "AggregateError",
        "Array",
        "ArrayBuffer",
        "BigInt64Array",
        "BigUint64Array",
        "Blob",
        "Boolean",
        "CustomEvent",
        "DataView",
        "Date",
        "DOMException",
        "Error",
        "EvalError",
        "Event",
        "EventTarget",
        "File",
        "Float32Array",
        "Float64Array",
        "FormData",
        "Function",
        "Headers",
        "HTMLElement",
        "Int16Array",
        "Int32Array",
        "Int8Array",
        "Map",
        "Number",
        "Object",
        "Promise",
        "RangeError",
        "ReadableStream",
        "ReferenceError",
        "RegExp",
        "Request",
        "Response",
        "Set",
        "SharedArrayBuffer",
        "String",
        "Symbol",
        "SyntaxError",
        "TextDecoder",
        "TextEncoder",
        "TransformStream",
        "TypeError",
        "URIError",
        "URL",
        "URLSearchParams",
        "Uint16Array",
        "Uint32Array",
        "Uint8Array",
        "Uint8ClampedArray",
        "WeakMap",
        "WeakSet",
        "WritableStream",
    }
)


@dataclass(frozen=True)
class SupertypeFinding:
    """The first ``extends`` clause the walk could not follow."""

    clause: str
    file: str
    line: int
    class_name: str
    why: str
    #: The source could not be read or parsed: the gate did not run.
    unchecked: bool = False
    #: How the clause relates to the class (#1883: Python "has base").
    verb: str = "extends"

    def describe(self) -> str:
        if self.unchecked:
            return f"{self.why} ({self.file})" if self.file else self.why
        return (
            f"class `{self.class_name}` ({self.file}:{self.line}) {self.verb} "
            f"`{self.clause}`, {self.why}"
        )

    @property
    def receiver(self) -> str:
        """The base-class receiver of a dispatched call in the clause's language."""
        return "this" if self.verb == "extends" else "self"


def dynamic_supertype(
    project_root: str,
    declarations: list[tuple[str, int, str]],
    bare: str,
    cache: Any = None,
    owner: str = "",
) -> SupertypeFinding | None:
    """The first unfollowable supertype clause above a JS/TS or Python member ``bare``.

    ``declarations`` are the target's ``(file, line, language)`` rows; rows that are
    not a member of a class body (functions, object literal methods), JS/TS
    constructors and files in other languages pass. ``cache`` (the index) tells
    project modules from third-party ones for Python (#1883); without it a
    non-stdlib module that is no project file cannot be classified. ``owner`` (the
    qualified target's class path) skips Python members of other classes.
    """
    python = [row for row in declarations if row[0].lower().endswith(".py")]
    if python:
        python_found = _python_finding(project_root, python, bare, cache, owner)
        if python_found is not None:
            return python_found
    reader = SourceReader(project_root)
    for rel, line, _language in declarations:
        if not rel.lower().endswith(JSTS_SUFFIXES):
            continue
        source = reader.read(rel)
        if source is None:
            return _unchecked(rel, "the declaring file could not be read or parsed")
        member = _member_at(source, line, bare)
        if member is None:
            if source.has_error:
                return _unchecked(rel, "the declaring file has a syntax error")
            continue
        owner_class = _owner_class(member)
        if (
            owner_class is None
            or _is_constructor(source, member)
            or _is_private(member)
        ):
            continue
        found = _walk_chain(reader, source, owner_class)
        if found is not None:
            return found
    return None


def _python_finding(
    project_root: str,
    rows: list[tuple[str, int, str]],
    bare: str,
    cache: Any,
    owner: str,
) -> SupertypeFinding | None:
    """#1883: the first finding on a row of the target's own class.

    A file may declare ``bare`` in several classes; for ``V2.m`` the rows of
    other classes are other symbols. When no row's class is named like the
    owner (a module-qualified name, an alias), every row counts.
    """
    from .callers_py_supertypes import python_dynamic_base

    wanted = owner.rpartition(".")[2]
    results = [
        python_dynamic_base(
            project_root, rel, line, bare, lambda: python_project_tops(cache)
        )
        for rel, line, _language in rows
    ]
    own = [found for name, found in results if wanted and name == wanted]
    candidates = own if own else [found for _name, found in results]
    unread = [found for name, found in results if name is None and found is not None]
    return next((f for f in [*unread, *candidates] if f is not None), None)


def supertype_outcome(
    scope: Scope,
    project_root: str,
    declarations: list[tuple[str, int, str]],
    bare: str,
    cache: Any = None,
    owner: str = "",
) -> tuple[CheckOutcome, SupertypeFinding | None]:
    """The ``supertype_dispatch`` check (RFC-0040) and its finding."""
    try:
        finding = dynamic_supertype(project_root, declarations, bare, cache, owner)
    except Exception as exc:  # noqa: BLE001 — a failed walk is "cannot prove"
        raise_if_interrupted(exc)
        finding = _unchecked("", f"the supertype walk failed ({type(exc).__name__})")
    if finding is None:
        return checked(scope), None
    if finding.unchecked:
        return NotChecked(DYNAMIC_SUPERTYPE_REASON), finding
    return checked(scope, DYNAMIC_SUPERTYPE_REASON), finding


def dynamic_supertype_hint(func_name: str, finding: SupertypeFinding) -> str:
    """next_step of the gate."""
    if finding.unchecked:
        return (
            f"No resolved caller for {func_name!r}, and its class's supertype "
            f"chain could not be read: {finding.describe()}. A call through a "
            "supertype could reach it without a call edge naming it, so this is "
            "not evidence of absence."
        )
    return (
        f"No resolved caller for {func_name!r}, but {finding.describe()}. The "
        "index records no inheritance edge for such a clause, so a call through "
        f"a supertype (for example `{finding.receiver}."
        f"{func_name.rpartition('.')[2]}()` in a "
        "base class) could reach it without a call edge naming it; this is not "
        "evidence of absence. Read what the clause evaluates to and search its "
        "classes for calls of the method."
    )


def python_project_tops(cache: Any) -> frozenset[str] | None:
    """Every directory and module name of the index's Python files; None if unreadable.

    A top-level import name in this set may be a project module, so one that does
    not resolve to a project file is not treated as a third-party package.
    """
    if cache is None:
        return None
    from ...resident import snapshot_memo

    def read() -> frozenset[str] | None:
        try:
            rows = (
                cache.get_conn()
                .execute("SELECT file_path FROM ast_index WHERE language = 'python'")
                .fetchall()
            )
        except Exception:  # noqa: BLE001 — unreadable: cannot classify
            return None
        tops: set[str] = set()
        for (path,) in rows:
            for part in str(path).replace("\\", "/").split("/"):
                tops.add(part[:-3] if part.endswith(".py") else part)
        return frozenset(tops)

    found = snapshot_memo.cached(cache, "supertypes.python_tops", (), read)
    return None if found is None else frozenset(found)


def _unchecked(rel: str, why: str) -> SupertypeFinding:
    return SupertypeFinding("", rel, 0, "", why, unchecked=True)


def _member_at(source: Source, line: int, bare: str) -> Any | None:
    """The innermost class-body member named ``bare`` whose span holds ``line``."""
    best = None
    for node in _facts(source).members.get(bare.lstrip("#"), ()):
        if not node.start_point[0] + 1 <= line <= node.end_point[0] + 1:
            continue
        if best is None or node.start_byte > best.start_byte:
            best = node
    return best


def _is_private(member: Any) -> bool:
    """``#m``: an ECMAScript private member is never reached through a subclass."""
    name = member.child_by_field_name("name") or member.child_by_field_name("property")
    return name is not None and name.type == "private_property_identifier"


def _member_name(source: Source, node: Any) -> str:
    text = source.text(node)
    if node.type == "private_property_identifier":
        return text.lstrip("#")
    if node.type == "string" and len(text) >= 2:
        return text[1:-1]
    return text


def _owner_class(member: Any) -> Any | None:
    body = member.parent
    if body is None or body.type != "class_body":
        return None
    owner = body.parent
    return owner if owner is not None and owner.type in _CLASS_TYPES else None


def _is_constructor(source: Source, member: Any) -> bool:
    name = member.child_by_field_name("name")
    return (
        member.type in ("method_definition", "method_signature")
        and name is not None
        and source.text(name) == "constructor"
    )


def _class_name(source: Source, node: Any) -> str:
    name = node.child_by_field_name("name")
    return "<anonymous>" if name is None else source.text(name)


def _heritage_value(node: Any) -> tuple[bool, Any | None]:
    """``(has_extends, value)``; value None when the clause has an unexpected shape."""
    heritage = [c for c in node.named_children if c.type == "class_heritage"]
    if not heritage:
        return False, None
    if len(heritage) != 1:
        return True, None
    clauses = [c for c in heritage[0].named_children if c.type == "extends_clause"]
    if clauses:
        if len(clauses) != 1:
            return True, None
        values = [
            child
            for index, child in enumerate(clauses[0].children)
            if clauses[0].field_name_for_child(index) == "value"
        ]
        return True, values[0] if len(values) == 1 else None
    if any(c.type == "implements_clause" for c in heritage[0].named_children):
        return False, None  # TypeScript ``implements`` only: no runtime supertype
    exprs = heritage[0].named_children  # JavaScript: the expression itself
    return True, exprs[0] if len(exprs) == 1 else None


def _walk_chain(
    reader: SourceReader, source: Source, node: Any
) -> SupertypeFinding | None:
    seen: set[tuple[str, int]] = set()
    for _ in range(_CHAIN_MAX):
        key = (source.rel, int(node.start_byte))
        if key in seen:
            return _finding(source, node, None, "which is a cycle")
        seen.add(key)
        has_extends, written = _heritage_value(node)
        if not has_extends:
            return None
        value = written
        while value is not None and value.type == _PARENTHESIZED:
            inner = value.named_children
            value = inner[0] if len(inner) == 1 else None
        if value is None or value.has_error:
            return _finding(source, node, written, "a clause that could not be read")
        step = _step(reader, source, value)
        if isinstance(step, str):
            return _finding(source, node, written, step)
        if step is None:
            return None  # a known external class or ``null``
        source, node = step
    return _finding(source, node, None, "whose chain is too long to follow")


def _finding(
    source: Source, node: Any, value: Any | None, why: str
) -> SupertypeFinding:
    clause = source.text(value) if value is not None else "?"
    return SupertypeFinding(
        " ".join(clause.split())[:80],
        source.rel,
        int(node.start_point[0]) + 1,
        _class_name(source, node),
        why,
    )


_Step = tuple[Source, Any] | str | None
#: How a finding names the clause's expression.
_EXPRESSION_KINDS = {
    "call_expression": "a call (a mixin or class factory)",
    "ternary_expression": "a conditional",
    "as_expression": "a cast",
    "satisfies_expression": "a cast",
    "non_null_expression": "a cast",
    "type_assertion": "a cast",
    "class": "a class expression",
    "subscript_expression": "a computed member",
}


def _step(reader: SourceReader, source: Source, value: Any) -> _Step:
    """The supertype class, None for a known external one, or why it cannot be read."""
    if value.type == "null":
        return None
    if value.type == "identifier":
        return _resolve_name(reader, source, source.text(value))
    if value.type == "member_expression":
        return _resolve_member(reader, source, value)
    kind = _EXPRESSION_KINDS.get(value.type, f"a `{value.type}` expression")
    return f"{kind} the index cannot follow"


def _resolve_name(reader: SourceReader, source: Source, name: str) -> _Step:
    bindings = _bindings(source, name)
    if bindings > 1:
        return "a name bound more than once in its file"
    local = source.classes.get(name) or []
    imported = source.named_imports.get(name)
    if bindings == 0:
        return None if name in KNOWN_GLOBALS else _UNDECLARED
    if local:
        return source, local[0]
    if imported is not None:
        spec, original = imported
        if not spec.startswith(("./", "../")):
            return None  # a package export: a known external class
        return _imported_class(reader, source.rel, spec, original, 0)
    module = source.module_bindings.get(name)
    if name in source.module_bindings and module is not None:
        if not module.startswith(("./", "../")):
            return None  # a package's default export
        return "a default or module import the index cannot follow"
    if _required_package(source, name):
        return None  # ``const B = require('pkg')``: a known external class
    return "a value, not a class the index can follow"


def _required_package(source: Source, name: str) -> bool:
    """``const X = require('pkg')`` or ``const { X } = require('pkg').m`` binds ``name``."""
    for node in _facts(source).declarators.get(name, ())[:1]:
        value = node.child_by_field_name("value")
        while value is not None and value.type == "member_expression":
            value = value.child_by_field_name("object")
        return _requires_package(source, value)
    return False


def _requires_package(source: Source, value: Any | None) -> bool:
    if value is None or value.type != "call_expression":
        return False
    func = value.child_by_field_name("function")
    args = value.child_by_field_name("arguments")
    if func is None or source.text(func) != "require" or args is None:
        return False
    if len(args.named_children) != 1 or args.named_children[0].type != "string":
        return False
    spec = source.text(args.named_children[0])[1:-1]
    return bool(spec) and not spec.startswith(("./", "../", "/"))


_UNDECLARED = "an identifier not declared or imported in its file"
#: Declarations whose ``name`` field binds a name in the file.
_NAMED_BINDINGS = frozenset(
    {
        *_CLASS_TYPES,
        "variable_declarator",
        "function_declaration",
        "generator_function_declaration",
        "enum_declaration",
        "import_specifier",
        "namespace_import",
    }
)
#: Parameter nodes whose ``pattern`` (TS) or self (JS identifier) binds a name.
_PARAMETERS = frozenset({"required_parameter", "optional_parameter"})


def _bindings(source: Source, name: str) -> int:
    """How many declarations, parameters and imports bind ``name`` in the file (any scope)."""
    return _facts(source).bindings.get(name, 0)


def _bound_name(node: Any) -> Any | None:
    """The name node a declaration, parameter, pattern or import binds, if any."""
    kind = node.type
    if kind == "import_specifier":
        return node.child_by_field_name("alias") or node.child_by_field_name("name")
    if kind == "namespace_import":
        return node.named_children[0] if node.named_children else None
    if kind in _NAMED_BINDINGS:
        return node.child_by_field_name("name")
    if kind in _PARAMETERS:
        return node.child_by_field_name("pattern")
    if kind == "shorthand_property_identifier_pattern":
        return node
    if kind == "identifier" and node.parent is not None and _binds(node):
        return node
    return None


@dataclass(frozen=True)
class _Facts:
    """One walk of a file: members by name, binding counts, declarators by name."""

    members: dict[str, list[Any]]
    bindings: dict[str, int]
    declarators: dict[str, list[Any]]


_FACTS_MAX = 64
_FACTS: OrderedDict[int, tuple[Source, _Facts]] = OrderedDict()
_FACTS_LOCK = threading.Lock()


def _facts(source: Source) -> _Facts:
    key = id(source)
    with _FACTS_LOCK:
        hit = _FACTS.get(key)
        if hit is not None and hit[0] is source:
            _FACTS.move_to_end(key)
            return hit[1]
    members: dict[str, list[Any]] = {}
    bindings: dict[str, int] = {}
    declarators: dict[str, list[Any]] = {}
    for node in _walk(source.root):
        if node.type in _MEMBER_TYPES:
            name = node.child_by_field_name("name") or node.child_by_field_name(
                "property"
            )
            if name is not None:
                members.setdefault(_member_name(source, name), []).append(node)
        if node.type == "variable_declarator":
            target = node.child_by_field_name("name")
            for part in _walk(target) if target is not None else ():
                if part.type in ("identifier", "shorthand_property_identifier_pattern"):
                    declarators.setdefault(source.text(part), []).append(node)
        bound = _bound_name(node)
        if bound is not None and bound.type in _NAME_NODES:
            text = source.text(bound)
            bindings[text] = bindings.get(text, 0) + 1
    found = _Facts(members, bindings, declarators)
    with _FACTS_LOCK:
        _FACTS[key] = (source, found)
        while len(_FACTS) > _FACTS_MAX:
            _FACTS.popitem(last=False)
    return found


_NAME_NODES = frozenset(
    {"identifier", "type_identifier", "shorthand_property_identifier_pattern"}
)
#: Parents in which a bare identifier is itself a binding.
_BINDING_PARENTS = frozenset(
    {"formal_parameters", "import_clause", "array_pattern", "rest_pattern"}
)
#: ``(parent, field)`` in which an identifier is a binding.
_BINDING_FIELDS = frozenset(
    {
        ("arrow_function", "parameter"),
        ("pair_pattern", "value"),
        ("assignment_pattern", "left"),
        ("catch_clause", "parameter"),
    }
)


def _binds(node: Any) -> bool:
    parent = node.parent.type
    return parent in _BINDING_PARENTS or (parent, _field(node)) in _BINDING_FIELDS


def _field(node: Any) -> str | None:
    parent = node.parent
    for index, child in enumerate(parent.children):
        if child == node:
            found = parent.field_name_for_child(index)
            return None if found is None else str(found)
    return None  # pragma: no cover - a node is always among its parent's children


def _resolve_member(reader: SourceReader, source: Source, value: Any) -> _Step:
    obj = value.child_by_field_name("object")
    prop = value.child_by_field_name("property")
    if obj is None or prop is None or obj.type != "identifier":
        return "a member path the index cannot follow"
    root = source.text(obj)
    if root in source.classes or root in source.module_values:
        return "a member of a local value, not a class the index can follow"
    if root in source.named_imports:
        spec = source.named_imports[root][0]
        if not spec.startswith(("./", "../")):
            return None  # ``React.Component`` with a named package import
        return "a member of an imported value the index cannot follow"
    if root not in source.module_bindings:
        return "a member path of an identifier not declared or imported"
    module = source.module_bindings[root]
    if module is None:
        return "a member of a module the index cannot follow"
    if not module.startswith(("./", "../")):
        return None  # a package namespace: a known external class
    return _imported_class(reader, source.rel, module, source.text(prop), 0)


def _imported_class(
    reader: SourceReader, from_rel: str, spec: str, name: str, hops: int
) -> _Step:
    """The class ``name`` exported by the relative module ``spec``."""
    target = reader.resolve_module(from_rel, spec)
    if target is None:
        return "an import that does not resolve to one project file"
    other = reader.read(target)
    if other is None or other.has_error:
        return "an import whose file could not be parsed"
    found = other.classes.get(name) or []
    if name in other.exported_values:
        if len(found) == 1:
            return other, found[0]
        return "an import that is not one class declaration"
    if hops >= _CHAIN_MAX:
        return "an import whose re-exports are too deep to follow"
    sources = _reexport_sources(other, name)
    if len(sources) == 1:
        return _imported_class(reader, target, sources[0][0], sources[0][1], hops + 1)
    if found and len(found) == 1 and name not in other.named_imports:
        return other, found[0]  # ``class X {}`` with a separate ``export { X }``
    return "an import that does not resolve to one project class"


def _reexport_sources(source: Source, name: str) -> list[tuple[str, str]]:
    """``(module, original name)`` for every ``export ... from`` that may pass ``name``."""
    found: list[tuple[str, str]] = []
    for node in source.root.named_children:
        if node.type != "export_statement":
            continue
        spec_node = node.child_by_field_name("source")
        if spec_node is None:
            continue
        text = source.text(spec_node)
        spec = text[1:-1] if len(text) >= 2 else ""
        clauses = [c for c in node.named_children if c.type == "export_clause"]
        if not clauses:
            if not any(c.type == "namespace_export" for c in node.named_children):
                found.append((spec, name))  # ``export * from``
            continue
        for item in clauses[0].named_children:
            if item.type != "export_specifier":
                continue
            original = item.child_by_field_name("name")
            alias = item.child_by_field_name("alias")
            exported = alias if alias is not None else original
            if exported is not None and source.text(exported) == name:
                found.append((spec, source.text(original)))
    return found


def _walk(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(reversed(node.children))
    return found


__all__ = [
    "DYNAMIC_SUPERTYPE_REASON",
    "KNOWN_GLOBALS",
    "SupertypeFinding",
    "dynamic_supertype",
    "dynamic_supertype_hint",
    "python_project_tops",
    "supertype_outcome",
]
