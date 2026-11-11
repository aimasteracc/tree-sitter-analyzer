"""#1894: a Java method a subtype inherits as another type's method.

.. code-block:: java

    interface I { void m(); default void run() { m(); } }
    class A { public void m() {} }        // no supertype
    class B extends A implements I {}     // A.m implements I.m in B

``b.run()`` calls ``A.m`` through ``I``, but the call edge of ``m()`` in ``I``
is bound to ``I.m``, and ``A`` has no supertype, so the override proof
(:mod:`.callers_java_overrides`) never ran: ``A.m`` answered ``complete``.

:func:`subtype_proof` walks the project subtypes of the declaring type
(transitively). The method is dispatch-reachable when the supertype closure of
some subtype holds, besides the declaring type, a type that declares the same
name. It then passes only when every call edge named like it is bound to this
declaration or outside the project (the same rule as the override proof). It
fails outright when that closure holds a JDK type declaring the name (the JDK
calls it), or cannot be resolved in the project.

The subtypes are found from source: every project Java type whose
``extends`` / ``implements`` clause names the declaring type. A clause whose
last name segment matches but that cannot be resolved to a project type
(qualified, ambiguous, outside the project) may be a subtype, so it fails the
proof. Too many subtypes fail it too.

Not checked, by design:

* methods that cannot be inherited as an implementation: static, private (the
  caller skips them), and methods without a body (abstract, or interface
  methods that are not ``default``): they implement nothing;
* types without named subtypes: ``final`` classes, enums, records and
  anonymous class bodies (an anonymous or enum-constant body has exactly one
  supertype, so it cannot add a type);
* subtypes outside the project. Like the override proof, the walk is
  closed-world: a library class may be extended by code that is not indexed,
  and no index can see that code.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

from .callers_java_overrides import (
    _JDK,
    OverrideProof,
    _describe,
    _direct_supertypes,
    _dispatch_sites,
    _enclosing_types,
    _key,
    _method_at,
    _name,
    _owner_type,
    _package,
    _Parsed,
    _Reader,
    _single_type_import,
    _type_declarations,
)
from .evidence_file_cache import FILE_CACHE

#: How a subtype relates to the declaring type in a finding.
SUBTYPE_VERB = "has subtype"
#: Subtypes visited before giving up (fail closed).
_MAX_SUBTYPES = 128
#: Owners that may have named subtypes.
_EXTENSIBLE = frozenset({"class_declaration", "interface_declaration"})
#: Declarations that may name a supertype (an enum or a record implements one).
_SUBTYPE_DECLARATIONS = _EXTENSIBLE | {"enum_declaration", "record_declaration"}
_GENERIC_ARGS = re.compile(r"<[^<>]*>")


def subtype_proof(
    cache: Any,
    project_root: str,
    rel_path: str,
    text: str,
    line: int,
    bare: str,
) -> tuple[str, OverrideProof]:
    """``(subtype name, proof)`` that no project subtype lets a call through
    another type reach the method ``bare`` declared at ``line``.

    The subtype name is the one the failure is about ("" when proved, or when
    the failure is not about one subtype).
    """
    if cache is None:
        return "", _fail("the project index could not be read to find its subtypes")
    reader = _Reader(cache, project_root)
    parsed = reader.parse(rel_path, text)
    if parsed is None:
        return "", _fail("its declaring file could not be parsed")
    method = _method_at(parsed, line, bare)
    if method is None:
        return "", _fail("its declaration could not be located")
    owner = _owner_type(method)
    if (
        owner is None
        or method.child_by_field_name("body") is None
        or not _extensible(parsed, owner)
    ):
        return "", OverrideProof(True)
    subtypes = _subtypes(reader, cache, project_root, rel_path, owner, parsed)
    if isinstance(subtypes, tuple):
        return subtypes
    target = _key((rel_path, owner))
    reached: tuple[str, str] | None = None  # (subtype, type declaring ``bare``)
    for file, node in subtypes:
        name = _type_name(reader, file, node)
        found = _reach(reader, file, node, target, bare)
        if isinstance(found, OverrideProof):
            return name, found
        if found is not None and reached is None:
            reached = (name, found)
    if reached is None:
        return "", OverrideProof(True)
    subtype, declaring = reached
    sites = _dispatch_sites(cache, bare, rel_path, line, _name(parsed, owner))
    if sites is None:
        return subtype, _fail("the call edges named like it could not be read")
    if not sites:
        return "", OverrideProof(True)
    return subtype, OverrideProof(
        False,
        f"which also inherits `{declaring}.{bare}`, so it implements that method "
        "there; call(s) named like it are not bound to this declaration and may "
        "dispatch here through it: " + _describe(sites),
        tuple(sites),
    )


def _fail(detail: str) -> OverrideProof:
    return OverrideProof(False, detail)


def _extensible(parsed: _Parsed, owner: Any) -> bool:
    """A named class or interface that is not ``final``."""
    if owner.type not in _EXTENSIBLE:
        return False
    for child in owner.children:
        if child.type == "modifiers":
            words = parsed.source[child.start_byte : child.end_byte].decode(
                "utf-8", "replace"
            )
            if "final" in words.split():
                return False
    return True


def _subtypes(
    reader: _Reader,
    cache: Any,
    project_root: str,
    rel_path: str,
    owner: Any,
    parsed: _Parsed,
) -> list[tuple[str, Any]] | tuple[str, OverrideProof]:
    """Every project subtype of ``owner`` (transitively), or why it is unknown."""
    files = _java_type_files(cache)
    if files is None:
        return "", _fail("the project's types could not be read to find its subtypes")
    found: list[tuple[str, Any]] = []
    seen = {_key((rel_path, owner))}
    queue: list[tuple[str, Any, str]] = [(rel_path, owner, _name(parsed, owner) or "")]
    while queue:
        file, node, name = queue.pop()
        candidates = _candidates(reader, project_root, files, name)
        if isinstance(candidates, OverrideProof):
            return "", candidates
        for sub_file, sub in candidates:
            direct = _extends(reader, sub_file, sub, name, (file, node))
            if isinstance(direct, OverrideProof):
                return _type_name(reader, sub_file, sub), direct
            key = _key((sub_file, sub))
            if not direct or key in seen:
                continue
            seen.add(key)
            if len(seen) > _MAX_SUBTYPES:
                return "", _fail("it has too many subtypes to check")
            found.append((sub_file, sub))
            queue.append((sub_file, sub, _type_name(reader, sub_file, sub)))
    return found


def _java_type_files(cache: Any) -> list[str] | None:
    try:
        rows = cache.get_conn().execute(
            "SELECT DISTINCT file_path FROM ast_symbol_rows "
            "WHERE kind = 'class' AND language = 'java'"
        )
        return sorted(str(row[0]) for row in rows)
    except (sqlite3.Error, AttributeError):
        return None


def _candidates(
    reader: _Reader, project_root: str, files: list[str], name: str
) -> list[tuple[str, Any]] | OverrideProof:
    """Named types in files whose text has a supertype clause naming ``name``."""
    clause = re.compile(
        r"\b(?:extends|implements)\b[^{;]*?\b" + re.escape(name) + r"\b", re.DOTALL
    )
    found: list[tuple[str, Any]] = []
    for file in files:
        text = FILE_CACHE.read_text(os.path.join(project_root, file))
        if text is None:
            return _fail(f"{file}, which may declare a subtype, could not be read")
        # RFC-0043: the clause names ``name`` as a whole word, so a text without the
        # substring cannot match; the substring test is exact and far cheaper than
        # the lazy clause scan over every Java type file.
        if name not in text or not clause.search(text):
            continue
        parsed = reader.parse(file, text)
        if parsed is None:
            return _fail(f"{file}, which may declare a subtype, could not be parsed")
        found.extend(
            (file, node)
            for node in _type_declarations(parsed.root)
            if node.type in _SUBTYPE_DECLARATIONS
        )
    return found


def _extends(
    reader: _Reader, file: str, node: Any, name: str, target: tuple[str, Any]
) -> bool | OverrideProof:
    """``node`` names ``target`` as a direct supertype; a failure when it may."""
    parsed = reader.parse(file)
    if parsed is None:
        return _fail("a file that may declare a subtype could not be parsed")
    for supertype in _direct_supertypes(node):  # a declaration: never a tuple
        raw = parsed.source[supertype.start_byte : supertype.end_byte].decode(
            "utf-8", "replace"
        )
        written = _GENERIC_ARGS.sub("", raw)
        while _GENERIC_ARGS.search(written):
            written = _GENERIC_ARGS.sub("", written)
        if written.strip().rpartition(".")[2].strip() != name:
            continue
        resolved = reader._resolve(file, node, supertype)
        if isinstance(resolved, str):
            if _imports_another(reader, parsed, name, target):
                continue
            return _fail(f"which may extend it through `{raw}`: {resolved}")
        if _key(resolved) == _key(target):
            return True
    return False


def _imports_another(
    reader: _Reader, parsed: _Parsed, name: str, target: tuple[str, Any]
) -> bool:
    """The file imports ``name`` from a package that is not the target's.

    Only for a top-level target: an import of a nested type names its outer
    type, which this cannot compare.
    """
    target_file, target_node = target
    if target_node.parent is None or target_node.parent.type != "program":
        return False
    text = parsed.source.decode("utf-8", "replace")
    imported = _single_type_import(text, name)
    if imported is None:
        return False
    declaring = reader.parse(target_file)
    if declaring is None:
        return False
    return imported != _package(declaring.source.decode("utf-8", "replace"))


def _reach(
    reader: _Reader, file: str, node: Any, target: tuple[str, int | str], bare: str
) -> str | OverrideProof | None:
    """The type in ``node``'s closure (other than the target) declaring ``bare``."""
    closure = reader.closure(file, [node])
    if isinstance(closure, str):
        return _fail(f"whose {_subject(closure)}, so what it inherits is unknown")
    enclosing = reader.closure(file, _enclosing_types(node))
    if isinstance(enclosing, str):
        return _fail(
            f"whose enclosing type's {_subject(enclosing)}, so what it inherits "
            "is unknown"
        )
    for type_file, type_node in closure:
        if _key((type_file, type_node)) == target:
            continue
        if type_file == _JDK and bare in type_node.members:
            return _fail(
                f"which also implements `{type_node.qualified}.{bare}`, declared "
                "outside the project"
            )
        if reader.declares(type_file, type_node, bare):
            return _type_name(reader, type_file, type_node)
    return None


def _subject(detail: str) -> str:
    """A closure failure (``its supertype ...``) said of the subtype."""
    return detail.replace("its supertype", "supertype", 1)


def _type_name(reader: _Reader, file: str, node: Any) -> str:
    parsed = reader.parse(file)
    return (_name(parsed, node) if parsed is not None else None) or "<anonymous>"


__all__ = ["SUBTYPE_VERB", "subtype_proof"]
