"""#1937 / #1938: PHP methods reached without a call edge naming them.

PHP has no ``override`` keyword: any method of a class with a parent class, an
interface or a trait may redefine a method of that supertype, and is then
reached by every call through the supertype -- from PHPUnit when the class
extends ``PHPUnit\\Framework\\TestCase`` (``setUp``, ``test*``), or from
``$this->step()`` in a project base class. And the language calls the magic
methods itself (#1938): ``$handler($request)`` runs ``__invoke``, a string
conversion ``__toString``, ``new`` ``__construct``.

A PHP method lets ``complete`` through only when it is no magic method and:

* it is ``private`` (never reached through a supertype), or
* its declaring type is not a trait (whose methods become members of every
  class that uses it), and either has no supertype, or **every** supertype in
  its transitive closure (``extends``, ``implements`` and used traits) resolves
  to one type declared in the project's PHP files -- PHP's rules: a fully
  qualified ``\\A\\B``, a ``use`` import (``as`` aliases and group imports
  included), otherwise the current namespace -- and either no type in it
  declares the method's name (compared case-insensitively, as PHP does), or
  every call edge named like it is bound to this declaration or outside the
  project. A trait ``use`` with an adaptation block (``insteadof`` / ``as``)
  fails.
"""

from __future__ import annotations

import os
import re
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
from .callers_supertypes import SupertypeFinding
from .evidence_file_cache import FILE_CACHE

PHP_SUFFIXES = (".php",)
_ACCESS = "access to an inaccessible property"
_SERIAL = "`serialize` / `unserialize`"
#: Methods PHP calls implicitly (lowercase; PHP method names are
#: case-insensitive), with what runs them.
MAGIC_METHODS: dict[str, str] = {
    "__construct": "`new`",
    "__destruct": "the object's destruction",
    "__call": "a call of an inaccessible method",
    "__callstatic": "a static call of an inaccessible method",
    "__get": _ACCESS,
    "__set": _ACCESS,
    "__isset": _ACCESS,
    "__unset": _ACCESS,
    "__sleep": _SERIAL,
    "__wakeup": _SERIAL,
    "__serialize": _SERIAL,
    "__unserialize": _SERIAL,
    "__tostring": "a string conversion",
    "__invoke": "calling the object (`$obj(...)`)",
    "__set_state": "`var_export`",
    "__clone": "`clone`",
    "__debuginfo": "`var_dump`",
}
_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "trait_declaration",
        "enum_declaration",
    }
)
_BODIES = frozenset({"declaration_list", "enum_declaration_list"})
_NAMES = frozenset({"name", "qualified_name", "relative_name"})
#: Children of a supertype clause that name no supertype.
_NOT_NAMES = frozenset({"comment", "use_list"})
_USE_CLAUSE = re.compile(r"^\\?([\w\\]+)(?:\s+as\s+(\w+))?$", re.IGNORECASE)
_REDEFINES_VERB = "may redefine"
_REDEFINES_LEAD = (
    "it may redefine a method of a supertype (PHP has no `override` keyword)"
)
_MAGIC_LEAD = "it is a PHP magic method, which the language calls implicitly"


def php_row_finding(
    project_root: str, rel: str, line: int, bare: str, cache: Any
) -> tuple[str | None, SupertypeFinding | None]:
    """``(declaring type name, finding)`` of one PHP declaration row."""
    text = FILE_CACHE.read_text(os.path.join(project_root, rel))
    if text is None:
        return None, unchecked(rel, "the declaring file could not be read")
    parsed = parse("php", text)
    if parsed is None:
        return None, unchecked(rel, "the declaring file could not be parsed")
    method = _method_at(parsed, line, bare)
    if method is None:
        return None, None
    body = method.parent
    owner = body.parent if body is not None and body.type in _BODIES else None
    if owner is not None and owner.type not in _TYPES:
        owner = None
    name = None if owner is None else _name(parsed, owner)
    if bare.lower() in MAGIC_METHODS:
        detail = f"PHP runs it on {MAGIC_METHODS[bare.lower()]}, not by its name"
        return name, finding(
            bare,
            rel,
            line,
            name,
            detail,
            verb="declares the magic method",
            lead=_MAGIC_LEAD,
        )
    if owner is None or _is_private(parsed, method):
        return name, None
    proof = _proof(cache, project_root, rel, parsed, owner, line, bare)
    if proof.proved:
        return name, None
    return name, finding(
        bare, rel, line, name, proof.detail, verb=_REDEFINES_VERB, lead=_REDEFINES_LEAD
    )


