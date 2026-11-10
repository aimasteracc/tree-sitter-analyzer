"""#1937: a C# method reached through a supertype leaves no call edge naming it.

.. code-block:: csharp

    public abstract class Base {
        internal virtual bool Has(int x) { return false; }
        public bool Check(int x) { return Has(x); }   // reaches Derived.Has
    }
    public class Derived : Base { internal override bool Has(int x) => true; }

``Derived.Has`` answered ``complete`` with 0 callers. Three kinds of method are
reached through a supertype:

* an ``override`` (also ``sealed override``) -- through its base class, or by
  the BCL when the base class is outside the project
  (``KeyedCollection<,>.GetKeyForItem``, ``object.ToString``);
* an explicit interface implementation (``void IRun.Run()``) -- only through
  the interface;
* a ``public`` instance method of a class, struct or record that lists an
  interface declaring the same name -- an implicit interface implementation
  (``Dispose`` of an ``IDisposable``). Since a base list does not say which
  names are classes, every entry of it must resolve.

Such a method lets ``complete`` through only when every supertype that matters
resolves, from source, to a type declared in the project's C# files (for an
``override`` or explicit implementation the whole transitive closure; for an
implicit implementation the interfaces of the declaring type, transitively), a
type in it declares the name, and every call edge named like it is bound to
this declaration or outside the project (the Java gate's check). A method that
overrides and implements nothing passes. A record's ``Equals`` /
``GetHashCode`` / ``ToString`` / ``PrintMembers`` / ``Deconstruct`` are called
by its synthesized members and never pass.

Names resolve in C#'s order, from source: nested types of the enclosing types
(also those they inherit), then each enclosing namespace from the innermost
outward -- its types first, then its ``using`` directives. A level whose
``using`` directives could import an outside type of the name ends the search
(fail closed), as do aliases, ``global using`` names that are not project
types, generic arity mismatches, ambiguity and closures larger than
:data:`MAX_TYPES`. ``partial`` types are read in all their parts.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from .callers_override_common import (
    MAX_TYPES,
    OverrideProof,
    Parsed,
    ancestors,
    class_files,
    dispatch_proof,
    fail,
    finding,
    parse,
    unchecked,
    walk,
)
from .callers_supertypes import KOTLIN_OVERRIDE_VERB, SupertypeFinding
from .evidence_file_cache import FILE_CACHE

CSHARP_SUFFIXES = (".cs",)
#: Members of ``System.Object`` an ``override`` may redefine.
OBJECT_METHODS = frozenset({"ToString", "Equals", "GetHashCode", "Finalize"})
#: Members a record synthesizes and calls itself.
RECORD_METHODS = OBJECT_METHODS | {"PrintMembers", "Deconstruct"}
_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "record_declaration",
    }
)
_OVERRIDE = re.compile(r"\boverride\b")
#: ``(verb, hint lead)`` by how the method is reached through a supertype.
_OVERRIDES = (KOTLIN_OVERRIDE_VERB, "it is declared `override`")
_EXPLICIT = ("explicitly implements", "it explicitly implements an interface member")
_IMPLICIT = ("may implement", "it may implement an interface member")


def csharp_row_finding(
    project_root: str, rel: str, line: int, bare: str, cache: Any
) -> tuple[str | None, SupertypeFinding | None]:
    """``(declaring type name, finding)`` of one C# declaration row."""
    text = FILE_CACHE.read_text(os.path.join(project_root, rel))
    if text is None:
        return None, unchecked(rel, "the declaring file could not be read")
    parsed = parse("csharp", text)
    if parsed is None:
        return None, unchecked(rel, "the declaring file could not be parsed")
    method = _method_at(parsed, line, bare)
    if method is None:
        lines = text.splitlines()
        if 0 < line <= len(lines) and _OVERRIDE.search(lines[line - 1]):
            return None, unchecked(
                rel, "its `override` declaration could not be located"
            )
        return None, None
    owner = _owner_type(method)
    if owner is None:
        if any(a.type == "ERROR" for a in ancestors(method)):
            return None, unchecked(rel, "its declaring type could not be parsed")
        return None, None
    name = _name_text(parsed, owner)
    modifiers = {parsed.text(c) for c in method.children if c.type == "modifier"}
    if "override" in modifiers:
        kind = _OVERRIDES
    elif any(c.type == "explicit_interface_specifier" for c in method.children):
        kind = _EXPLICIT
    else:
        kind = _IMPLICIT
    proof = _proof(cache, project_root, rel, parsed, owner, modifiers, kind, line, bare)
    if proof is None or proof.proved:
        return name, None
    verb, lead = kind
    return name, finding(bare, rel, line, name, proof.detail, verb=verb, lead=lead)


