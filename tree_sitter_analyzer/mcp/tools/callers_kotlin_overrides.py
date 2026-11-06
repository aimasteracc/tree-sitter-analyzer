"""#1930: a Kotlin ``override`` may be reached through a supertype outside the project.

.. code-block:: kotlin

    class F : java.io.Closeable { override fun close() {} }

``F.close`` answered ``complete`` with 0 callers, although whoever holds a
``Closeable`` (``use { }``, the JDK, a library) calls it. Those callers are not in
the project, so nothing in the index can prove absence. This is the Kotlin form of
the Java ``@Override`` gate (:mod:`.callers_java_overrides`); Kotlin needs no
annotation, because ``override`` is mandatory on every overriding member.

A function declared ``override`` lets ``complete`` through only when:

* it is not named like a ``kotlin.Any`` member (``equals`` / ``hashCode`` /
  ``toString``), which every class inherits from outside the project;
* **every** supertype in the transitive closure of its declaring type (a class,
  object, companion object, object expression or enum entry) resolves, from
  source, to a type declared in the project's Kotlin files. Kotlin's order is
  followed: a nested type in scope, a top-level type of the same file, an
  explicit import (``as`` aliases included), the same package, star imports.
  Anything else (``java.io.Closeable``, ``AutoCloseable``, a library type, a type
  alias, an ambiguous name, a closure larger than :data:`_MAX_TYPES`) fails;
* some type in that closure declares a member of the same name;
* every call edge named like it is bound to this declaration or outside the
  project (the Java gate's check).

A function without ``override`` overrides nothing in Kotlin and passes. A file
that cannot be read or parsed, or a declaration that cannot be located while its
line says ``override``, leaves the check not run.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from .callers_java_overrides import (
    OVERRIDE_REASON,
    OverrideProof,
    _describe,
    _dispatch_sites,
)
from .callers_supertypes import KOTLIN_OVERRIDE_VERB, SupertypeFinding
from .evidence_file_cache import FILE_CACHE

KOTLIN_SUFFIXES = (".kt", ".kts")
#: Members every Kotlin class inherits from ``kotlin.Any``.
ANY_METHODS = frozenset({"equals", "hashCode", "toString"})
#: Types visited in one closure before giving up (fail closed).
_MAX_TYPES = 64
_TYPE_DECLARATIONS = frozenset({"class_declaration", "object_declaration"})
#: Nodes whose body may declare an overriding member.
_OWNERS = _TYPE_DECLARATIONS | {"companion_object", "object_literal", "enum_entry"}
_BODIES = frozenset({"class_body", "enum_class_body"})
#: Delegation specifiers that wrap the supertype's ``user_type``.
_WRAPPED = frozenset({"constructor_invocation", "explicit_delegation"})
_OVERRIDE = re.compile(r"\boverride\b")


def kotlin_supertype_finding(
    project_root: str,
    declarations: list[tuple[str, int, str]],
    bare: str,
    cache: Any,
    owner: str = "",
) -> SupertypeFinding | None:
    """The first Kotlin row of ``bare`` that overrides a member it cannot close."""
    wanted = owner.rpartition(".")[2]
    results: list[tuple[str | None, SupertypeFinding | None]] = [
        _row_finding(project_root, rel, line, bare, cache)
        for rel, line, _language in declarations
        if rel.lower().endswith(KOTLIN_SUFFIXES)
    ]
    own = [found for name, found in results if wanted and name == wanted]
    candidates = own if own else [found for _name, found in results]
    unread = [found for _n, found in results if found is not None and found.unchecked]
    return next((f for f in [*unread, *candidates] if f is not None), None)


def _row_finding(
    project_root: str, rel: str, line: int, bare: str, cache: Any
) -> tuple[str | None, SupertypeFinding | None]:
    """``(owner type name, finding)`` of one declaration row."""
    text = FILE_CACHE.read_text(os.path.join(project_root, rel))
    if text is None:
        return None, _unchecked(rel, "the declaring file could not be read")
    parsed = _parse(text)
    if parsed is None:
        return None, _unchecked(rel, "the declaring file could not be parsed")
    function = _function_at(parsed, line, bare)
    if function is None:
        if _override_on_line(text, line):
            return None, _unchecked(
                rel, "its `override` declaration could not be located"
            )
        return None, None
    if not _is_override(parsed, function):
        return None, None
    owner = _owner_type(function)
    name = None if owner is None else _owner_name(parsed, owner)
    proof = override_proof(cache, project_root, rel, parsed, owner, line, bare)
    if proof.proved:
        return name, None
    return name, SupertypeFinding(
        bare,
        rel,
        line,
        name or "<anonymous>",
        proof.detail,
        verb=KOTLIN_OVERRIDE_VERB,
        reason=OVERRIDE_REASON,
    )


def override_proof(
    cache: Any,
    project_root: str,
    rel: str,
    parsed: _Parsed,
    owner: Any | None,
    line: int,
    bare: str,
) -> OverrideProof:
    """Prove the ``override`` member ``bare`` of ``owner`` is closed in the project."""
    if bare in ANY_METHODS:
        return _fail(f"`kotlin.Any.{bare}` is declared outside the project")
    if owner is None:
        return _fail("its declaring type could not be located")
    if cache is None:
        return _fail("the project index could not be read to resolve its supertypes")
    reader = _Reader(cache, project_root, {rel: parsed})
    closure = reader.closure(rel, owner)
    if isinstance(closure, str):
        return _fail(closure)
    if not any(reader.declares(file, node, bare) for file, node in closure):
        return _fail("no supertype in the project declares it")
    sites = _dispatch_sites(cache, bare, rel, line, _owner_name(parsed, owner))
    if sites is None:
        return _fail("the call edges named like it could not be read")
    if sites:
        return OverrideProof(
            False,
            "call(s) named like it are not bound to this declaration and may "
            "dispatch here through a supertype: " + _describe(sites),
            tuple(sites),
        )
    return OverrideProof(True)


def _fail(detail: str) -> OverrideProof:
    return OverrideProof(False, detail)


def _unchecked(rel: str, why: str) -> SupertypeFinding:
    return SupertypeFinding("", rel, 0, "", why, unchecked=True)


@dataclass(frozen=True)
class _Parsed:
    source: bytes
    root: Any

    def text(self, node: Any) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _parse(text: str) -> _Parsed | None:
    """The Kotlin tree. The grammar flags errors on some valid code, so an error
    node is not a failure here; the supertype list of every type the proof reads
    is checked instead (:func:`_direct_supertypes`)."""
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely("kotlin")
        if parser is None:
            return None
        source = text.encode("utf-8")
        tree = parser.parse(source)
    except Exception:  # noqa: BLE001 — a grammar failure is "cannot prove"
        return None
    return _Parsed(source, tree.root_node)


def _walk(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(node.children)
    return found


def _name_node(node: Any) -> Any | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return named
    return next(
        (c for c in node.children if c.type in {"identifier", "simple_identifier"}),
        None,
    )


def _function_at(parsed: _Parsed, line: int, bare: str) -> Any | None:
    """The function declaration named ``bare`` whose header holds ``line``."""
    matches = []
    for node in _walk(parsed.root):
        if node.type != "function_declaration":
            continue
        name = _name_node(node)
        if name is None or parsed.text(name) != bare:
            continue
        if int(node.start_point[0]) + 1 <= line <= int(name.start_point[0]) + 1:
            matches.append(node)
    return matches[0] if len(matches) == 1 else None


def _override_on_line(text: str, line: int) -> bool:
    lines = text.splitlines()
    return 0 < line <= len(lines) and bool(_OVERRIDE.search(lines[line - 1]))


def _is_override(parsed: _Parsed, function: Any) -> bool:
    for child in function.children:
        if child.type == "modifiers":
            return any(
                part.type == "member_modifier" and parsed.text(part) == "override"
                for part in child.children
            )
    return False


def _owner_type(member: Any) -> Any | None:
    body = member.parent
    if body is None or body.type not in _BODIES:
        return None
    owner = body.parent
    return owner if owner is not None and owner.type in _OWNERS else None


def _owner_name(parsed: _Parsed, owner: Any) -> str | None:
    if owner.type == "object_literal":
        return None
    name = _name_node(owner)
    if name is not None:
        return parsed.text(name)
    return "Companion" if owner.type == "companion_object" else None


def _body(node: Any) -> Any | None:
    return next((c for c in node.children if c.type in _BODIES), None)


def _direct_supertypes(node: Any) -> list[Any] | None:
    """Direct supertype nodes (an enum entry yields ``("enum", <enum class>)``);
    None when the supertype list was not parsed cleanly."""
    if node.type == "enum_entry":
        body = node.parent
        enum = body.parent if body is not None else None
        return [] if enum is None else [("enum", enum)]
    found: list[Any] = []
    for child in node.children:
        if child.type in _BODIES:
            break
        if child.type == "ERROR" or child.is_missing:
            return None
        if child.type != "delegation_specifiers":
            continue
        if child.has_error:
            return None
        for spec in child.named_children:
            inner = spec.named_children[0] if spec.named_children else spec
            if inner.type in _WRAPPED and inner.named_children:
                inner = inner.named_children[0]
            found.append(inner)
    return found


def _segments(parsed: _Parsed, user_type: Any) -> list[str]:
    """``a.b.C<T>`` -> ``["a", "b", "C"]`` (type arguments dropped)."""
    found: list[str] = []
    for child in user_type.children:
        if child.type in {"identifier", "simple_identifier", "type_identifier"}:
            found.append(parsed.text(child))
        elif child.type in {"user_type", "simple_user_type"}:
            found.extend(_segments(parsed, child))
    return found


def _package(parsed: _Parsed) -> str:
    header = next((c for c in parsed.root.children if c.type == "package_header"), None)
    if header is None:
        return ""
    name = next((c for c in header.named_children), None)
    return "" if name is None else re.sub(r"\s+", "", parsed.text(name))


@dataclass(frozen=True)
class _Import:
    path: tuple[str, ...]
    alias: str | None
    star: bool

    @property
    def local(self) -> str:
        return self.alias or self.path[-1]


def _imports(parsed: _Parsed) -> list[_Import]:
    found: list[_Import] = []
    for node in _walk(parsed.root):
        if node.type not in {"import", "import_header"} or node.parent is None:
            continue
        if node.parent.type not in {"source_file", "import_list"}:
            continue
        path = next(
            (
                c
                for c in node.named_children
                if c.type in {"qualified_identifier", "identifier"}
            ),
            None,
        )
        if path is None:
            continue
        segments = tuple(re.sub(r"\s+", "", parsed.text(path)).split("."))
        alias_nodes = [
            c
            for c in node.named_children
            if c.type == "identifier" and c.start_byte != path.start_byte
        ]
        star = any(c.type == "*" for c in _walk(node))
        alias = parsed.text(alias_nodes[-1]) if alias_nodes and not star else None
        found.append(_Import(segments, alias, star))
    return found


class _Reader:
    """Reads project Kotlin files and resolves supertype names from source."""

    def __init__(self, cache: Any, project_root: str, seed: dict[str, _Parsed]) -> None:
        self._cache = cache
        self._root = project_root
        self._parsed: dict[str, _Parsed | None] = dict(seed)

    def parse(self, rel: str) -> _Parsed | None:
        if rel not in self._parsed:
            text = FILE_CACHE.read_text(os.path.join(self._root, rel))
            self._parsed[rel] = None if text is None else _parse(text)
        return self._parsed[rel]

    def closure(self, rel: str, start: Any) -> list[tuple[str, Any]] | str:
        """Every supertype of ``start`` (transitively) as ``(file, node)``, or why not."""
        seen: set[tuple[str, int]] = set()
        found: list[tuple[str, Any]] = []
        queue: list[tuple[str, Any]] = [(rel, start)]
        while queue:
            file, node = queue.pop()
            supertypes = _direct_supertypes(node)
            if supertypes is None:
                return f"the supertype list of a type in {file} could not be parsed"
            for supertype in supertypes:
                resolved = self._resolve(file, node, supertype)
                if isinstance(resolved, str):
                    return resolved + self._via(file, node, rel, start)
                key = (resolved[0], int(resolved[1].start_byte))
                if key in seen:
                    continue
                seen.add(key)
                if len(seen) > _MAX_TYPES:
                    return "its supertype closure is too large to check"
                found.append(resolved)
                queue.append(resolved)
        return found

    def _via(self, file: str, node: Any, rel: str, start: Any) -> str:
        """`` (via `Res`)`` when the clause is not on the declaring type itself."""
        parsed = self.parse(file)
        if parsed is None or (file, node.start_byte) == (rel, start.start_byte):
            return ""
        name = _owner_name(parsed, node)
        return f" (via `{name}`)" if name else ""

    def declares(self, rel: str, node: Any, bare: str) -> bool:
        """A type in the closure declares a member (function or property) ``bare``."""
        parsed = self.parse(rel)
        if parsed is None:
            return False
        body = _body(node)
        members = [] if body is None else list(body.named_children)
        for child in node.children:
            if child.type == "primary_constructor":
                members.extend(_walk(child))
        for member in members:
            if member.type == "function_declaration":
                name = _name_node(member)
            elif member.type == "property_declaration":
                name = next(
                    (
                        _name_node(d)
                        for d in _walk(member)
                        if d.type == "variable_declaration"
                    ),
                    None,
                )
            elif member.type == "class_parameter" and any(
                c.type in {"val", "var"} for c in member.children
            ):
                name = _name_node(member)
            else:
                continue
            if name is not None and parsed.text(name) == bare:
                return True
        return False

    def _resolve(self, file: str, user: Any, supertype: Any) -> tuple[str, Any] | str:
        if isinstance(supertype, tuple):  # enum entry -> its enum class (same file)
            return file, supertype[1]
        parsed = self.parse(file)
        if parsed is None:  # pragma: no cover — every queued file was parsed
            return "a file in its supertype closure could not be parsed"
        segments = _segments(parsed, supertype) if supertype.type == "user_type" else []
        if not segments:
            return (
                f"its supertype `{parsed.text(supertype)}` is not a type name "
                "that can be resolved"
            )
        head = self._simple(file, parsed, user, segments[0])
        if isinstance(head, str):
            return head
        if head is not None:
            nested = self._nested(head, segments[1:])
            if nested is not None:
                return nested
        if len(segments) > 1:
            qualified = self._qualified(tuple(segments))
            if isinstance(qualified, str) or qualified is not None:
                return qualified
        return f"its supertype `{'.'.join(segments)}` is declared outside the project"

    def _simple(
        self, file: str, parsed: _Parsed, user: Any, name: str
    ) -> tuple[str, Any] | str | None:
        """The project type a simple name denotes at ``user``; None when none does."""
        aliases = [n for n in _walk(parsed.root) if n.type == "type_alias"]
        if any(_alias_name(parsed, n) == name for n in aliases):
            return f"its supertype `{name}` is a type alias"
        declared = [
            n
            for n in _walk(parsed.root)
            if n.type in _TYPE_DECLARATIONS
            and _name_node(n) is not None
            and parsed.text(_name_node(n)) == name
            and _in_scope(n, user)
        ]
        nested = [
            n for n in declared if n.parent is not None and n.parent.type in _BODIES
        ]
        imports = _imports(parsed)
        explicit = [i for i in imports if not i.star and i.local == name]
        if len(nested) == 1:
            return file, nested[0]
        if len(declared) > 1 or (declared and explicit):
            return f"its supertype `{name}` is ambiguous in {file}"
        if declared:
            return file, declared[0]
        if explicit:
            found = self._qualified(explicit[0].path)
            if found is None:
                dotted = ".".join(explicit[0].path)
                return f"its supertype `{name}` (`{dotted}`) is declared outside the project"
            return found
        same = self._top_level(name, _package(parsed))
        if isinstance(same, str) or same:
            return _one(same, name)
        starred: list[tuple[str, Any]] = []
        for star in (i for i in imports if i.star):
            in_package = self._top_level(name, ".".join(star.path))
            if isinstance(in_package, str):
                return in_package
            starred.extend(in_package)
        return _one(starred, name) if starred else None

    def _qualified(self, path: tuple[str, ...]) -> tuple[str, Any] | str | None:
        """``pkg.Top.Nested`` as a project type; None when no split names one."""
        for split in range(len(path) - 1, -1, -1):
            package, top, rest = ".".join(path[:split]), path[split], path[split + 1 :]
            candidates = self._top_level(top, package)
            if isinstance(candidates, str):
                return candidates
            if len(candidates) > 1:
                return f"its supertype `{'.'.join(path)}` is ambiguous in the project"
            if candidates:
                return self._nested(candidates[0], list(rest))
        return None

    def _nested(
        self, start: tuple[str, Any], rest: list[str]
    ) -> tuple[str, Any] | None:
        file, node = start
        parsed = self.parse(file)
        for name in rest:
            body = _body(node)
            if parsed is None or body is None:
                return None
            matches = [
                c
                for c in body.named_children
                if c.type in _TYPE_DECLARATIONS
                and _name_node(c) is not None
                and parsed.text(_name_node(c)) == name
            ]
            if len(matches) != 1:
                return None
            node = matches[0]
        return file, node

    def _top_level(self, name: str, package: str) -> list[tuple[str, Any]] | str:
        try:
            rows = self._cache.get_conn().execute(
                "SELECT DISTINCT file_path FROM ast_symbol_rows "
                "WHERE name = ? AND kind = 'class' AND language = 'kotlin'",
                (name,),
            )
            files = sorted(str(row[0]) for row in rows)
        except (sqlite3.Error, AttributeError):
            return "the project's types could not be read"
        found: list[tuple[str, Any]] = []
        for candidate in files:
            parsed = self.parse(candidate)
            if parsed is None:
                return "a candidate supertype file could not be parsed"
            if _package(parsed) != package:
                continue
            found.extend(
                (candidate, node)
                for node in parsed.root.children
                if node.type in _TYPE_DECLARATIONS
                and _name_node(node) is not None
                and parsed.text(_name_node(node)) == name
            )
        return found


def _one(found: list[tuple[str, Any]] | str, name: str) -> tuple[str, Any] | str:
    if isinstance(found, str):
        return found
    if len(found) == 1:
        return found[0]
    return f"its supertype `{name}` is ambiguous in the project"


def _alias_name(parsed: _Parsed, node: Any) -> str | None:
    name = _name_node(node)
    return None if name is None else parsed.text(name)


def _in_scope(candidate: Any, user: Any) -> bool:
    """A same-file type is visible to ``user``'s supertype list: it is top-level,
    or declared in a body that strictly encloses ``user``."""
    container = candidate.parent  # a declaration below the root has a parent
    if container.type == "source_file":
        return True
    current = user.parent
    while current is not None:
        if (current.type, current.start_byte, current.end_byte) == (
            container.type,
            container.start_byte,
            container.end_byte,
        ):
            return True
        current = current.parent
    return False


__all__ = [
    "ANY_METHODS",
    "KOTLIN_OVERRIDE_VERB",
    "KOTLIN_SUFFIXES",
    "kotlin_supertype_finding",
    "override_proof",
]
