"""Kotlin rules of the grep oracle (#1933).

Called by :func:`.oracle_grep.classify` for a hit in a ``.kt`` / ``.kts`` file
after the shared checks (parse error, listed caller, comment, string). The
rules are deliberately conservative; every doubt answers ``residual``:

* A bare call ``make()`` or ``this.make()`` inside a class body means
  ``this.make()``, so it may dispatch to an override in a subclass (#1926). It
  is ``other_symbol`` only when every enclosing class is a project class that
  is provably unrelated to the target's class (:meth:`ClassTable.related`),
  and nothing between the hit and the class may bring another implicit
  receiver: a lambda (``apply {}``, ``with(x) {}``, ``x.run {}``, DSL
  builders: the oracle does not trust any host list), an anonymous function,
  an extension function or property, a companion object, an object
  expression, an enum entry body, a labelled ``this@X`` or a script file. Top
  level code outside all of these has no implicit receiver.
* The own declaration of an ``override fun`` is residual unless every
  supertype in its class's ancestry is a project class and one of them
  declares the name (#1930): an override of a JDK / library type, of a
  default import (``Comparable``) or of an ``Any`` member can be called by
  code the project does not contain.
* A member call on any other receiver (``x.make()``), a callable reference
  (``::make``), an infix call and an aliased import are residual. A Kotlin
  function is used only by a call, an infix call or ``::name``, so any other
  occurrence of the bare name (a property read, a named argument, a type) is
  ``other_symbol``.
"""

from __future__ import annotations

import re
from typing import Any

from .oracle_classes import UNRESOLVED, ClassInfo, ClassTable, class_of_target
from .oracle_syntax import Repo, chain, text, walk

KOTLIN_CLASSES = ("class_declaration", "object_declaration")
#: Scopes between a hit and its class whose implicit receivers the oracle cannot name.
OPAQUE_SCOPES = {
    "lambda_literal": "inside a lambda (it may have a receiver: apply / with / run / DSL builders)",
    "anonymous_function": "inside an anonymous function (it may have a receiver)",
    "companion_object": "inside a companion object (its own members and supertypes are in scope)",
    "object_literal": "inside an object expression (an anonymous subtype)",
    "enum_entry": "inside an enum entry (an anonymous subtype)",
}
#: Members of ``kotlin.Any``: an override of one is called by code outside the project.
ANY_MEMBERS = frozenset({"equals", "hashCode", "toString"})
#: Declarations whose name is a ``name`` field.
_NAMED_FIELD = ("function_declaration", *KOTLIN_CLASSES, "companion_object")
#: Declarations whose name is their first identifier child.
_FIRST_IDENTIFIER = (
    "variable_declaration",
    "parameter",
    "class_parameter",
    "enum_entry",
    "type_alias",
    "type_parameter",
)
_TYPE_NODES = ("user_type", "nullable_type", "parenthesized_type", "function_type")
_NOT_A_CALL = (
    "not a call: a Kotlin function is used only by a call, an infix call or `::name`"
)


def classify_kotlin(repo: Repo, item: Any, rel: str, node: Any) -> tuple[str, str]:
    """Class of a Kotlin hit that is not a listed caller, a comment or a string."""
    parent = node.parent
    if parent is None:
        return "residual", "no syntax parent at the occurrence"
    if any(a.type == "package_header" for a in chain(node)):
        return "declaration", "package name"
    imp = next((a for a in chain(node) if a.type == "import" and a.is_named), None)
    if imp is not None:
        return _import(imp, node, item.name)
    if parent.type in (*_NAMED_FIELD, *_FIRST_IDENTIFIER) and _same(
        declared_name(parent), node
    ):
        return _declaration(repo, item, rel, parent)
    if parent.type == "callable_reference":
        return "residual", "callable reference `::name` (called wherever it is passed)"
    if parent.type == "infix_expression":
        return "residual", "infix call (`a name b`)"
    if parent.type == "navigation_expression":
        return _member(repo, item, rel, parent, node)
    if parent.type == "call_expression" and _same(_first_named(parent), node):
        return _implicit(repo, item, rel, node, "bare call")
    if parent.type == "value_argument" and _named_argument(parent, node):
        return "other_symbol", "a named argument label"
    if parent.type == "user_type":
        return "other_symbol", "a type name"
    return "other_symbol", _NOT_A_CALL


