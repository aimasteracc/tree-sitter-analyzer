"""Trust classes of a SCIP-resolved symbol, relative to the query target (TS / JS only).

A call site that SCIP resolves to a symbol other than the target is evidence
that the site does not call the target only when the resolution cannot hide
the target at run time. The SCIP spike (hand check of 55 "different symbol"
sites, 5 of them wrong) fixed the classes that may be trusted:

========================  =======  ==============================================
class                     trusted  meaning
========================  =======  ==============================================
``target``                yes      the symbol is the target itself
``other_function``        yes      a bare call bound lexically to another project
                                   function
``subclass_override``     yes      a member of a subclass of the target's class
                                   (an override; the target's own callers bind to
                                   the target, not to this symbol)
``other_class_nominal``   yes      a member of an unrelated project class that
                                   declares a private / ``#private`` / protected
                                   member, so no other class can stand in for it
``external_core``         yes      a member of a core ECMAScript value type
                                   (``String``, ``Array``, ``Map`` ...)
``other_class``           no       an unrelated class without such a member:
                                   structural typing lets the target's class in
``structural``            no       an interface, type literal or type alias
``external_iface``        no       lib.dom / ``@types`` / any other external type
``external_function``     no       an external function
``ambient_decl``          no       declared in a ``.d.ts`` (it can shadow a JS
                                   implementation)
``dispatch_super``        no       a supertype member the target overrides or
                                   implements: a call to it may dispatch here
``same_class_other``      no       another member of the target's class
``via_variable``          no       a variable or property holding a function
``local``                 no       a document-local symbol (local alias)
========================  =======  ==============================================

Python is out of scope: scip-python resolves a union receiver to its first
member only, so no "different symbol" is trusted there.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from . import callers_scip_symbols as sym
from .callers_scip_index import KIND_CLASS, ScipIndex

TARGET = "target"
TRUSTED_OTHER = frozenset(
    {"other_function", "subclass_override", "other_class_nominal", "external_core"}
)
#: Core ECMAScript value types (members of lib.es*.d.ts owners with these names).
TS_CORE = frozenset(
    {
        "String", "Number", "Boolean", "BigInt", "Symbol", "Array", "ReadonlyArray",
        "RegExp", "Math", "JSON", "Date", "Map", "ReadonlyMap", "Set", "ReadonlySet",
        "WeakMap", "WeakSet", "Promise", "Object", "ObjectConstructor",
        "ArrayConstructor", "StringConstructor", "NumberConstructor",
        "PromiseConstructor", "Uint8Array", "Int8Array", "Uint16Array",
        "Int32Array", "Uint32Array", "Float64Array", "ArrayBuffer", "DataView",
        "Function", "CallableFunction", "Error", "Console",
    }
)  # fmt: skip
AMBIENT_SUFFIXES = (".d.ts", ".d.mts", ".d.cts")
_ACCESS_MODIFIER = re.compile(r"\s*(?:private|protected)\b")
_CLASS_DOC = re.compile(
    r"^```(?:ts|typescript|js|javascript)\s*\n\s*(?:abstract\s+)?class\b"
)

SourceLines = Callable[[str], list[str]]


@dataclass
class TypeGraph:
    """Supertype queries over one index (memoized; the index is immutable)."""

    index: ScipIndex
    _ancestors: dict[str, frozenset[str]] = field(default_factory=dict)
    _types: tuple[str, ...] | None = None

    def parents(self, type_symbol: str) -> frozenset[str]:
        info = self.index.symbols.get(type_symbol)
        if info is None:
            return frozenset()
        return frozenset(r.symbol for r in info.relationships if r.is_implementation)

    def ancestors(self, type_symbol: str) -> frozenset[str]:
        found = self._ancestors.get(type_symbol)
        if found is not None:
            return found
        seen: set[str] = set()
        todo = [type_symbol]
        while todo:
            for parent in self.parents(todo.pop()):
                if parent not in seen and parent != type_symbol:
                    seen.add(parent)
                    todo.append(parent)
        result = frozenset(seen)
        self._ancestors[type_symbol] = result
        return result

    def project_types(self) -> tuple[str, ...]:
        if self._types is None:
            self._types = tuple(
                s for s in self.index.defined_in if sym.last_kind(s) == "type"
            )
        return self._types


@dataclass(frozen=True)
class TargetContext:
    """The target symbols and the types around them that the trust rules read."""

    targets: frozenset[str]
    #: Members the targets override or implement (transitively).
    supers: frozenset[str]
    classes: frozenset[str]
    class_ancestors: frozenset[str]
    class_descendants: frozenset[str]


def target_context(graph: TypeGraph, targets: frozenset[str]) -> TargetContext:
    index = graph.index
    supers: set[str] = set()
    todo = list(targets)
    while todo:
        info = index.symbols.get(todo.pop())
        for rel in info.relationships if info else ():
            if (rel.is_implementation or rel.is_reference) and rel.symbol not in (
                supers | targets
            ):
                supers.add(rel.symbol)
                todo.append(rel.symbol)
    classes = frozenset(o for o in (sym.owner(t) for t in targets) if o)
    ancestors: set[str] = set()
    for cls in classes:
        ancestors |= graph.ancestors(cls)
    descendants = frozenset(
        t
        for t in graph.project_types()
        if t not in classes and graph.ancestors(t) & classes
    )
    return TargetContext(
        targets, frozenset(supers), classes, frozenset(ancestors), descendants
    )


def _ambient(index: ScipIndex, symbol: str) -> bool:
    return any(f.endswith(AMBIENT_SUFFIXES) for f in index.defined_in.get(symbol, ()))


def _builtin_owner(owner: str) -> bool:
    parsed = sym.parse(owner)
    if not parsed:
        return False
    header = parsed[0]
    return (len(header) > 2 and header[2] == "typescript") or "`lib." in owner


def _is_class(graph: TypeGraph, owner: str) -> bool:
    info = graph.index.symbols.get(owner)
    if info is None:
        return False
    if info.kind == KIND_CLASS:
        return True
    return info.kind == 0 and bool(_CLASS_DOC.match(info.documentation))


def nominal(graph: TypeGraph, cls: str, lines_of: SourceLines) -> bool:
    """A TS class that declares a private / ``#private`` / protected member.

    Only a class defined in exactly one file is examined; anything else is
    reported as not nominal (the conservative answer).
    """
    files = graph.index.defined_in.get(cls, ())
    if len(files) != 1:
        return False
    path = files[0]
    lines = lines_of(path)
    for occ in graph.index.documents.get(path, ()):
        if not occ.is_definition or occ.symbol == cls or not occ.symbol.startswith(cls):
            continue
        if sym.owner(occ.symbol) != cls:
            continue
        name = sym.last_name(occ.symbol) or ""
        if name.startswith("#"):
            return True
        if occ.line < len(lines) and _ACCESS_MODIFIER.match(lines[occ.line]):
            return True
    return False


def classify(
    graph: TypeGraph, symbol: str, ctx: TargetContext, lines_of: SourceLines
) -> str:
    """The trust class of an occurrence resolved to ``symbol`` (see module doc)."""
    if symbol in ctx.targets:
        return TARGET
    if sym.is_local(symbol):
        return "local"
    if symbol in ctx.supers:
        return "dispatch_super"
    index = graph.index
    owner = sym.owner(symbol)
    if _ambient(index, symbol) or (owner is not None and _ambient(index, owner)):
        return "ambient_decl"
    if owner is None:
        if symbol not in index.defined_in:
            return "external_function"
        return "other_function" if sym.last_kind(symbol) == "method" else "via_variable"
    if owner in ctx.class_ancestors:
        return "dispatch_super"
    if owner in ctx.classes:
        return "same_class_other"
    if owner in ctx.class_descendants:
        return "subclass_override"
    if owner not in index.defined_in:
        core = _builtin_owner(owner) and sym.last_name(owner) in TS_CORE
        return "external_core" if core else "external_iface"
    if not _is_class(graph, owner):
        return "structural"
    if any(
        a not in index.defined_in and not _builtin_owner(a)
        for a in graph.ancestors(owner)
    ):
        return "other_class"
    return "other_class_nominal" if nominal(graph, owner, lines_of) else "other_class"


__all__ = [
    "TARGET",
    "TRUSTED_OTHER",
    "TS_CORE",
    "TargetContext",
    "TypeGraph",
    "classify",
    "nominal",
    "target_context",
]