def _proof(
    cache: Any,
    project_root: str,
    rel: str,
    parsed: Parsed,
    owner: Any,
    modifiers: set[str],
    kind: tuple[str, str],
    line: int,
    bare: str,
) -> OverrideProof | None:
    """Whether the method is closed in the project; None when nothing applies."""
    overriding = kind is not _IMPLICIT
    if not overriding:
        if owner.type == "record_declaration" and bare in RECORD_METHODS:
            return fail(f"a record calls its `{bare}` from synthesized members")
        if (
            "public" not in modifiers
            or "static" in modifiers
            or owner.type == "interface_declaration"
        ):
            return None
    if kind is _OVERRIDES and bare in OBJECT_METHODS:
        return fail(
            f"it overrides `System.Object.{bare}`, declared outside the project"
        )
    if cache is None:
        return fail("the project index could not be read to resolve its supertypes")
    reader = _Reader(cache, project_root, {rel: parsed})
    start = reader.type_of(rel, owner)
    closure = reader.closure(start, interfaces_only=not overriding)
    if isinstance(closure, str):
        return fail(closure)
    if not any(reader.declares(t, bare) for t in closure):
        if overriding:
            return fail("no supertype in the project declares it")
        return None
    return dispatch_proof(cache, bare, rel, line, start.name)


def _owner_type(method: Any) -> Any | None:
    """The type whose body declares ``method``, through ``#if`` regions."""
    body = method.parent
    while body is not None and body.type.startswith("preproc"):
        body = body.parent
    if body is None or body.type != "declaration_list":
        return None
    owner = body.parent
    return owner if owner is not None and owner.type in _TYPES else None


def _members(body: Any) -> list[Any]:
    """Members of a type body, those inside ``#if`` regions included."""
    found: list[Any] = []
    stack = list(reversed(body.named_children))
    while stack:
        node = stack.pop()
        if node.type.startswith("preproc"):
            stack.extend(reversed(node.named_children))
        else:
            found.append(node)
    return found


def _name_text(parsed: Parsed, node: Any) -> str | None:
    name = node.child_by_field_name("name")
    return None if name is None else parsed.text(name)


def _method_at(parsed: Parsed, line: int, bare: str) -> Any | None:
    """The method declaration named ``bare`` whose header holds ``line``."""
    matches = []
    for node in walk(parsed.root):
        if node.type != "method_declaration":
            continue
        name = node.child_by_field_name("name")
        if name is None or parsed.text(name) != bare:
            continue
        if int(node.start_point[0]) + 1 <= line <= int(name.start_point[0]) + 1:
            matches.append(node)
    return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class _Type:
    file: str
    node: Any
    namespace: str
    path: tuple[str, ...]
    name: str
    arity: int

    @property
    def key(self) -> tuple[str, tuple[str, ...], str, int]:
        return (self.namespace, self.path, self.name, self.arity)

    @property
    def dotted(self) -> str:
        return ".".join(p for p in (self.namespace, *self.path, self.name) if p)


@dataclass(frozen=True)
class _Using:
    kind: str  # "ns" | "alias" | "static"
    value: str


def _arity(node: Any) -> int:
    params = next((c for c in node.children if c.type == "type_parameter_list"), None)
    if params is None:
        return 0
    return sum(1 for c in params.named_children if c.type == "type_parameter")


