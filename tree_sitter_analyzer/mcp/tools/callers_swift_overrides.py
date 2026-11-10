"""#1937 / #1938: Swift methods reached without a call edge naming them.

* **XCTest** (#1938) runs every ``test*`` method of an ``XCTestCase`` subclass by
  reflection. An instance method without parameters whose name starts with
  ``test``, declared in a class or an extension, is never ``complete`` (the
  superclass may be a project base class whose own superclass is
  ``XCTestCase``, so the check does not depend on it).
* An ``override`` (#1937) is reached through its superclass -- from
  ``XCTestCase`` or Foundation when the superclass is outside the project. It
  lets ``complete`` through only when every superclass up the chain resolves to
  exactly one top-level ``class`` declared in the project's Swift files, one of
  them declares the name, and every call edge named like it is bound to this
  declaration or outside the project. An ``override`` in an extension is
  checked against the extended class.
"""

from __future__ import annotations

import os
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

SWIFT_SUFFIXES = (".swift",)
_KEYWORDS = frozenset({"class", "struct", "enum", "extension", "actor", "protocol"})
_TEST_LEAD = "it is an XCTest test method, which XCTest runs by reflection"
_OVERRIDE_LEAD = "it is declared `override`"


def swift_row_finding(
    project_root: str, rel: str, line: int, bare: str, cache: Any
) -> tuple[str | None, SupertypeFinding | None]:
    """``(declaring type name, finding)`` of one Swift declaration row."""
    text = FILE_CACHE.read_text(os.path.join(project_root, rel))
    if text is None:
        return None, unchecked(rel, "the declaring file could not be read")
    parsed = parse("swift", text)
    if parsed is None:
        return None, unchecked(rel, "the declaring file could not be parsed")
    function = _function_at(parsed, line, bare) or _only_function(parsed, bare)
    if function is None:
        return None, None
    owner = _owner(function)
    # The grammar fails on some valid Swift (`#if` around a class, `async`
    # tests): the body is left in ERROR nodes, or the class is read as a
    # top-level function. Without a located owner such a file is "unparsed".
    unparsed = owner is None and (
        parsed.root.has_error or any(a.type == "ERROR" for a in ancestors(function))
    )
    if owner is None and not unparsed:
        return None, None
    keyword = None if owner is None else _keyword(parsed, owner)
    name = None if owner is None else _type_name(parsed, owner)
    modifiers = _modifiers(parsed, function)
    static = bool(modifiers & {"static", "class"})
    if (
        bare.startswith("test")
        and not static
        and (unparsed or keyword in {"class", "extension"})
        and not any(c.type == "parameter" for c in function.children)
    ):
        detail = (
            "XCTest runs every `test*` method of an `XCTestCase` subclass, "
            "never by name"
        )
        if unparsed:
            detail += " (its declaring type could not be parsed)"
        return name, finding(
            bare,
            rel,
            line,
            name,
            detail,
            verb="declares the test method",
            lead=_TEST_LEAD,
        )
    if "override" not in modifiers:
        return name, None
    if unparsed:
        proof = fail("its declaring class could not be parsed")
    else:
        proof = _override_proof(
            cache, project_root, rel, parsed, owner, keyword, line, bare
        )
    if proof.proved:
        return name, None
    return name, finding(
        bare,
        rel,
        line,
        name,
        proof.detail,
        verb=KOTLIN_OVERRIDE_VERB,
        lead=_OVERRIDE_LEAD,
    )


def _only_function(parsed: Parsed, bare: str) -> Any | None:
    """The one function named ``bare`` in the file: the index may record a line
    off the declaration where the grammar recovered from an error."""
    found = [
        node
        for node in walk(parsed.root)
        if node.type == "function_declaration"
        and any(
            c.type == "simple_identifier" and parsed.text(c) == bare
            for c in node.children
        )
    ]
    return found[0] if len(found) == 1 else None


def _override_proof(
    cache: Any,
    project_root: str,
    rel: str,
    parsed: Parsed,
    owner: Any,
    keyword: str | None,
    line: int,
    bare: str,
) -> OverrideProof:
    if keyword not in {"class", "extension"}:
        return fail("its declaring type is not a class")
    if cache is None:
        return fail("the project index could not be read to resolve its superclass")
    reader = _Reader(cache, project_root, {rel: parsed})
    start: tuple[str, Any] | str = (rel, owner)
    if keyword == "extension":
        start = reader.top_class(_type_name(parsed, owner) or "")
    if isinstance(start, str):
        return fail(start)
    chain = reader.chain(start)
    if isinstance(chain, str):
        return fail(chain)
    if not any(reader.declares(file, node, bare) for file, node in chain):
        return fail("no superclass in the project declares it")
    start_parsed = reader.parse(start[0])
    owner_name = None if start_parsed is None else _type_name(start_parsed, start[1])
    return dispatch_proof(cache, bare, rel, line, owner_name)


