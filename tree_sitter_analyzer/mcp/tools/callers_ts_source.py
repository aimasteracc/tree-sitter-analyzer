"""PR-3: JS/TS class facts read from source, never from inheritance edges.

``callers_graph_bindings`` drops a ``this.m()`` site bound to the enclosing
class's own ``m`` only when the target's class cannot be reached through that
``this``. The inheritance edges in the index are not trusted for that: a missing
``extends`` edge (an unresolved or a generic supertype, #1880) would make a
subclass look unrelated. Everything here is read from the source files, and any
shape that is not understood answers "cannot prove":

* :func:`this_is_method_receiver` -- the call's ``this`` is the receiver of a
  non-static method declared directly in the class body of ``class C``: the
  only functions crossed on the way up are arrow functions (lexical ``this``);
  a ``function`` expression, a nested class, a field initializer or an object
  literal method in between binds another ``this``;
* :func:`chain_avoids` -- the target class's whole ``extends`` chain, resolved
  name by name (same file, or a named import from a relative module), never
  reaches ``C``; an ``extends`` value that is not a plain name (``mixin(B)``,
  ``ns.B``), an import that cannot be resolved to one file, a name declared twice
  or a chain longer than :data:`_CHAIN_MAX` fails;
* :func:`class_escapes` -- the target class is used as a value somewhere in the
  project (passed, stored, ``T.prototype``, aliased on import or export, default
  exported, read from a namespace object by name): the TS-handbook
  ``applyMixins(D, [T])`` pattern copies ``T``'s methods onto a subclass of
  ``C`` without naming them, so such a class keeps the site.
"""

from __future__ import annotations

import os
import posixpath
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .evidence_file_cache import FILE_CACHE, StatKey

#: Grammar per JS/TS source suffix.
GRAMMARS = {
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}
JSTS_SUFFIXES = tuple(GRAMMARS)
_CLASS_TYPES = frozenset({"class_declaration", "abstract_class_declaration", "class"})
#: Functions that bind their own ``this`` (or leave the method body).
_THIS_BOUNDARIES = frozenset(
    {
        "function_expression",
        "function_declaration",
        "generator_function",
        "generator_function_declaration",
        "function",
        "class_static_block",
        "public_field_definition",
        "field_definition",
        "program",
        *_CLASS_TYPES,
    }
)
#: Module specifier suffixes tried for an extensionless relative import, in order.
_RESOLVE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
#: ESM-style ``./x.js`` imports in TS resolve to the TS source first.
_JS_TO_TS = {
    ".js": (".ts", ".tsx", ".js"),
    ".mjs": (".mts", ".mjs"),
    ".cjs": (".cts", ".cjs"),
    ".jsx": (".tsx", ".jsx"),
}
#: Assertion matchers whose class argument is only the right side of ``instanceof``.
_INSTANCEOF_MATCHERS = frozenset(
    {"toBeInstanceOf", "toThrow", "toThrowError", "instanceOf"}
)
#: Steps followed along one ``extends`` chain before giving up.
_CHAIN_MAX = 32
#: Files containing the class name that the escape scan reads before giving up.
_ESCAPE_FILES_MAX = 400
_PARSED_MAX = 128
_PARSED: OrderedDict[tuple[str, StatKey], Source | None] = OrderedDict()
_PARSED_LOCK = threading.Lock()


