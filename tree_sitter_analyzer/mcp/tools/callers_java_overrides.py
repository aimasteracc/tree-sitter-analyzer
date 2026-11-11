"""PR-2: when a Java ``@Override`` may still let an unseen caller in.

``@Override`` registers nothing, but it says the method is reached through a
supertype. Two ways in leave no call edge that names the target:

1. **External supertype.** The overridden method is declared outside the project
   (gson ``Adapter.computeValue`` overrides ``java.lang.ClassValue.computeValue``):
   the JDK or a framework calls it. Nothing in the project can prove absence.
2. **Supertype dispatch inside the project.** ``adapter.write(out, v)`` with
   ``TypeAdapter<T> adapter`` is bound to ``TypeAdapter.write``. Since #1880 the
   index has the ``extends`` edge for a generic supertype, so the call graph
   offers the override as a possible target; the source check below still runs,
   because an index built before #1880, an unresolved call edge or a supertype
   reached only through a placeholder leaves no such evidence.

So an ``@Override`` lets ``complete`` through only when both are ruled out:

* **every** supertype in the transitive closure of the declaring type resolves to
  a type declared in the project, read from source (``extends`` / ``implements``,
  Java's name-resolution order: same file, single-type import, same package);
  any qualified, wildcard-only, ``java.lang`` or otherwise unresolved name fails,
  except a JDK type whose overridable members are known
  (:mod:`.callers_java_jdk`, #1884): it ends the walk, and fails only when it
  declares the method's name;
  so does a method named like a ``java.lang.Object`` method (an implicit
  supertype of every class), a record, or a closure larger than
  :data:`_MAX_TYPES`;
* some type in that closure declares a method of the same name;
* every call edge in the project named like the method is bound to this very
  declaration, or to an external / standard-library receiver type (which cannot
  dispatch into a type whose whole closure is in the project). Any other edge
  (unresolved, bound by name, bound to another definition) may be a supertype
  call and keeps the gate shut.

Any read or parse failure keeps the gate shut.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .callers_java_jdk import KnownType, known_type
from .evidence_file_cache import FILE_CACHE

#: completeness reason: the target overrides a supertype method, and a call through
#: the supertype could reach it without a call edge naming it.
OVERRIDE_REASON = "OVERRIDE_DISPATCH"
#: Methods every Java type inherits from ``java.lang.Object`` (``getClass`` and the
#: monitor methods are final and cannot be overridden).
OBJECT_METHODS = frozenset({"equals", "hashCode", "toString", "clone", "finalize"})
#: Call-edge resolutions whose receiver type is outside the project.
_OUTSIDE_RESOLUTIONS = frozenset({"external", "stdlib"})
#: Resolutions that bind by file (``local`` / ``project``) or by receiver type.
_FILE_RESOLUTIONS = frozenset({"local", "project"})
_ANNOTATED = "annotated_receiver"
#: Types visited in one closure before giving up (fail closed).
_MAX_TYPES = 64
#: Sites named in the hint.
_SITES_NAMED = 3
_TYPE_DECLARATIONS = frozenset(
    {"class_declaration", "interface_declaration", "enum_declaration"}
)
_ALL_TYPE_DECLARATIONS = _TYPE_DECLARATIONS | {
    "record_declaration",
    "annotation_type_declaration",
}
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
#: File of a closure entry that is a known JDK type (#1884).
_JDK = "<jdk>"


@dataclass(frozen=True)
class OverrideProof:
    """Whether an ``@Override`` declaration is closed in the project."""

    proved: bool
    #: Why it is not proved (one sentence fragment for the hint).
    detail: str = ""
    #: Call sites that may dispatch here through a supertype (when that is why).
    sites: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def override_proof(
    cache: Any,
    project_root: str,
    rel_path: str,
    text: str,
    line: int,
    bare: str,
    *,
    annotated: bool = True,
) -> OverrideProof:
    """Prove the ``@Override`` declaration of ``bare`` at ``line`` is closed.

    #1884: ``annotated=False`` proves the same for a method without
    ``@Override``, which may still override a supertype method. There, no
    supertype declaring the name means it overrides nothing: proved, once the
    supertype names (the declaring type's and its enclosing types') resolve.
    """
    if bare in OBJECT_METHODS:
        return _fail(
            f"it overrides `java.lang.Object.{bare}`, declared outside the project"
        )
    if cache is None:
        return _fail("the project index could not be read to resolve its supertypes")
    reader = _Reader(cache, project_root)
    parsed = reader.parse(rel_path, text)
    if parsed is None:
        return _fail("its declaring file could not be parsed")
    method = _method_at(parsed, line, bare)
    if method is None:
        return _fail("its declaration could not be located")
    owner = _owner_type(method)
    if owner is None:
        return _fail("its declaring type is not a class, interface or enum")
    closure = reader.closure(rel_path, [owner])
    if isinstance(closure, str):
        return _fail(closure)
    external = next(
        (
            node.qualified
            for file, node in closure
            if file == _JDK and bare in node.members
        ),
        None,
    )
    if external is not None:
        return _fail(f"it overrides `{external}.{bare}`, declared outside the project")
    declared = any(reader.declares(file, node, bare) for file, node in closure)
    if annotated and not declared:
        return _fail("no supertype in the project declares it")
    # A member type inherited by an enclosing type is in scope for the owner's
    # supertype names, so the enclosing types must be closed in the project too.
    enclosing = reader.closure(rel_path, _enclosing_types(owner))
    if isinstance(enclosing, str):
        return _fail(
            enclosing.replace("its supertype", "an enclosing type's supertype")
        )
    if not declared:
        return OverrideProof(True)  # #1884: overrides nothing
    owner_name = _name(parsed, owner)
    sites = _dispatch_sites(cache, bare, rel_path, line, owner_name)
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


def override_hint(func_name: str, detail: str) -> str:
    """next_step of the override gate."""
    return (
        f"No resolved caller for {func_name!r}, but it carries `@Override` and "
        f"{detail}, so a caller through the supertype would leave no call edge "
        "naming it; this is not evidence of absence."
    )


def _fail(detail: str) -> OverrideProof:
    return OverrideProof(False, detail)


def _describe(sites: list[dict[str, Any]]) -> str:
    named = [f"{site['file']}:{site['line']}" for site in sites[:_SITES_NAMED]]
    if len(sites) > _SITES_NAMED:
        named.append(f"and {len(sites) - _SITES_NAMED} more")
    return "; ".join(named)


@dataclass(frozen=True)
class _Parsed:
    source: bytes
    root: Any


class _Reader:
    """Reads and parses project Java files, resolving supertype names from source."""

    def __init__(self, cache: Any, project_root: str) -> None:
        self._cache = cache
        self._root = project_root
        self._parsed: dict[str, _Parsed | None] = {}

    def parse(self, rel_path: str, text: str | None = None) -> _Parsed | None:
        if rel_path not in self._parsed:
            if text is None:
                text = FILE_CACHE.read_text(os.path.join(self._root, rel_path))
            self._parsed[rel_path] = None if text is None else _parse(text)
        return self._parsed[rel_path]

    def closure(self, rel_path: str, starts: list[Any]) -> list[tuple[str, Any]] | str:
        """Every supertype of ``starts`` (transitively) as ``(file, node)``, or why not."""
        seen: set[tuple[str, int | str]] = set()
        found: list[tuple[str, Any]] = []
        queue: list[tuple[str, Any]] = [(rel_path, start) for start in starts]
        while queue:
            file, node = queue.pop()
            for supertype in _direct_supertypes(node):
                resolved = self._resolve(file, node, supertype)
                if isinstance(resolved, str):
                    return resolved
                key = _key(resolved)
                if key in seen:
                    continue
                seen.add(key)
                if len(seen) > _MAX_TYPES:
                    return "its supertype closure is too large to check"
                found.append(resolved)
                if resolved[0] != _JDK:  # a known JDK type ends the walk
                    queue.append(resolved)
        return found

    def declares(self, rel_path: str, node: Any, bare: str) -> bool:
        """A project type in the closure declares a method ``bare``."""
        if rel_path == _JDK:
            return False
        parsed = self.parse(rel_path)
        if parsed is None:
            return False
        for member in _members(node):
            if member.type == "method_declaration" and _name(parsed, member) == bare:
                return True
        return False

    def _resolve(self, file: str, node: Any, supertype: Any) -> tuple[str, Any] | str:
        parsed = self.parse(file)
        if parsed is None:
            return "a file in its supertype closure could not be parsed"
        if isinstance(supertype, tuple):  # enum constant body -> its enum (same file)
            return file, supertype[1]
        name = _simple_type_name(parsed, supertype)
        if name is None:
            raw = parsed.source[supertype.start_byte : supertype.end_byte].decode(
                "utf-8", "replace"
            )
            return f"its supertype `{raw}` is not a simple name that can be resolved"
        same_file = [
            n
            for n in _type_declarations(parsed.root)
            if _name(parsed, n) == name and _in_scope(n, node)
        ]
        if len(same_file) == 1:
            return file, same_file[0]
        if same_file:
            return f"its supertype `{name}` is declared more than once in {file}"
        text = parsed.source.decode("utf-8", "replace")
        imported = _single_type_import(text, name)
        package = imported if imported is not None else _package(text)
        candidates = self._top_level(name, package)
        if isinstance(candidates, str):
            return candidates
        if len(candidates) == 1:
            return candidates[0]
        if not candidates and not same_file:
            known = known_type(self._cache, name, imported)
            if known is not None:
                return _JDK, known
        where = "outside the project" if not candidates else "ambiguous in the project"
        return f"its supertype `{name}` is {where}"

    def _top_level(self, name: str, package: str) -> list[tuple[str, Any]] | str:
        try:
            rows = self._cache.get_conn().execute(
                "SELECT DISTINCT file_path FROM ast_symbol_rows "
                "WHERE name = ? AND kind = 'class' AND language = 'java'",
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
            if _package(parsed.source.decode("utf-8", "replace")) != package:
                continue
            found.extend(
                (candidate, node)
                for node in parsed.root.children
                if node.type in _ALL_TYPE_DECLARATIONS and _name(parsed, node) == name
            )
        return found


def _key(resolved: tuple[str, Any]) -> tuple[str, int | str]:
    if isinstance(resolved[1], KnownType):
        return resolved[0], resolved[1].qualified
    return resolved[0], int(resolved[1].start_byte)


def _parse(text: str) -> _Parsed | None:
    from ...language_loader import create_parser_safely

    try:
        parser = create_parser_safely("java")
        if parser is None:
            return None
        source = text.encode("utf-8")
        tree = parser.parse(source)
    except Exception:  # noqa: BLE001 — a grammar failure is "cannot prove"
        return None
    if tree.root_node.has_error:
        return None
    return _Parsed(source, tree.root_node)


def _name(parsed: _Parsed, node: Any) -> str | None:
    name = node.child_by_field_name("name")
    if name is None:
        return None
    return parsed.source[name.start_byte : name.end_byte].decode("utf-8", "replace")


def _walk(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(node.children)
    return found


def _method_at(parsed: _Parsed, line: int, bare: str) -> Any | None:
    """The method declaration named ``bare`` whose header holds ``line``."""
    matches = []
    for node in _walk(parsed.root):
        if node.type != "method_declaration" or _name(parsed, node) != bare:
            continue
        name = node.child_by_field_name("name")
        if int(node.start_point[0]) + 1 <= line <= int(name.start_point[0]) + 1:
            matches.append(node)
    return matches[0] if len(matches) == 1 else None


def _owner_type(method: Any) -> Any | None:
    """The type the method is a member of: a declaration, an anonymous class
    (``object_creation_expression``) or an enum constant body; None otherwise."""
    body = method.parent
    if body is not None and body.type == "enum_body_declarations":
        body = body.parent
    if body is None or body.type not in {"class_body", "interface_body", "enum_body"}:
        return None
    owner = body.parent
    if owner is None:
        return None
    if owner.type in _TYPE_DECLARATIONS or owner.type in {
        "object_creation_expression",
        "enum_constant",
    }:
        return owner
    return None


def _direct_supertypes(node: Any) -> list[Any]:
    """Direct supertype type nodes; an enum constant yields ``("enum", <enum>)``."""
    if node.type == "object_creation_expression":
        created = node.child_by_field_name("type")
        return [] if created is None else [created]
    if node.type == "enum_constant":
        enum = node.parent.parent if node.parent is not None else None
        return [] if enum is None else [("enum", enum)]
    found: list[Any] = []
    for child in node.children:
        if child.type == "superclass":
            found.extend(c for c in child.named_children)
        elif child.type in {"super_interfaces", "extends_interfaces"}:
            for type_list in child.named_children:
                found.extend(type_list.named_children)
    return found


def _simple_type_name(parsed: _Parsed, node: Any) -> str | None:
    if node.type == "generic_type":
        node = node.named_children[0] if node.named_children else node
    if node.type != "type_identifier":
        return None
    return parsed.source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _same(a: Any, b: Any) -> bool:
    return (a.type, a.start_byte, a.end_byte) == (b.type, b.start_byte, b.end_byte)


def _ancestors(node: Any) -> list[Any]:
    found: list[Any] = []
    current = node.parent
    while current is not None:
        found.append(current)
        current = current.parent
    return found


def _in_scope(candidate: Any, user: Any) -> bool:
    """A same-file type declaration is visible to ``user``'s supertype clause: it is
    top-level, or declared in a body / block that strictly encloses ``user``."""
    container = candidate.parent
    if container is None:
        return False
    if container.type == "program":
        return True
    return any(_same(container, ancestor) for ancestor in _ancestors(user))


def _enclosing_types(owner: Any) -> list[Any]:
    """Types that lexically enclose ``owner`` (their members are in its scope)."""
    return [
        node
        for node in _ancestors(owner)
        if node.type in _ALL_TYPE_DECLARATIONS
        or node.type in {"object_creation_expression", "enum_constant"}
    ]


def _type_declarations(root: Any) -> list[Any]:
    return [node for node in _walk(root) if node.type in _ALL_TYPE_DECLARATIONS]


def _members(node: Any) -> list[Any]:
    body = node.child_by_field_name("body")
    if body is None:
        # anonymous class / enum constant: the class_body child
        body = next((c for c in node.children if c.type == "class_body"), None)
    if body is None:
        return []
    members = list(body.named_children)
    for child in body.named_children:
        if child.type == "enum_body_declarations":
            members.extend(child.named_children)
    return members


def _single_type_import(text: str, name: str) -> str | None:
    """The package of ``import p.q.Name;``, if present.

    ``import static p.Outer.Name;`` imports a member type that shadows the same
    package; it is returned as ``p.Outer``, which matches no package (fails closed).
    """
    found = re.search(
        r"^\s*import\s+(?:static\s+)?([\w.]+)\." + re.escape(name) + r"\s*;",
        text,
        re.MULTILINE,
    )
    return found.group(1) if found else None


def _package(text: str) -> str:
    found = _PACKAGE.search(text)
    return found.group(1) if found else ""


def _dispatch_sites(
    cache: Any, bare: str, rel_path: str, line: int, owner: str | None
) -> list[dict[str, Any]] | None:
    """Call edges named ``bare`` not proved to bind to this declaration or outside."""
    try:
        conn = cache.get_conn()
        same_file = int(
            conn.execute(
                "SELECT count(*) FROM ast_symbol_rows WHERE name = ? AND file_path = ? "
                "AND kind IN ('method', 'function')",
                (bare, rel_path),
            ).fetchone()[0]
        )
        rows = list(
            conn.execute(
                "SELECT file_path, line, callee_resolution, callee_resolved_file, "
                "metadata FROM edges WHERE kind = 'calls' AND callee_name = ?",
                (bare,),
            )
        )
    except (sqlite3.Error, AttributeError, TypeError):
        return None
    sites: list[dict[str, Any]] = []
    for file, call_line, resolution, resolved_file, metadata in rows:
        if _bound_here_or_outside(
            str(resolution or ""),
            str(resolved_file or ""),
            metadata,
            rel_path,
            line,
            owner,
            same_file,
        ):
            continue
        sites.append({"file": str(file), "line": int(call_line or 0)})
    sites.sort(key=lambda site: (site["file"], site["line"]))
    return sites


def _bound_here_or_outside(
    resolution: str,
    resolved_file: str,
    metadata: Any,
    rel_path: str,
    line: int,
    owner: str | None,
    same_file: int,
) -> bool:
    if resolution in _OUTSIDE_RESOLUTIONS:
        return True
    if resolved_file != rel_path:
        return False
    if resolution in _FILE_RESOLUTIONS:
        return same_file == 1
    if resolution == _ANNOTATED:
        binding = _binding(metadata)
        return (
            binding is not None
            and owner is not None
            and binding.get("owner") == owner
            and binding.get("line") == line
        )
    return False


def _binding(metadata: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(metadata) if isinstance(metadata, str) else metadata
    except ValueError:
        return None
    binding = parsed.get("receiver_binding") if isinstance(parsed, dict) else None
    return binding if isinstance(binding, dict) else None


__all__ = [
    "OBJECT_METHODS",
    "OVERRIDE_REASON",
    "OverrideProof",
    "override_hint",
    "override_proof",
]