def _function_at(parsed: Parsed, line: int, bare: str) -> Any | None:
    matches = []
    for node in walk(parsed.root):
        if node.type != "function_declaration":
            continue
        name = next((c for c in node.children if c.type == "simple_identifier"), None)
        if name is None or parsed.text(name) != bare:
            continue
        if int(node.start_point[0]) + 1 <= line <= int(name.start_point[0]) + 1:
            matches.append(node)
    return matches[0] if len(matches) == 1 else None


def _owner(function: Any) -> Any | None:
    """The type or extension whose body declares ``function`` (ERROR nodes the
    grammar leaves inside a body are looked through)."""
    for node in ancestors(function):
        if node.type == "ERROR":
            continue
        if node.type != "class_body":
            return None
        owner = node.parent
        return (
            owner if owner is not None and owner.type == "class_declaration" else None
        )
    return None


def _keyword(parsed: Parsed, owner: Any) -> str | None:
    return next(
        (parsed.text(c) for c in owner.children if parsed.text(c) in _KEYWORDS),
        None,
    )


def _type_name(parsed: Parsed, owner: Any) -> str | None:
    for child in owner.children:
        if child.type in {"type_identifier", "user_type"}:
            return parsed.text(child)
        if child.type == "class_body":
            break
    return None


def _modifiers(parsed: Parsed, function: Any) -> set[str]:
    found: set[str] = set()
    for child in function.children:
        if child.type == "modifiers":
            found.update(parsed.text(m) for m in child.named_children)
    return found


def _superclass(parsed: Parsed, node: Any) -> str | None:
    """The first inheritance entry (a superclass, if the class has one)."""
    for child in node.children:
        if child.type == "class_body":
            return None
        if child.type == "inheritance_specifier":
            return parsed.text(child).strip()
    return None


class _Reader:
    def __init__(self, cache: Any, project_root: str, seed: dict[str, Parsed]) -> None:
        self._cache = cache
        self._root = project_root
        self._parsed: dict[str, Parsed | None] = dict(seed)

    def parse(self, rel: str) -> Parsed | None:
        if rel not in self._parsed:
            text = FILE_CACHE.read_text(os.path.join(self._root, rel))
            self._parsed[rel] = None if text is None else parse("swift", text)
        return self._parsed[rel]

    def top_class(self, name: str) -> tuple[str, Any] | str:
        """The one top-level ``class`` named ``name`` in the project, or why not."""
        if not name.isidentifier():
            return f"its superclass `{name}` is not a simple name that can be resolved"
        files = class_files(self._cache, "swift", name)
        if isinstance(files, str):
            return files
        found: list[tuple[str, Any]] = []
        for rel in files:
            parsed = self.parse(rel)
            if parsed is None:
                return "a candidate superclass file could not be parsed"
            found.extend(
                (rel, node)
                for node in parsed.root.children
                if node.type == "class_declaration"
                and _keyword(parsed, node) == "class"
                and _type_name(parsed, node) == name
            )
        if len(found) == 1:
            return found[0]
        if found:
            return f"its superclass `{name}` is declared more than once in the project"
        return f"its superclass `{name}` is declared outside the project"

    def chain(self, start: tuple[str, Any]) -> list[tuple[str, Any]] | str:
        found: list[tuple[str, Any]] = []
        current = start
        while len(found) <= MAX_TYPES:
            parsed = self.parse(current[0])
            if parsed is None:
                return "a file in its superclass chain could not be parsed"
            name = _superclass(parsed, current[1])
            if name is None:
                return found
            resolved = self.top_class(name)
            if isinstance(resolved, str):
                return resolved
            if any(
                resolved[0] == f and resolved[1].start_byte == n.start_byte
                for f, n in found
            ):
                return "its superclass chain is cyclic"
            found.append(resolved)
            current = resolved
        return "its superclass chain is too long to check"

    def declares(self, rel: str, node: Any, bare: str) -> bool:
        parsed = self.parse(rel)
        body = next((c for c in node.children if c.type == "class_body"), None)
        if parsed is None or body is None:
            return False
        for member in walk(body):
            if member.type != "function_declaration":
                continue
            owner = _owner(member)
            if owner is None or owner.start_byte != node.start_byte:
                continue
            name = next(
                (c for c in member.children if c.type == "simple_identifier"), None
            )
            if name is not None and parsed.text(name) == bare:
                return True
        return False


__all__ = ["SWIFT_SUFFIXES", "swift_row_finding"]