@dataclass(frozen=True)
class Source:
    """One parsed JS/TS file."""

    rel: str
    data: bytes
    root: Any
    classes: dict[str, list[Any]] = field(default_factory=dict)
    #: local name -> (module specifier, imported name) for ``import { a as b }``.
    named_imports: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: local names bound to a whole module (``import * as ns``, default, require)
    #: -> the module specifier (None when not a string literal).
    module_bindings: dict[str, str | None] = field(default_factory=dict)
    #: The grammar reported a syntax error: only the escape scan reads such a file.
    has_error: bool = False
    #: Value names declared at module level (class, function, enum, const/let/var).
    module_values: frozenset[str] = frozenset()
    #: The subset declared by ``export <declaration>`` (a module's own export of a
    #: name wins over ``export *`` and cannot coexist with another export of it).
    exported_values: frozenset[str] = frozenset()
    #: Names passed on by ``export ... from`` (``*`` for a star export).
    reexports: frozenset[str] = frozenset()

    def text(self, node: Any) -> str:
        return self.data[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def one_class(self, name: str) -> Any | None:
        found = self.classes.get(name) or []
        return found[0] if len(found) == 1 else None


def clear_parsed() -> None:
    """Forget the memoized parses (tests)."""
    with _PARSED_LOCK:
        _PARSED.clear()


class SourceReader:
    """Per-query reader: parsed files plus the stat evidence of every read."""

    def __init__(self, project_root: str) -> None:
        self.root = project_root
        self.stamps: dict[str, StatKey | None] = {}
        self._sources: dict[str, Source | None] = {}

    def read(self, rel: str) -> Source | None:
        if rel not in self._sources:
            self._sources[rel] = self._load(rel)
        return self._sources[rel]

    def _load(self, rel: str) -> Source | None:
        grammar = GRAMMARS.get(os.path.splitext(rel)[1].lower())
        if grammar is None:
            return None
        found = FILE_CACHE.read_stamped(os.path.join(self.root, rel))
        if found is None:
            return None
        data, stamp = found
        self.stamps[rel] = stamp
        key = (rel, stamp) if stamp is not None else None
        if key is not None:
            with _PARSED_LOCK:
                if key in _PARSED:
                    _PARSED.move_to_end(key)
                    return _PARSED[key]
        parsed = _parse(rel, data, grammar)
        if key is not None:
            with _PARSED_LOCK:
                _PARSED[key] = parsed
                while len(_PARSED) > _PARSED_MAX:
                    _PARSED.popitem(last=False)
        return parsed

    def resolve_module(self, from_rel: str, spec: str) -> str | None:
        """The one project file a relative module specifier names, else None."""
        if not spec.startswith(("./", "../")):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(from_rel), spec))
        if base.startswith("../") or base == "..":
            return None
        stem, ext = posixpath.splitext(base)
        if ext in _JS_TO_TS:
            candidates = [stem + suffix for suffix in _JS_TO_TS[ext]]
        elif ext in GRAMMARS:
            candidates = [base]
        else:
            candidates = [base + suffix for suffix in _RESOLVE_SUFFIXES] + [
                f"{base}/index{suffix}" for suffix in _RESOLVE_SUFFIXES
            ]
        existing = [
            path
            for path in candidates
            if os.path.isfile(os.path.join(self.root, *path.split("/")))
        ]
        return existing[0] if len(existing) == 1 else None


def _parse(rel: str, data: bytes, grammar: str) -> Source | None:
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely(grammar)
        if parser is None:
            return None
        tree = parser.parse(data)
    except Exception:  # noqa: BLE001 — a grammar failure is "cannot prove"
        return None
    root = tree.root_node
    source = Source(rel, data, root)
    classes: dict[str, list[Any]] = {}
    imports: dict[str, tuple[str, str]] = {}
    modules: dict[str, str | None] = {}
    values: set[str] = set()
    exported: set[str] = set()
    reexports: set[str] = set()
    for node in _walk(root):
        kind = node.type
        if kind in _CLASS_TYPES:
            name = node.child_by_field_name("name")
            if name is not None:
                classes.setdefault(source.text(name), []).append(node)
        if _module_level(node):
            declared = _declared_names(source, node)
            values.update(declared)
            if node.parent is not None and node.parent.type == "export_statement":
                exported.update(declared)
        if kind == "import_statement":
            _collect_import(source, node, imports, modules)
        elif kind == "export_statement" and node.child_by_field_name("source"):
            reexports.update(_reexported_names(source, node))
        elif kind == "variable_declarator" and _is_require(source, node):
            name = node.child_by_field_name("name")
            if name is not None and name.type == "identifier":
                modules[source.text(name)] = None
    return Source(
        rel,
        data,
        root,
        classes,
        imports,
        modules,
        has_error=bool(root.has_error),
        module_values=frozenset(values),
        exported_values=frozenset(exported),
        reexports=frozenset(reexports),
    )


#: Module-level declarations that bind a value name.
_VALUE_DECLARATIONS = frozenset(
    {
        *_CLASS_TYPES,
        "function_declaration",
        "generator_function_declaration",
        "enum_declaration",
        "lexical_declaration",
        "variable_declaration",
    }
)