def _same(a: Any | None, b: Any) -> bool:
    return a is not None and a.id == b.id


def _first_named(node: Any) -> Any | None:
    return node.named_children[0] if node.named_children else None


def declared_name(decl: Any) -> Any | None:
    """The name token of a Kotlin declaration node, or None."""
    if decl.type in _NAMED_FIELD:
        return decl.child_by_field_name("name")
    return next((c for c in decl.named_children if c.type == "identifier"), None)


def _named_argument(argument: Any, node: Any) -> bool:
    """``f(name = x)``: the first child, followed by ``=``."""
    children = argument.children
    return len(children) >= 2 and children[0].id == node.id and children[1].type == "="


def _import(imp: Any, node: Any, name: str) -> tuple[str, str]:
    alias = next(
        (c for c in imp.named_children if c.type == "identifier"),
        None,
    )
    if alias is None or alias.id == node.id:
        return "import_export", ""
    return "residual", f"imported as `{text(alias)}` (that name is not searched)"


def _member(repo: Repo, item: Any, rel: str, nav: Any, node: Any) -> tuple[str, str]:
    children = nav.named_children
    if len(children) < 2 or children[-1].id != node.id:
        return "other_symbol", f"the name is a receiver; {_NOT_A_CALL}"
    receiver = children[0]
    if receiver.type == "this_expression":
        if receiver.named_children:
            return "residual", "a labelled `this@...` (its receiver is not resolved)"
        return _implicit(repo, item, rel, node, "`this` call")
    if receiver.type == "super_expression":
        return "residual", "a `super` call"
    return "residual", "member access on a receiver of unknown type"


# -- implicit receivers --------------------------------------------------------


def _has_receiver_type(decl: Any) -> bool:
    """``fun Box.f()`` / ``val Box.p``: a type written before the name."""
    stop = (
        decl.child_by_field_name("name")
        if decl.type == "function_declaration"
        else None
    )
    for child in decl.named_children:
        if child.type == "variable_declaration" or (
            stop is not None and child.id == stop.id
        ):
            return False
        if child.type in _TYPE_NODES:
            return True
    return False


def _context_receivers(decl: Any) -> bool:
    return any("context" in c.type for c in decl.children) or any(
        text(m).lstrip().startswith("context")
        for m in decl.children
        if m.type == "modifiers"
    )


def enclosing_classes(node: Any) -> tuple[list[str] | None, str]:
    """Named classes / objects around ``node`` (innermost first), or (None, why)
    when a scope in between may bring an implicit receiver the oracle cannot name."""
    out: list[str] = []
    current = node.parent
    while current is not None:
        kind = current.type
        if kind == "ERROR":
            return None, "parse error around the occurrence"
        if kind in OPAQUE_SCOPES:
            return None, OPAQUE_SCOPES[kind]
        if kind in ("function_declaration", "property_declaration"):
            if _has_receiver_type(current):
                return None, "inside an extension (its receiver is implicit)"
            if _context_receivers(current):
                return None, "inside a declaration with context receivers"
        if kind in KOTLIN_CLASSES:
            name = current.child_by_field_name("name")
            if name is None:
                return None, "inside an unnamed class"
            if _context_receivers(current):
                return None, "inside a class with context receivers"
            out.append(text(name))
        current = current.parent
    return out, ""


def _imports(root: Any) -> list[tuple[str, str | None, bool]]:
    """(qualified name, alias, star) of every import of a file."""
    out = []
    for node in walk(root):
        if node.type != "import" or not node.is_named:
            continue
        path = next(
            (c for c in node.named_children if c.type == "qualified_identifier"), None
        )
        if path is None:
            continue
        alias = next((c for c in node.named_children if c.type == "identifier"), None)
        star = text(node).rstrip().rstrip(";").rstrip().endswith("*")
        out.append((text(path), text(alias) if alias is not None else None, star))
    return out


def _import_binds(root: Any, name: str) -> bool:
    return any(
        alias == name or (alias is None and path.rsplit(".", 1)[-1] == name)
        for path, alias, _star in _imports(root)
    )


