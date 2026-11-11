"""#1953: a Swift method may satisfy a protocol requirement a framework calls.

.. code-block:: swift

    class ExtensionDelegate: NSObject, WKExtensionDelegate {
        func handle(_ backgroundTasks: Set<WKRefreshBackgroundTask>) { }
    }

WatchKit calls ``handle`` through ``WKExtensionDelegate``; no call edge names
it. A non-``private`` method of a type is "possibly a protocol requirement" when
the type conforms -- in its declaration or in an extension of it in any file,
directly, through a superclass or through a refined protocol -- to

* a name that is not declared in the project's Swift files (its requirements
  are unknown), unless it is a standard type whose method requirements are
  known (:data:`KNOWN_REQUIREMENTS`) and do not include the name, or
* a project protocol that declares the name: then every call edge named like it
  must be bound to this declaration or outside the project.

Declarations are found by scanning the project's Swift files for the
declaring keyword, then read from the tree. A declaration the grammar does not
recover (the Swift grammar fails on some valid code) blocks, as does a method
whose declaring type could not be parsed. Types named alike are merged (nested
types are found by their last name segment), which only adds conformances.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .callers_override_common import (
    MAX_TYPES,
    Parsed,
    dispatch_proof,
    finding,
    parse,
    walk,
)
from .callers_supertypes import SupertypeFinding
from .evidence_file_cache import FILE_CACHE

#: Method requirements of standard types whose conformance a project often
#: declares (properties and initializers are not methods). A superclass named
#: here (``NSObject``) needs ``override`` to redefine a method.
KNOWN_REQUIREMENTS: dict[str, frozenset[str]] = {
    name: frozenset(methods)
    for names, methods in (
        (("Any", "AnyObject", "NSObject", "Sendable", "CaseIterable"), ()),
        (("Identifiable", "RawRepresentable", "Decodable"), ()),
        (("CustomStringConvertible", "CustomDebugStringConvertible"), ()),
        (("LocalizedError", "CustomNSError"), ()),
        (("Error",), ("_getEmbeddedNSError",)),
        # XCTest runs `test*` methods and overrides (checked elsewhere); the
        # rest of its protocol methods are the `XCTWaiterDelegate` ones.
        (("XCTestCase",), ("waiter", "nestedWaiter")),
        (("Equatable",), ("==",)),
        (("Hashable",), ("==", "hash")),
        (("Comparable",), ("==", "<", "<=", ">", ">=")),
        (("Encodable", "Codable"), ("encode",)),
        (("String", "Character", "Bool", "Double", "Float"), ()),
        (("Int", "Int8", "Int16", "Int32", "Int64"), ()),
        (("UInt", "UInt8", "UInt16", "UInt32", "UInt64"), ()),
        (
            (
                "ExpressibleByStringLiteral",
                "ExpressibleByIntegerLiteral",
                "ExpressibleByFloatLiteral",
                "ExpressibleByBooleanLiteral",
                "ExpressibleByNilLiteral",
                "ExpressibleByArrayLiteral",
                "ExpressibleByDictionaryLiteral",
                "ExpressibleByUnicodeScalarLiteral",
                "ExpressibleByExtendedGraphemeClusterLiteral",
            ),
            (),
        ),
    )
    for name in names
}
_REAL = frozenset({"class", "struct", "enum", "actor", "protocol"})
_LEAD = "it may satisfy a protocol requirement"
_VERB = "declares"
_MODIFIERS = (
    r"(?:(?:public|open|internal|fileprivate|private|package|final|indirect|"
    r"nonisolated|distributed)\s+)*"
)
_ATTRIBUTES = r"(?:@\w+(?:\([^)\n]*\))?\s+)*"


def requirement_finding(
    cache: Any,
    project_root: str,
    rel: str,
    parsed: Parsed,
    owner: Any | None,
    line: int,
    bare: str,
    modifiers: set[str],
    owner_name: str | None,
) -> SupertypeFinding | None:
    """A finding when the method may satisfy a requirement no call edge shows.

    ``owner`` is the type or extension whose body declares the method; None
    when it could not be located in a file the grammar failed on."""
    if "private" in modifiers:
        return None  # a private method witnesses no requirement
    if owner is None:
        return _block(
            bare,
            rel,
            line,
            owner_name,
            "and its declaring type could not be parsed, so the protocols it "
            "conforms to are unknown",
        )
    from .callers_swift_overrides import _type_name

    extended = _last(_type_name(parsed, owner) or "")
    if not extended:
        return None
    if cache is None:
        return _block(
            bare,
            rel,
            line,
            owner_name,
            "and the project index could not be read to find its protocols",
        )
    conformances = _Walk(_Decls(cache, project_root, {rel: parsed}), bare)
    conformances.run(extended)
    if conformances.blocked is not None:
        return _block(bare, rel, line, owner_name, conformances.blocked)
    if not conformances.declaring:
        return None
    proof = dispatch_proof(cache, bare, rel, line, owner_name)
    if proof.proved:
        return None
    return _block(
        bare,
        rel,
        line,
        owner_name,
        f"and the project protocol `{conformances.declaring[0]}` declares it; "
        + proof.detail,
    )


def _block(
    bare: str, rel: str, line: int, owner: str | None, detail: str
) -> SupertypeFinding:
    return finding(bare, rel, line, owner, detail, verb=_VERB, lead=_LEAD)


@dataclass
class _Walk:
    """Breadth-first walk over the conformances of a type."""

    decls: _Decls
    bare: str
    blocked: str | None = None
    declaring: list[str] = field(default_factory=list)

    def run(self, start: str) -> None:
        seen = {start}
        queue = [start]
        while queue and self.blocked is None:
            name = queue.pop(0)
            found = self.decls.find(name)
            if isinstance(found, str):
                self.blocked = f"and {found}"
                return
            real = [d for d in found if d.keyword in _REAL]
            # A name declared only nested in the project may still denote an
            # outside top-level type.
            if name != start and not any(d.top for d in real):
                self._external(name)
            if any(d.keyword == "protocol" and d.declares(self.bare) for d in real):
                self.declaring.append(name)
            for entry in (e for d in found for e in d.entries):
                if entry not in seen:
                    seen.add(entry)
                    queue.append(entry)
            if len(seen) > MAX_TYPES:
                self.blocked = "and its conformances are too many to check"

    def _external(self, name: str) -> None:
        known = KNOWN_REQUIREMENTS.get(name)
        if known is None:
            self.blocked = (
                f"and its type conforms to `{name}`, which is not declared in "
                "the project, so its requirements are unknown"
            )
        elif self.bare in known:
            self.blocked = f"and `{name}` requires a method named like it"


@dataclass(frozen=True)
class _Decl:
    keyword: str
    entries: tuple[str, ...]
    requirements: frozenset[str]
    top: bool

    def declares(self, bare: str) -> bool:
        return bare in self.requirements


class _Decls:
    """Declarations of a Swift type name in the project's Swift files."""

    def __init__(self, cache: Any, project_root: str, seed: dict[str, Parsed]):
        self._cache = cache
        self._root = project_root
        self._parsed: dict[str, Parsed | None] = dict(seed)
        self._files: list[str] | str | None = None

    def files(self) -> list[str] | str:
        if self._files is None:
            try:
                rows = self._cache.get_conn().execute(
                    "SELECT file_path FROM ast_index WHERE language = 'swift'"
                )
                self._files = sorted(str(row[0]) for row in rows)
            except (sqlite3.Error, AttributeError):
                self._files = "the project's Swift files could not be listed"
        return self._files

    def find(self, name: str) -> list[_Decl] | str:
        files = self.files()
        if isinstance(files, str):
            return files
        pattern = re.compile(
            r"^[ \t]*"
            + _ATTRIBUTES
            + _MODIFIERS
            + r"(class|struct|enum|actor|extension|protocol)\s+(?:\w+\.)*"
            + re.escape(name)
            + r"\b",
            re.MULTILINE,
        )
        found: list[_Decl] = []
        for rel in files:
            text = FILE_CACHE.read_text(os.path.join(self._root, rel))
            if text is None:
                return f"the Swift file {rel} could not be read"
            lines = [text.count("\n", 0, m.start(1)) for m in pattern.finditer(text)]
            if not lines:
                continue
            parsed = self._parse(rel, text)
            nodes = [] if parsed is None else _declarations(parsed, name)
            for row in lines:
                decl = next((d for start, end, d in nodes if start <= row <= end), None)
                if decl is None:
                    return (
                        f"the declaration of `{name}` in {rel}:{row + 1} could "
                        "not be parsed"
                    )
                found.append(decl)
        return found

    def _parse(self, rel: str, text: str) -> Parsed | None:
        if rel not in self._parsed:
            self._parsed[rel] = parse("swift", text)
        return self._parsed[rel]