def _module_level(node: Any) -> bool:
    if node.type not in _VALUE_DECLARATIONS:
        return False
    parent = node.parent
    if parent is not None and parent.type == "export_statement":
        parent = parent.parent
    return parent is not None and parent.type == "program"


def _declared_names(source: Source, node: Any) -> list[str]:
    if node.type in ("lexical_declaration", "variable_declaration"):
        names = []
        for item in node.named_children:
            name = (
                item.child_by_field_name("name")
                if item.type == "variable_declarator"
                else None
            )
            if name is not None and name.type == "identifier":
                names.append(source.text(name))
        return names
    name = node.child_by_field_name("name")
    return [] if name is None else [source.text(name)]


def _reexported_names(source: Source, node: Any) -> list[str]:
    """Names an ``export ... from`` statement passes on; ``*`` for a star export."""
    clauses = [c for c in node.named_children if c.type == "export_clause"]
    if not clauses:
        return ["*"]
    names: list[str] = []
    for item in clauses[0].named_children:
        if item.type != "export_specifier":
            continue
        for key in ("name", "alias"):
            part = item.child_by_field_name(key)
            if part is not None:
                names.append(source.text(part))
    return names


def _collect_import(
    source: Source,
    node: Any,
    imports: dict[str, tuple[str, str]],
    modules: dict[str, str | None],
) -> None:
    spec_node = node.child_by_field_name("source")
    spec = _string_value(source, spec_node)
    for clause in node.named_children:
        if clause.type != "import_clause":
            continue
        for part in clause.named_children:
            if part.type == "identifier":
                modules[source.text(part)] = spec  # default import
            elif part.type == "namespace_import":
                for ident in part.named_children:
                    if ident.type == "identifier":
                        modules[source.text(ident)] = spec
            elif part.type == "named_imports" and spec is not None:
                for item in part.named_children:
                    if item.type != "import_specifier":
                        continue
                    name = item.child_by_field_name("name")
                    alias = item.child_by_field_name("alias")
                    if name is None:
                        continue
                    local = source.text(alias if alias is not None else name)
                    imports[local] = (spec, source.text(name))


def _is_require(source: Source, node: Any) -> bool:
    value = node.child_by_field_name("value")
    while value is not None and value.type in ("await_expression",):
        value = value.named_children[0] if value.named_children else None
    if value is None or value.type != "call_expression":
        return False
    func = value.child_by_field_name("function")
    return func is not None and source.text(func) in ("require", "import")


def _string_value(source: Source, node: Any) -> str | None:
    if node is None or node.type != "string":
        return None
    text = source.text(node)
    return text[1:-1] if len(text) >= 2 else None