def _implicit(repo: Repo, item: Any, rel: str, node: Any, how: str) -> tuple[str, str]:
    if rel.endswith(".kts"):
        return (
            "residual",
            f"{how} inside a script (a script may have an implicit receiver)",
        )
    classes, why = enclosing_classes(node)
    if classes is None:
        return "residual", f"{how} {why}"
    parsed = repo.tree(rel)
    if parsed is None or _import_binds(parsed[0].root_node, item.name):
        return (
            "residual",
            f"{how}: an import binds the name (it may be an object member)",
        )
    target_cls = class_of_target(item.qual)
    if target_cls is None:
        return (
            "residual",
            f"{how} of a top-level or extension target (scope not modelled)",
        )
    table = kotlin_class_table(repo)
    _anc, closed = table.ancestors(target_cls)
    if target_cls not in table or not closed:
        return "residual", f"the ancestry of {target_cls} does not fully resolve"
    if not declared_directly_in(repo, item, target_cls):
        return (
            "residual",
            f"the target is not declared directly in class {target_cls} (companion, "
            "object expression, enum entry, extension, or not found)",
        )
    if not classes:
        return (
            "other_symbol",
            f"{how} outside any class, lambda or extension (no implicit receiver)",
        )
    related = [c for c in classes if table.related(c, target_cls)]
    if related:
        return (
            "residual",
            f"{how} inside {classes}: {related} is related to {target_cls} or has an "
            "unresolved ancestry (#1926: it may dispatch to the target)",
        )
    return "other_symbol", f"{how} inside {classes}, unrelated to {target_cls}"


# -- declarations and overrides ------------------------------------------------


def _scope_of(decl: Any) -> Any | None:
    """The nearest class-like scope, function or lambda around a declaration."""
    current = decl.parent
    while current is not None:
        if current.type in (*KOTLIN_CLASSES, *OPAQUE_SCOPES, "function_declaration"):
            return current
        current = current.parent
    return None


def _scope_name(scope: Any | None) -> str | None:
    if scope is None or scope.type not in KOTLIN_CLASSES:
        return None
    name = scope.child_by_field_name("name")
    return text(name) if name is not None else None


def _declaration(repo: Repo, item: Any, rel: str, decl: Any) -> tuple[str, str]:
    if decl.type != "function_declaration" or rel != item.file:
        return "declaration", ""
    target_cls = class_of_target(item.qual)
    scope = _scope_of(decl)
    if target_cls is not None and _scope_name(scope) != target_cls:
        return "declaration", ""
    if _is_override(decl):
        external = _override_outside_project(repo, decl, scope, item.name)
        if external:
            return (
                "residual",
                f"override of a supertype outside the project ({external}): code "
                "outside the project may call it (#1930)",
            )
    return "own_declaration", ""


def _is_override(decl: Any) -> bool:
    return any(
        c.type == "modifiers" and re.search(r"\boverride\b", text(c))
        for c in decl.children
    )


def _override_outside_project(
    repo: Repo, decl: Any, scope: Any | None, name: str
) -> str:
    """Why an override may implement a member declared outside the project ('' if not)."""
    if name in ANY_MEMBERS:
        return f"`{name}` is a member of kotlin.Any"
    cls = _scope_name(scope)
    if cls is None or _has_receiver_type(decl):
        return "declared in an object expression, companion object or enum entry"
    table = kotlin_class_table(repo)
    ancestors, closed = table.ancestors(cls)
    if not closed:
        return f"the ancestry of {cls} does not resolve to project classes"
    outside = sorted(a for a in ancestors if a not in table)
    if outside:
        return f"{cls} extends {', '.join(outside)}"
    members = kotlin_members(repo)
    if not any(name in members.get(a, ()) for a in ancestors):
        return f"no project supertype of {cls} declares `{name}`"
    return ""


def declared_directly_in(repo: Repo, item: Any, cls: str) -> bool:
    """Every same-named ``fun`` of class ``cls`` in the target's file is a plain member.

    A target declared in a companion object, object expression, enum entry or
    as a member extension of ``cls`` has no provable dispatch class.
    """
    parsed = repo.tree(item.file)
    if parsed is None:
        return False
    found = False
    for node in walk(parsed[0].root_node):
        if node.type != "function_declaration":
            continue
        name = node.child_by_field_name("name")
        if name is None or text(name) != item.name:
            continue
        scope = _scope_of(node)
        if _scope_name(scope) == cls:
            if _has_receiver_type(node):
                return False
            found = True
        elif _nearest_named_class(node) == cls:
            return False  # under cls, but inside an anonymous or local scope
    return found


