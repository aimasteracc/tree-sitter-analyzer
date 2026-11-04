"""Project classes, their supertypes, and when two classes are provably unrelated.

A supertype counts as resolved only when the file that names it binds that
name to the project class of the same name (TS: a class declared in the file
or an un-aliased import from a module that exports it; Java: no aliasing
exists, but an import of a non-project type is external). Anything else --
an aliased import or re-export, ``extends ns.Base``, ``extends Mixin(Base)``,
an unknown name -- is an unresolved marker, and an ancestry that contains one
is never "provably unrelated".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .oracle_bindings import bindings_of, name_binds_class_ts
from .oracle_syntax import CLASS_TYPES, INTERFACE_TYPES, Repo, text, walk

#: Supertype names that are never project code (their ancestry cannot reach a project class).
BUILTIN_SUPERTYPES = {
    "java": {
        "Object",
        "Exception",
        "RuntimeException",
        "Error",
        "Throwable",
        "Enum",
        "Record",
        "Comparable",
        "Iterable",
        "Serializable",
        "Cloneable",
        "AutoCloseable",
        "Closeable",
        "Runnable",
    },
    "ts": {
        "Error",
        "Object",
        "Array",
        "Map",
        "Set",
        "Promise",
        "EventTarget",
        "TypeError",
        "RangeError",
        "Function",
        "ReadableStream",
        "WritableStream",
        "TransformStream",
        "Response",
        "Request",
        "Headers",
    },
}
UNRESOLVED = "<unresolved>"
_SUPER_CLAUSES = (
    "superclass",
    "super_interfaces",
    "extends_interfaces",
    "class_heritage",
    "extends_clause",
    "implements_clause",
    "extends_type_clause",
)
_TYPE_NODES = (
    "type_identifier",
    "identifier",
    "scoped_type_identifier",
    "generic_type",
    "member_expression",
    "call_expression",
    "nested_type_identifier",
)
_CONTAINERS = (
    "generic_type",
    "type_arguments",
    "scoped_type_identifier",
    "member_expression",
    "nested_type_identifier",
)


@dataclass
class ClassInfo:
    supers: set[str] = field(default_factory=set)
    interface: bool = False


@dataclass
class ClassTable:
    family: str
    classes: dict[str, ClassInfo]
    _ancestry: dict[str, tuple[frozenset[str], bool]] = field(default_factory=dict)

    def __contains__(self, name: object) -> bool:
        return name in self.classes

    def ancestors(self, name: str) -> tuple[frozenset[str], bool]:
        """(transitive supertypes, whether every one resolved to a project or builtin type)."""
        if name in self._ancestry:
            return self._ancestry[name]
        builtins = BUILTIN_SUPERTYPES[self.family]
        seen: set[str] = set()
        closed = True
        stack = [name]
        while stack:
            info = self.classes.get(stack.pop())
            if info is None:
                continue
            for sup in info.supers:
                if sup in seen:
                    continue
                seen.add(sup)
                if sup in self.classes:
                    stack.append(sup)
                elif sup not in builtins:
                    closed = False  # an unknown name may be an alias of a project class
        result = (frozenset(seen), closed)
        self._ancestry[name] = result
        return result

    def related(self, a: str, b: str) -> bool:
        """True unless ``a`` and ``b`` are *provably* unrelated by inheritance.

        Provably unrelated: different project classes, neither an interface,
        both ancestries fully resolve, neither is an ancestor of the other,
        and no project class has both in its ancestry (a common subtype can
        dispatch either way) -- nor touches either one through an ancestry
        that does not resolve.
        """
        if a == b or a not in self.classes or b not in self.classes:
            return True
        if self.classes[a].interface or self.classes[b].interface:
            return True
        anc_a, closed_a = self.ancestors(a)
        anc_b, closed_b = self.ancestors(b)
        if not (closed_a and closed_b) or b in anc_a or a in anc_b:
            return True
        for name in self.classes:
            anc, closed = self.ancestors(name)
            span = anc | {name}
            if a in span and b in span:
                return True
            if not closed and (a in span or b in span):
                return True
        return False


def raw_supertypes(node: Any) -> list[str]:
    """Supertype names as written (``<mixin>`` for a call such as ``extends Mixin(Base)``)."""
    out: list[str] = []
    for child in node.children:
        if child.type not in _SUPER_CLAUSES:
            continue
        for sub in walk(child):
            if sub.type not in _TYPE_NODES:
                continue
            if sub.type == "call_expression":
                out.append("<mixin>")
                break
            if (
                sub.parent is not None
                and sub.parent.type in _CONTAINERS
                and sub.parent is not child
            ):
                continue
            out.append(re.sub(r"<.*", "", text(sub).strip(), flags=re.S).strip())
    return [s for s in out if s]


def _resolve_ts(repo: Repo, rel: str, raw: str) -> str:
    builtins = BUILTIN_SUPERTYPES["ts"]
    if raw.startswith("<") or "." in raw:
        return (
            UNRESOLVED  # a mixin call or `ns.Base`: not provably a named project class
        )
    if raw in builtins and not bindings_of(repo, rel, raw):
        return raw  # a global builtin the file does not rebind
    return raw if name_binds_class_ts(repo, rel, raw) else UNRESOLVED


def _java_imports(root: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in root.children:
        if node.type != "import_declaration" or "static" in text(node).split():
            continue
        m = re.search(r"import\s+([A-Za-z0-9_.]+)\s*;", text(node))
        if m:
            out[m.group(1).rsplit(".", 1)[-1]] = m.group(1)
    return out


def _resolve_java(raw: str, imports: dict[str, str], packages: set[str]) -> str:
    simple = raw.rsplit(".", 1)[-1].strip()
    fqn = imports.get(simple)
    if fqn is not None:
        package = fqn.rsplit(".", 1)[0]
        if not any(package == p or package.startswith(p + ".") for p in packages):
            return UNRESOLVED  # an imported non-project type of the same simple name
    return simple


def java_packages(repo: Repo) -> set[str]:
    if "java_packages" not in repo.memo:
        out = repo.git(
            "grep", "-h", "-E", r"^\s*package\s+[A-Za-z0-9_.]+\s*;", "--", "*.java"
        )
        repo.memo["java_packages"] = {
            m.group(1) for m in re.finditer(r"package\s+([A-Za-z0-9_.]+)", out)
        }
    packages: set[str] = repo.memo["java_packages"]
    return packages


def class_table(repo: Repo, fam: str) -> ClassTable:
    """Simple class name -> union of resolved supertypes over every same-named class."""
    key = f"classes:{fam}"
    if key in repo.memo:
        cached: ClassTable = repo.memo[key]
        return cached
    table: dict[str, ClassInfo] = {}
    packages = java_packages(repo) if fam == "java" else set()
    for rel in repo.files(fam):
        parsed = repo.tree(rel)
        if parsed is None:
            continue
        root = parsed[0].root_node
        imports = _java_imports(root) if fam == "java" else {}
        for node in walk(root):
            if node.type not in CLASS_TYPES:
                continue
            name = node.child_by_field_name("name")
            if name is None:
                continue
            info = table.setdefault(text(name), ClassInfo())
            info.interface = info.interface or node.type in INTERFACE_TYPES
            for raw in raw_supertypes(node):
                info.supers.add(
                    _resolve_java(raw, imports, packages)
                    if fam == "java"
                    else _resolve_ts(repo, rel, raw)
                )
    result = ClassTable(fam, table)
    repo.memo[key] = result
    return result


def enclosing_class(node: Any, fam: str) -> tuple[str | None, str]:
    """Name of the class whose ``this`` the node sees, or (None, why)."""
    current = node.parent
    while current is not None:
        if (
            fam == "java"
            and current.type == "class_body"
            and current.parent is not None
            and current.parent.type in ("object_creation_expression", "enum_constant")
        ):
            return None, "inside an anonymous class body"
        if fam == "ts" and current.type in (
            "function_expression",
            "function_declaration",
            "generator_function",
            "generator_function_declaration",
            "function",
        ):
            return None, "inside a non-arrow function (its own `this`)"
        if fam == "ts" and current.type == "object":
            return None, "inside an object literal"
        if current.type in CLASS_TYPES:
            name = current.child_by_field_name("name")
            return (text(name) or None), ("anonymous class" if name is None else "")
        current = current.parent
    return None, "not inside a class"


def all_enclosing_classes(node: Any) -> list[str] | None:
    """Every named Java class around ``node`` (innermost first); None inside an anonymous class."""
    out = []
    current = node.parent
    while current is not None:
        if (
            current.type == "class_body"
            and current.parent is not None
            and current.parent.type in ("object_creation_expression", "enum_constant")
        ):
            return None
        if current.type in CLASS_TYPES:
            name = current.child_by_field_name("name")
            if name is None:
                return None
            out.append(text(name))
        current = current.parent
    return out


def innermost_named_class(node: Any) -> str | None:
    current = node.parent
    while current is not None:
        if current.type in CLASS_TYPES:
            name = current.child_by_field_name("name")
            if name is not None:
                return text(name)
        current = current.parent
    return None


def class_of_target(qual: str) -> str | None:
    parts = qual.strip('"').split(".")
    return parts[-2] if len(parts) >= 2 else None