def _usings(parsed: Parsed, children: list[Any]) -> list[_Using]:
    found: list[_Using] = []
    for child in children:
        if child.type != "using_directive":
            continue
        kinds = {c.type for c in child.children}
        named = [c for c in child.named_children if c.type != "global"]
        if "=" in kinds:
            alias = named[0] if named else None
            found.append(_Using("alias", "" if alias is None else parsed.text(alias)))
            continue
        target = named[-1] if named else None
        value = "" if target is None else re.sub(r"\s+", "", parsed.text(target))
        found.append(_Using("static" if "static" in kinds else "ns", value))
    return found


def _levels(parsed: Parsed, node: Any) -> list[tuple[str, list[_Using]]]:
    """Namespace levels around ``node``, innermost first, with their usings."""
    decls = [a for a in ancestors(node) if a.type == "namespace_declaration"]
    root_children = list(parsed.root.children)
    scoped = next(
        (c for c in root_children if c.type == "file_scoped_namespace_declaration"),
        None,
    )
    outer: list[tuple[str, list[_Using]]] = []  # outermost first
    prefix = ""
    root_usings = root_children
    if scoped is not None:
        index = next(i for i, c in enumerate(root_children) if c.id == scoped.id)
        root_usings = root_children[:index]
        prefix = _ns_name(parsed, scoped)
        outer.extend(_expand("", prefix, _usings(parsed, root_children[index:])))
    for decl in reversed(decls):
        name = _ns_name(parsed, decl)
        body = decl.child_by_field_name("body")
        usings = _usings(parsed, list(body.children) if body is not None else [])
        outer.extend(_expand(prefix, name, usings))
        prefix = f"{prefix}.{name}" if prefix else name
    levels = list(reversed(outer))
    levels.append(("", _usings(parsed, root_usings)))
    return levels


def _expand(
    prefix: str, name: str, usings: list[_Using]
) -> list[tuple[str, list[_Using]]]:
    """``namespace B.C`` in ``A``: levels ``A.B`` (no usings), ``A.B.C``."""
    parts = name.split(".")
    found = []
    for count in range(1, len(parts) + 1):
        full = ".".join(p for p in (prefix, *parts[:count]) if p)
        found.append((full, usings if count == len(parts) else []))
    return found


def _ns_name(parsed: Parsed, decl: Any) -> str:
    name = decl.child_by_field_name("name")
    if name is None:
        name = next(
            (
                c
                for c in decl.named_children
                if c.type in {"identifier", "qualified_name"}
            ),
            None,
        )
    return "" if name is None else re.sub(r"\s+", "", parsed.text(name))


def _segments(parsed: Parsed, node: Any) -> tuple[list[tuple[str, int]], str] | None:
    """``A.B<int>`` -> ``([("A", 0), ("B", 1)], "")``; the second item is the
    alias of an ``x::`` prefix (``global`` included). None for other shapes."""
    if node.type == "identifier":
        return [(parsed.text(node), 0)], ""
    if node.type == "generic_name":
        ident = next((c for c in node.named_children if c.type == "identifier"), None)
        args = next(
            (c for c in node.named_children if c.type == "type_argument_list"), None
        )
        if ident is None or args is None:
            return None
        count = (
            len(args.named_children)
            or sum(1 for c in args.children if c.type == ",") + 1
        )
        return [(parsed.text(ident), count)], ""
    if node.type == "alias_qualified_name":
        alias = node.child_by_field_name("alias")
        name = node.child_by_field_name("name")
        inner = None if name is None else _segments(parsed, name)
        if alias is None or inner is None:
            return None
        return inner[0], parsed.text(alias)
    if node.type == "qualified_name":
        qualifier = node.child_by_field_name("qualifier")
        name = node.child_by_field_name("name")
        if qualifier is None or name is None:
            return None
        head, tail = _segments(parsed, qualifier), _segments(parsed, name)
        if head is None or tail is None or tail[1]:
            return None
        return head[0] + tail[0], head[1]
    return None