def _proof(
    cache: Any,
    project_root: str,
    rel: str,
    parsed: Parsed,
    owner: Any,
    line: int,
    bare: str,
) -> OverrideProof:
    if owner.type == "trait_declaration":
        return fail(
            "it is declared in a trait, whose methods become members of every "
            "class that uses it (and may redefine those classes' supertype methods)"
        )
    if not _clauses(owner):
        return OverrideProof(True)
    if cache is None:
        return fail("the project index could not be read to resolve its supertypes")
    reader = _Reader(cache, project_root, {rel: parsed})
    closure = reader.closure(rel, owner)
    if isinstance(closure, str):
        return fail(closure)
    if not any(reader.declares(file, node, bare) for file, node in closure):
        return OverrideProof(True)
    return dispatch_proof(cache, bare, rel, line, _name(parsed, owner), nocase=True)


def _name(parsed: Parsed, node: Any) -> str | None:
    name = node.child_by_field_name("name")
    if name is None:
        name = next((c for c in node.children if c.type == "name"), None)
    return None if name is None else parsed.text(name)


def _method_at(parsed: Parsed, line: int, bare: str) -> Any | None:
    matches = []
    for node in walk(parsed.root):
        if node.type != "method_declaration":
            continue
        name = node.child_by_field_name("name")
        if name is None or parsed.text(name).lower() != bare.lower():
            continue
        if int(node.start_point[0]) + 1 <= line <= int(name.start_point[0]) + 1:
            matches.append(node)
    return matches[0] if len(matches) == 1 else None


def _is_private(parsed: Parsed, method: Any) -> bool:
    return any(
        c.type == "visibility_modifier" and parsed.text(c).lower() == "private"
        for c in method.children
    )


def _clauses(owner: Any) -> list[Any]:
    """Supertype clauses: ``extends``, ``implements`` and trait ``use``."""
    found = [
        c for c in owner.children if c.type in {"base_clause", "class_interface_clause"}
    ]
    body = next((c for c in owner.children if c.type in _BODIES), None)
    if body is not None:
        found.extend(c for c in body.named_children if c.type == "use_declaration")
    return found


def _context(parsed: Parsed, node: Any) -> tuple[str, dict[str, str]]:
    """``(namespace, {lowercase alias: imported name})`` in effect at ``node``."""
    block = next(
        (
            a
            for a in ancestors(node)
            if a.type == "namespace_definition"
            and a.child_by_field_name("body") is not None
        ),
        None,
    )
    if block is not None:
        body = block.child_by_field_name("body")
        return _ns(parsed, block), _imports(parsed, list(body.named_children))
    namespace = ""
    uses: list[Any] = []
    for child in parsed.root.named_children:
        if child.start_byte >= node.start_byte:
            break
        if child.type == "namespace_definition":
            namespace, uses = _ns(parsed, child), []
        elif child.type == "namespace_use_declaration":
            uses.append(child)
    return namespace, _imports(parsed, uses)


def _ns(parsed: Parsed, definition: Any) -> str:
    name = definition.child_by_field_name("name") or next(
        (c for c in definition.children if c.type == "namespace_name"), None
    )
    return "" if name is None else re.sub(r"\s+", "", parsed.text(name))