def _walk(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(reversed(node.children))
    return found


def this_is_method_receiver(
    source: Source, line: int, name: str, class_name: str, method_line: int
) -> bool:
    """The one ``this.name(...)`` call on ``line`` uses the ``this`` of a method of ``class_name``.

    The method is non-static, starts on ``method_line`` and sits directly in the
    body of the single class declared as ``class_name`` in the file.
    """
    if source.has_error:
        return False
    calls = [
        node
        for node in _walk(source.root)
        if node.type == "call_expression"
        and node.start_point[0] + 1 == line
        and _is_this_member(source, node.child_by_field_name("function"), name)
    ]
    if len(calls) != 1:
        return False
    method = _enclosing_method(calls[0])
    if method is None or method.start_point[0] + 1 != method_line:
        return False
    if any(child.type == "static" for child in method.children):
        return False
    body = method.parent
    owner = body.parent if body is not None else None
    if body is None or body.type != "class_body" or owner is None:
        return False
    return owner.type in _CLASS_TYPES and owner == source.one_class(class_name)


def _is_this_member(source: Source, node: Any, name: str) -> bool:
    if node is None or node.type != "member_expression":
        return False
    obj = node.child_by_field_name("object")
    prop = node.child_by_field_name("property")
    return (
        obj is not None
        and obj.type == "this"
        and prop is not None
        and prop.type == "property_identifier"
        and source.text(prop) == name
    )


def _enclosing_method(node: Any) -> Any | None:
    current = node.parent
    while current is not None and current.type not in _THIS_BOUNDARIES:
        if current.type == "method_definition":
            return current
        current = current.parent
    return None


def chain_avoids(
    reader: SourceReader, rel: str, class_name: str, forbidden: tuple[str, str]
) -> bool:
    """``class_name``'s whole ``extends`` chain (from source) never reaches ``forbidden``."""
    current: tuple[str, str] = (rel, class_name)
    seen = {current}
    for _ in range(_CHAIN_MAX):
        if current == forbidden:
            return False
        source = reader.read(current[0])
        if source is None or source.has_error:
            return False
        node = source.one_class(current[1])
        if node is None:
            return False
        parent = _extends_name(source, node)
        if parent is None:
            return False
        if parent == "":
            return True  # a root class: nothing above it
        resolved = _resolve_class(reader, source, parent)
        if resolved is None or resolved in seen:
            return False
        seen.add(resolved)
        current = resolved
    return False


def _extends_name(source: Source, node: Any) -> str | None:
    """``""`` for no ``extends``; the plain base name; None for any other shape."""
    heritage = [
        child for child in node.named_children if child.type == "class_heritage"
    ]
    if not heritage:
        return ""
    if len(heritage) != 1:
        return None
    clauses = [c for c in heritage[0].named_children if c.type == "extends_clause"]
    if clauses:
        if len(clauses) != 1:
            return None
        values = [
            child
            for index, child in enumerate(clauses[0].children)
            if clauses[0].field_name_for_child(index) == "value"
        ]
        value = values[0] if len(values) == 1 else None
    else:
        # JavaScript grammar: ``class_heritage`` holds the expression directly.
        exprs = heritage[0].named_children
        value = exprs[0] if len(exprs) == 1 else None
    if value is None or value.type != "identifier":
        return None
    return source.text(value)


def _resolve_class(
    reader: SourceReader, source: Source, name: str
) -> tuple[str, str] | None:
    local = source.classes.get(name) or []
    imported = source.named_imports.get(name)
    if local and imported is None:
        return (source.rel, name) if len(local) == 1 else None
    if imported is None or local or name in source.module_bindings:
        return None
    spec, original = imported
    target = reader.resolve_module(source.rel, spec)
    if target is None:
        return None
    other = reader.read(target)
    if other is None or other.has_error or other.one_class(original) is None:
        return None
    return (target, original)


def class_escapes(
    reader: SourceReader, files: list[str], decl_file: str, class_name: str
) -> bool:
    """The class ``class_name`` of ``decl_file`` may be used as a value in ``files``.

    A file where the name provably binds another declaration (its own module-level
    class, or a named import of a module that declares its own class of that name)
    is read for namespace-object accesses only. An unreadable file escapes.
    """
    needle = class_name.encode("utf-8")
    hits: list[str] = []
    for rel in files:
        found = FILE_CACHE.read_stamped(os.path.join(reader.root, rel))
        if found is None:
            return True
        if needle in found[0]:
            hits.append(rel)
    if len(hits) > _ESCAPE_FILES_MAX:
        return True
    for rel in hits:
        source = reader.read(rel)
        if source is None:
            return True
        ours = _may_bind(reader, source, class_name, decl_file)
        namespaces = frozenset(
            local
            for local, spec in source.module_bindings.items()
            if _module_may_export(reader, rel, spec, class_name, decl_file)
        )
        if _escapes_in(source, class_name, identifiers=ours, namespaces=namespaces):
            return True
    return False


def _may_bind(reader: SourceReader, source: Source, name: str, decl_file: str) -> bool:
    """Whether ``name`` in ``source`` may denote the class declared in ``decl_file``."""
    if source.rel == decl_file:
        return True
    imported = source.named_imports.get(name)
    if imported is None:
        # Its own module-level declaration shadows every other one of the name.
        return name not in source.module_values
    if name in source.module_values:
        return True  # declared and imported: cannot tell which one a use means
    return _module_may_export(reader, source.rel, imported[0], imported[1], decl_file)


def _module_may_export(
    reader: SourceReader, from_rel: str, spec: str | None, name: str, decl_file: str
) -> bool:
    """Whether the module ``spec`` may export ``decl_file``'s class as ``name``.

    Only a resolved project module that declares ``name`` itself, and neither
    imports nor re-exports it, is known to export something else.
    """
    target = None if spec is None else reader.resolve_module(from_rel, spec)
    if target is None or target == decl_file:
        return True
    other = reader.read(target)
    if other is None:
        return True
    if name in other.exported_values:
        return False  # the module's own declaration of the name
    if other.has_error:
        return True
    if "*" in other.reexports or name in other.reexports:
        return True
    if name in other.named_imports or name in other.module_bindings:
        return True
    return name not in other.module_values


def _escapes_in(
    source: Source,
    name: str,
    *,
    identifiers: bool = True,
    namespaces: frozenset[str] | None = None,
) -> bool:
    """Value uses of ``name`` (identifiers only when ``identifiers``) and reads of it
    from the module objects in ``namespaces`` (all of them when None)."""
    if namespaces is None:
        namespaces = frozenset(source.module_bindings)
    for node in _walk(source.root):
        kind = node.type
        if kind == "identifier" and source.text(node) == name:
            if identifiers and (_in_error(node) or not _passive_use(source, node)):
                return True
        elif kind == "shorthand_property_identifier" and source.text(node) == name:
            if identifiers:
                return True
        elif kind == "property_identifier" and source.text(node) == name:
            if _namespace_member(source, node, namespaces) and (
                _in_error(node) or not _passive_use(source, node.parent)
            ):
                return True
        elif kind == "string_fragment" and source.text(node) == name:
            if _namespace_subscript(source, node, namespaces):
                return True
    return False


def _in_error(node: Any) -> bool:
    current = node.parent
    while current is not None:
        if current.type == "ERROR" or current.is_missing:
            return True
        current = current.parent
    return False


def _field(node: Any) -> str | None:
    parent = node.parent
    if parent is None:
        return None
    for index, child in enumerate(parent.children):
        if child == node:
            found = parent.field_name_for_child(index)
            return None if found is None else str(found)
    return None


def _passive_use(source: Source, node: Any) -> bool:
    """A use of the class that cannot hand its prototype to other code."""
    parent = node.parent
    if parent is None:
        return False
    kind, where = parent.type, _field(node)
    if kind in _CLASS_TYPES and where == "name":
        return True
    if kind == "new_expression" and where == "constructor":
        return True
    if kind in ("extends_clause", "class_heritage"):
        return True
    if kind == "member_expression" and where == "object":
        prop = parent.child_by_field_name("property")
        return prop is not None and source.text(prop) != "prototype"
    if kind == "binary_expression" and where == "right":
        operator = parent.child_by_field_name("operator")
        return operator is not None and source.text(operator) == "instanceof"
    if kind in ("import_specifier", "export_specifier"):
        return parent.child_by_field_name("alias") is None
    if kind == "import_clause":
        return True  # a default import binding: its own uses are scanned by name
    if kind == "arguments" and _instanceof_matcher(source, parent.parent):
        return True
    current = parent
    while current is not None:
        if current.type == "type_query":
            return True
        current = current.parent
    return False


def _instanceof_matcher(source: Source, call: Any) -> bool:
    """``expect(x).toBeInstanceOf(T)`` and friends: test matchers that only run ``instanceof``."""
    if call is None or call.type != "call_expression":
        return False
    func = call.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return False
    prop = func.child_by_field_name("property")
    return prop is not None and source.text(prop) in _INSTANCEOF_MATCHERS


def _namespace_member(source: Source, node: Any, namespaces: frozenset[str]) -> bool:
    parent = node.parent
    if parent is None or parent.type != "member_expression":
        return False
    if _field(node) != "property":
        return False
    obj = parent.child_by_field_name("object")
    return (
        obj is not None and obj.type == "identifier" and source.text(obj) in namespaces
    )


def _namespace_subscript(source: Source, node: Any, namespaces: frozenset[str]) -> bool:
    string = node.parent
    access = string.parent if string is not None else None
    if access is None or access.type != "subscript_expression":
        return False
    obj = access.child_by_field_name("object")
    return (
        obj is not None and obj.type == "identifier" and source.text(obj) in namespaces
    )


__all__ = [
    "GRAMMARS",
    "JSTS_SUFFIXES",
    "Source",
    "SourceReader",
    "chain_avoids",
    "class_escapes",
    "clear_parsed",
    "this_is_method_receiver",
]