class _Reader:
    """Reads project C# files and resolves supertype names from source."""

    def __init__(self, cache: Any, project_root: str, seed: dict[str, Parsed]) -> None:
        self._cache = cache
        self._root = project_root
        self._parsed: dict[str, Parsed | None] = dict(seed)
        self._named: dict[str, list[_Type] | str] = {}
        self._closures: dict[Any, list[_Type] | str] = {}
        self._active: set[Any] = set()

    def _closure_memo(self, t: _Type) -> list[_Type] | str:
        if t.key not in self._closures:
            self._closures[t.key] = self.closure(t, interfaces_only=False)
        return self._closures[t.key]

    def parse(self, rel: str) -> Parsed | None:
        if rel not in self._parsed:
            text = FILE_CACHE.read_text(os.path.join(self._root, rel))
            self._parsed[rel] = None if text is None else parse("csharp", text)
        return self._parsed[rel]

    def type_of(self, rel: str, node: Any) -> _Type:
        parsed = self.parse(rel)
        assert parsed is not None  # noqa: S101 — only parsed files reach here
        path = tuple(
            _name_text(parsed, a) or ""
            for a in reversed(ancestors(node))
            if a.type in _TYPES
        )
        return _Type(
            rel,
            node,
            _levels(parsed, node)[0][0],
            path,
            _name_text(parsed, node) or "",
            _arity(node),
        )

    def named(self, name: str) -> list[_Type] | str:
        """Every project type declaration named ``name`` (partial parts apart)."""
        if name not in self._named:
            files = class_files(self._cache, "csharp", name)
            if isinstance(files, str):
                self._named[name] = files
                return files
            found: list[_Type] = []
            for rel in files:
                parsed = self.parse(rel)
                if parsed is None:
                    self._named[name] = "a candidate supertype file could not be parsed"
                    return self._named[name]
                found.extend(
                    self.type_of(rel, n)
                    for n in walk(parsed.root)
                    if n.type in _TYPES and _name_text(parsed, n) == name
                )
            self._named[name] = found
        return self._named[name]

    def parts(self, t: _Type) -> list[_Type] | str:
        named = self.named(t.name)
        if isinstance(named, str):
            return named
        found = [n for n in named if n.key == t.key]
        return found or [t]

    def declares(self, t: _Type, bare: str) -> bool:
        parts = self.parts(t)
        for part in parts if isinstance(parts, list) else [t]:
            parsed = self.parse(part.file)
            body = part.node.child_by_field_name("body")
            if parsed is None or body is None:
                continue
            for member in _members(body):
                if (
                    member.type == "method_declaration"
                    and _name_text(parsed, member) == bare
                ):
                    return True
        return False

    def closure(self, start: _Type, *, interfaces_only: bool) -> list[_Type] | str:
        """Supertypes of ``start`` (transitively), or why they do not resolve.

        ``interfaces_only``: classes in the closure are not walked (their
        interfaces are mapped by them, not by ``start``)."""
        seen: set[tuple[str, tuple[str, ...], str, int]] = {start.key}
        found: list[_Type] = []
        queue = [start]
        while queue:
            current = queue.pop()
            bases = self.direct(current, interfaces_only=interfaces_only)
            if isinstance(bases, str):
                return bases
            for base in bases:
                if base.key in seen:
                    continue
                seen.add(base.key)
                if len(seen) > MAX_TYPES:
                    return "its supertype closure is too large to check"
                if interfaces_only and base.node.type != "interface_declaration":
                    continue
                found.append(base)
                queue.append(base)
        return found

    def direct(self, t: _Type, *, interfaces_only: bool = False) -> list[_Type] | str:
        parts = self.parts(t)
        if isinstance(parts, str):
            return parts
        found: list[_Type] = []
        for part in parts:
            parsed = self.parse(part.file)
            if parsed is None:
                return "a file in its supertype closure could not be parsed"
            base_list = next(
                (c for c in part.node.children if c.type == "base_list"), None
            )
            if base_list is None:
                continue
            if base_list.has_error:
                return f"the base list of `{part.name}` could not be parsed"
            for entry in base_list.named_children:
                if entry.type == "primary_constructor_base_type":
                    entry = entry.child_by_field_name("type") or entry
                if entry.type == "predefined_type" and interfaces_only:
                    continue  # `object`: a class
                resolved = self.resolve(part, entry)
                if isinstance(resolved, str):
                    return resolved
                found.append(resolved)
        return found

    def resolve(self, user: _Type, entry: Any) -> _Type | str:
        parsed = self.parse(user.file)
        assert parsed is not None  # noqa: S101 — direct() parsed it
        raw = parsed.text(entry)
        segments = _segments(parsed, entry)
        if segments is None:
            return f"its supertype `{raw}` is not a type name that can be resolved"
        names, alias = segments
        if alias and alias != "global":
            return f"its supertype `{raw}` names the using alias `{alias}`"
        if alias == "global" or len(names) > 1:
            return self._qualified(parsed, user, names, raw, absolute=bool(alias))
        return self._simple(parsed, user, names[0], raw)

    def _simple(
        self, parsed: Parsed, user: _Type, name: tuple[str, int], raw: str
    ) -> _Type | str:
        nested = self._nested_in_scope(user, name)
        if nested is not None:
            return nested
        named = self.named(name[0])
        if isinstance(named, str):
            return named
        hidden = False
        for namespace, usings in _levels(parsed, user.node):
            if any(u.kind == "alias" and u.value == name[0] for u in usings):
                return f"its supertype `{raw}` names a using alias"
            declared = _distinct(
                n
                for n in named
                if not n.path and n.namespace == namespace and n.arity == name[1]
            )
            imported_ns = {u.value for u in usings if u.kind == "ns"}
            imported = _distinct(
                n
                for n in named
                if not n.path and n.namespace in imported_ns and n.arity == name[1]
            )
            if hidden and (declared or imported):
                return (
                    f"its supertype `{raw}` may name a type imported by a `using` "
                    "directive from outside the project"
                )
            for candidates in (declared, imported):
                if len(candidates) == 1:
                    return candidates[0]
                if candidates:
                    return f"its supertype `{raw}` is ambiguous in the project"
            hidden = hidden or bool(usings)
        return f"its supertype `{raw}` is declared outside the project"

    def _nested_in_scope(
        self, user: _Type, name: tuple[str, int]
    ) -> _Type | str | None:
        """A nested type of an enclosing type (declared or inherited)."""
        enclosing = [a for a in ancestors(user.node) if a.type in _TYPES]
        for node in enclosing:
            outer = self.type_of(user.file, node)
            found = self._member_type(outer, name)
            if found is not None:
                return found
            if outer.key in self._active:
                return "the supertypes of an enclosing type refer to each other"
            self._active.add(outer.key)
            try:
                bases = self._closure_memo(outer)
            finally:
                self._active.discard(outer.key)
            if isinstance(bases, str):
                return f"an enclosing type's supertype could not be resolved: {bases}"
            for base in bases:
                found = self._member_type(base, name)
                if found is not None:
                    return found
        return None

    def _member_type(self, outer: _Type, name: tuple[str, int]) -> _Type | None:
        named = self.named(name[0])
        if isinstance(named, str):
            return None
        found = _distinct(
            n
            for n in named
            if n.namespace == outer.namespace
            and n.path == (*outer.path, outer.name)
            and n.arity == name[1]
        )
        return found[0] if len(found) == 1 else None

    def _qualified(
        self,
        parsed: Parsed,
        user: _Type,
        names: list[tuple[str, int]],
        raw: str,
        *,
        absolute: bool,
    ) -> _Type | str:
        named = self.named(names[-1][0])
        if isinstance(named, str):
            return named
        dotted = ".".join(n for n, _a in names)
        levels = [("", [])] if absolute else _levels(parsed, user.node)
        for namespace, usings in levels:
            if any(u.kind == "alias" and u.value == names[0][0] for u in usings):
                return f"its supertype `{raw}` starts with a using alias"
            full = f"{namespace}.{dotted}" if namespace else dotted
            found = _distinct(
                n for n in named if n.dotted == full and n.arity == names[-1][1]
            )
            if len(found) == 1:
                return found[0]
            if found:
                return f"its supertype `{raw}` is ambiguous in the project"
        return f"its supertype `{raw}` is declared outside the project"


def _distinct(types: Any) -> list[_Type]:
    """One entry per type (the parts of a ``partial`` type are one type)."""
    seen: dict[tuple[str, tuple[str, ...], str, int], _Type] = {}
    for t in types:
        seen.setdefault(t.key, t)
    return list(seen.values())


__all__ = ["CSHARP_SUFFIXES", "OBJECT_METHODS", "csharp_row_finding"]