def _nearest_named_class(node: Any) -> str | None:
    current = node.parent
    while current is not None:
        if current.type in KOTLIN_CLASSES:
            name = current.child_by_field_name("name")
            if name is not None:
                return text(name)
        current = current.parent
    return None


# -- the class table -------------------------------------------------------------


def kotlin_packages(repo: Repo) -> set[str]:
    if "kotlin_packages" not in repo.memo:
        out = repo.git(
            "grep", "-h", "-E", r"^\s*package\s+[A-Za-z0-9_.]+", "--", "*.kt", "*.kts"
        )
        repo.memo["kotlin_packages"] = {
            m.group(1) for m in re.finditer(r"package\s+([A-Za-z0-9_.]+)", out)
        }
    packages: set[str] = repo.memo["kotlin_packages"]
    return packages


def _in_project(package: str, packages: set[str]) -> bool:
    return any(package == p or package.startswith(p + ".") for p in packages)


def raw_supertypes(decl: Any) -> list[str]:
    """Supertype names as written, without type arguments (``a.B`` keeps its dots)."""
    specs: list[Any] = []
    for child in decl.children:
        if child.type == "delegation_specifiers":
            specs.extend(
                c for c in child.named_children if c.type == "delegation_specifier"
            )
        elif child.type == "delegation_specifier":
            specs.append(child)
    out = []
    for spec in specs:
        user_type = next((n for n in walk(spec) if n.type == "user_type"), None)
        if user_type is None:
            continue  # a function type names no class
        parts = [text(c) for c in user_type.named_children if c.type == "identifier"]
        if parts:
            out.append(".".join(parts))
    return out


def _resolve(
    raw: str, imports: list[tuple[str, str | None, bool]], packages: set[str]
) -> str:
    if "." in raw:
        return UNRESOLVED  # a qualified or nested name: not provably one project class
    explicit = None
    for path, alias, star in imports:
        if star:
            continue
        if alias == raw:
            return UNRESOLVED  # `import x.Y as Raw`
        if alias is None and path.rsplit(".", 1)[-1] == raw:
            explicit = path
    if explicit is not None:
        package = explicit.rsplit(".", 1)[0]
        return raw if _in_project(package, packages) else UNRESOLVED
    if any(star and not _in_project(path, packages) for path, _a, star in imports):
        return UNRESOLVED  # a star import of a library may supply the name
    return raw


def kotlin_class_table(repo: Repo) -> ClassTable:
    """Simple class / object name -> union of resolved supertypes (Kotlin files only)."""
    key = "classes:kotlin"
    if key in repo.memo:
        cached: ClassTable = repo.memo[key]
        return cached
    packages = kotlin_packages(repo)
    table: dict[str, ClassInfo] = {}
    members: dict[str, set[str]] = {}
    for rel in repo.files("kotlin"):
        parsed = repo.tree(rel)
        if parsed is None:
            continue
        root = parsed[0].root_node
        imports = _imports(root)
        for node in walk(root):
            if node.type not in KOTLIN_CLASSES:
                continue
            name = node.child_by_field_name("name")
            if name is None:
                continue
            info = table.setdefault(text(name), ClassInfo())
            info.interface = info.interface or any(
                c.type == "interface" for c in node.children
            )
            for raw in raw_supertypes(node):
                info.supers.add(_resolve(raw, imports, packages))
            declared = members.setdefault(text(name), set())
            for fun in walk(node):
                scope = _scope_of(fun) if fun.type == "function_declaration" else None
                if scope is not None and scope.id == node.id:
                    fun_name = fun.child_by_field_name("name")
                    if fun_name is not None:
                        declared.add(text(fun_name))
    result = ClassTable("kotlin", table)
    repo.memo[key] = result
    repo.memo["kotlin_members"] = members
    return result


def kotlin_members(repo: Repo) -> dict[str, set[str]]:
    """Class name -> names of the functions declared directly in it (union)."""
    kotlin_class_table(repo)
    members: dict[str, set[str]] = repo.memo["kotlin_members"]
    return members