def _imports(parsed: Parsed, nodes: list[Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for decl in nodes:
        if decl.type != "namespace_use_declaration":
            continue
        if any(c.type in {"function", "const"} for c in decl.children):
            continue
        group = next(
            (c for c in decl.children if c.type == "namespace_use_group"), None
        )
        prefix = ""
        clauses = [c for c in decl.named_children if c.type == "namespace_use_clause"]
        if group is not None:
            head = next((c for c in decl.children if c.type == "namespace_name"), None)
            prefix = "" if head is None else parsed.text(head).strip("\\") + "\\"
            clauses = [
                c for c in group.named_children if c.type == "namespace_use_clause"
            ]
        for clause in clauses:
            matched = _USE_CLAUSE.match(
                re.sub(r"\s+", " ", parsed.text(clause)).strip()
            )
            if matched is None:
                continue
            target = prefix + matched.group(1)
            alias = matched.group(2) or target.rpartition("\\")[2]
            found[alias.lower()] = target
    return found


def _fqn(parsed: Parsed, node: Any, raw: str) -> str:
    """The fully qualified class name ``raw`` denotes at ``node``."""
    namespace, imports = _context(parsed, node)
    if raw.startswith("\\"):
        return raw[1:]
    if raw.lower().startswith("namespace\\"):
        return "\\".join(p for p in (namespace, raw[len("namespace\\") :]) if p)
    head, sep, rest = raw.partition("\\")
    imported = imports.get(head.lower())
    if imported is not None:
        return imported + sep + rest
    return "\\".join(p for p in (namespace, raw) if p)


class _Reader:
    """Reads project PHP files and resolves supertype names from source."""

    def __init__(self, cache: Any, project_root: str, seed: dict[str, Parsed]) -> None:
        self._cache = cache
        self._root = project_root
        self._parsed: dict[str, Parsed | None] = dict(seed)

    def parse(self, rel: str) -> Parsed | None:
        if rel not in self._parsed:
            text = FILE_CACHE.read_text(os.path.join(self._root, rel))
            self._parsed[rel] = None if text is None else parse("php", text)
        return self._parsed[rel]

    def closure(self, rel: str, start: Any) -> list[tuple[str, Any]] | str:
        seen: set[tuple[str, int]] = set()
        found: list[tuple[str, Any]] = []
        queue: list[tuple[str, Any]] = [(rel, start)]
        while queue:
            file, node = queue.pop()
            parsed = self.parse(file)
            if parsed is None:
                return "a file in its supertype closure could not be parsed"
            for clause in _clauses(node):
                if clause.has_error:
                    return f"a supertype clause in {file} could not be parsed"
                if clause.type == "use_declaration" and any(
                    c.type == "use_list" for c in clause.children
                ):
                    return f"a trait `use` in {file} adapts trait methods"
                for entry in clause.named_children:
                    if entry.type in _NOT_NAMES:
                        continue
                    if entry.type not in _NAMES:
                        return (
                            f"its supertype `{parsed.text(entry)}` in {file} is "
                            "not a name that can be resolved"
                        )
                    resolved = self._resolve(file, parsed, node, entry)
                    if isinstance(resolved, str):
                        return resolved
                    key = (resolved[0], int(resolved[1].start_byte))
                    if key in seen:
                        continue
                    seen.add(key)
                    if len(seen) > MAX_TYPES:
                        return "its supertype closure is too large to check"
                    found.append(resolved)
                    queue.append(resolved)
        return found

    def declares(self, rel: str, node: Any, bare: str) -> bool:
        parsed = self.parse(rel)
        body = next((c for c in node.children if c.type in _BODIES), None)
        if parsed is None or body is None:
            return False
        return any(
            m.type == "method_declaration"
            and (_name(parsed, m) or "").lower() == bare.lower()
            for m in body.named_children
        )

    def _resolve(
        self, file: str, parsed: Parsed, user: Any, entry: Any
    ) -> tuple[str, Any] | str:
        raw = re.sub(r"\s+", "", parsed.text(entry))
        wanted = _fqn(parsed, user, raw).lower()
        short = wanted.rpartition("\\")[2]
        files = class_files(self._cache, "php", short, nocase=True)
        if isinstance(files, str):
            return files
        found: list[tuple[str, Any]] = []
        for candidate in files:
            other = self.parse(candidate)
            if other is None:
                return "a candidate supertype file could not be parsed"
            for node in walk(other.root):
                if node.type not in _TYPES:
                    continue
                name = _name(other, node)
                if name is None or name.lower() != short:
                    continue
                namespace, _imports_ = _context(other, node)
                full = "\\".join(p for p in (namespace, name) if p).lower()
                if full == wanted:
                    found.append((candidate, node))
        if len(found) == 1:
            return found[0]
        if found:
            return f"its supertype `{raw}` is declared more than once in the project"
        return f"its supertype `{raw}` is declared outside the project"


__all__ = ["MAGIC_METHODS", "PHP_SUFFIXES", "php_row_finding"]