def _declarations(parsed: Parsed, name: str) -> list[tuple[int, int, _Decl]]:
    """``(first row, name row, declaration)`` of each declaration of ``name``."""
    from .callers_swift_overrides import _keyword, _type_name

    found = []
    for node in walk(parsed.root):
        if node.type not in {"class_declaration", "protocol_declaration"}:
            continue
        if _last(_type_name(parsed, node) or "") != name or not _header_ok(node):
            continue
        keyword = _keyword(parsed, node) or ""
        name_row = next(
            (
                int(c.start_point[0])
                for c in node.children
                if c.type in {"type_identifier", "user_type"}
            ),
            int(node.start_point[0]),
        )
        decl = _Decl(
            keyword,
            _entries(parsed, node),
            _requirements(parsed, node),
            node.parent is not None and node.parent.type == "source_file",
        )
        found.append((int(node.start_point[0]), name_row, decl))
    return found


_BODIES = frozenset({"class_body", "protocol_body", "enum_class_body"})


def _last(name: str) -> str:
    """``Outer.Inner<T>`` -> ``Inner``."""
    return name.partition("<")[0].strip().rpartition(".")[2]


def _header_ok(node: Any) -> bool:
    """The header up to the body was read without an error, and a body follows."""
    for child in node.children:
        if child.type in _BODIES:
            return True
        if child.type == "ERROR" or child.has_error:
            return False
    return False


def _entries(parsed: Parsed, node: Any) -> tuple[str, ...]:
    """Last name segment of each inheritance entry (generic arguments dropped)."""
    found = []
    for child in node.children:
        if child.type in _BODIES:
            break
        if child.type != "inheritance_specifier":
            continue
        user = next((c for c in walk(child) if c.type == "user_type"), None)
        if user is None:
            found.append(parsed.text(child).strip())
            continue
        idents = [c for c in user.children if c.type == "type_identifier"]
        found.append(parsed.text(idents[-1]) if idents else parsed.text(user))
    return tuple(found)


def _requirements(parsed: Parsed, node: Any) -> frozenset[str]:
    body = next((c for c in node.children if c.type == "protocol_body"), None)
    if body is None:
        return frozenset()
    names = set()
    for member in body.children:
        if member.type != "protocol_function_declaration":
            continue
        ident = next(
            (
                c
                for c in member.children
                if c.type in {"simple_identifier", "custom_operator"}
            ),
            None,
        )
        if ident is not None:
            names.add(parsed.text(ident))
    return frozenset(names)


__all__ = ["KNOWN_REQUIREMENTS", "requirement_finding"]
