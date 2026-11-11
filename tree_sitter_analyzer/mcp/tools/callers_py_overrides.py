"""#1949: a Python method reached from outside the project, not by a call edge.

.. code-block:: python

    import io
    class _Reader(io.RawIOBase):
        def writable(self): return False   # io calls it

The supertype walk of :mod:`.callers_py_supertypes` stops at a known external
base: no *project* call dispatches through ``io.RawIOBase``, so
``_Reader.writable`` answered ``complete`` with 0 callers although the standard
library calls it. Java, Kotlin, C#, PHP and Swift already refuse ``complete``
for an override of an external supertype.

:func:`python_override_finding` refuses it for Python (``OVERRIDE_DISPATCH``):

* a special method (``__init__``, ``__eq__``, ``__enter__``, a module-level
  ``__getattr__``, ...) is called by the interpreter -- for an operator, a
  builtin, a protocol or a construction -- not by its name: it never passes;
* otherwise the declaring class and every project class above it are walked
  with the import resolver of :mod:`.callers_py_supertypes`. A base outside the
  project (standard library or third party) may define or call the name, so it
  blocks, unless its whole member set is known and holds neither the name nor
  a hook of that shape: a builtin class the module does not rebind
  (``object``, ``Exception``, ``dict``), ``abc.ABC``, ``typing.Generic``,
  ``typing.Protocol``, ``typing.NamedTuple``, ``typing.TypedDict`` and the
  ``enum`` classes (whose ``_sunder_`` names are hooks). An external metaclass
  other than ``type``, ``abc.ABCMeta`` and the ``enum`` one blocks too. A base
  the resolver cannot follow blocks (fail closed);
* a mangled ``__m`` is skipped: no other class spells ``_C__m``.

Classes whose whole MRO resolves in the project are unchanged. The walk reuses
the parse memo of the supertype reader (one parse per file stamp) and the
member table of :mod:`.callers_py_members` (per content digest); it adds no
per-file facts of its own.
"""

from __future__ import annotations

import abc
import ast
import builtins
import enum
import typing
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

from .callers_java_overrides import OVERRIDE_REASON
from .callers_py_members import member_table
from .callers_py_supertypes import (
    _MISSING,
    PY_SUFFIX,
    _base_value,
    _Class,
    _eval,
    _lookup,
    _Module,
    _owner_class,
    _Reader,
    _scopes_for,
)
from .callers_supertypes import SupertypeFinding

#: How the hint introduces an external-base finding.
EXTERNAL_LEAD = "it may override a method of a base class outside the project"
#: How the hint introduces a special-method finding.
SPECIAL_LEAD = "it is a Python special method, which the interpreter calls implicitly"
_SPECIAL_VERB = "declares the special method"
_SPECIAL_WHY = (
    "which runs for an operator, a builtin, a protocol or a construction, "
    "not by a call naming it"
)
#: Classes visited in one walk (bases of bases included).
_CLASSES_MAX = 64
#: Metaclasses outside the project that call no class member by name.
_PLAIN_METACLASSES = frozenset(
    {"builtins.type", "abc.ABCMeta", "enum.EnumMeta", "enum.EnumType"}
)
#: ``typing_extensions`` re-exports the ``typing`` classes of the same name.
_TYPING_MODULES = ("typing", "typing_extensions")
_NAMED_TUPLE_EXTRA = frozenset(
    {"_make", "_asdict", "_replace", "_fields", "_field_defaults"}
)
_Tops = Callable[[], frozenset[str] | None]


@dataclass(frozen=True)
class _ModuleFinding(SupertypeFinding):
    """A module-level special method (PEP 562 ``__getattr__`` / ``__dir__``)."""

    def describe(self) -> str:
        return (
            f"module `{self.file}` {self.verb} `{self.clause}` (line {self.line}), "
            f"{self.why}"
        )


def python_override_finding(
    project_root: str, rel: str, line: int, bare: str, tops: _Tops
) -> SupertypeFinding | None:
    """Why ``bare`` (declared at ``rel:line``) may be called from outside the project.

    None when ``rel:line`` holds no declaration ``bare``, when ``bare`` is a
    mangled name, or when every base above its class is a project class or an
    external one whose members are known not to include it.
    """
    if not rel.lower().endswith(PY_SUFFIX) or _mangled(bare):
        return None
    reader = _Reader(project_root, tops)
    module = reader.module(rel)
    if module is None:
        return None  # the base walk already reports an unreadable file
    owner = _owner_class(module, line, bare)
    if owner is None:
        if is_special(bare) and _module_level(module, line, bare):
            return _ModuleFinding(
                bare,
                rel,
                line,
                "",
                _SPECIAL_WHY,
                verb=_SPECIAL_VERB,
                reason=OVERRIDE_REASON,
                lead=SPECIAL_LEAD,
            )
        return None
    if is_special(bare):
        return _special(rel, owner, bare)
    return _walk(reader, _Class(module, owner), bare)


def is_special(bare: str) -> bool:
    """``__x__``: a name the interpreter looks up itself."""
    return len(bare) > 4 and bare.startswith("__") and bare.endswith("__")


def _mangled(bare: str) -> bool:
    return bare.startswith("__") and not bare.endswith("__")


def _sunder(bare: str) -> bool:
    return (
        len(bare) > 2
        and bare.startswith("_")
        and bare.endswith("_")
        and not bare.startswith("__")
        and not bare.endswith("__")
    )


def _module_level(module: _Module, line: int, bare: str) -> bool:
    """A module-level declaration of ``bare`` spans ``line``."""
    table = member_table(module.digest, module.tree)
    return any(
        name == bare and first <= line <= last and parent is None
        for name, first, last, _def_line, parent in table
    )


def _special(rel: str, owner: ast.ClassDef, bare: str) -> SupertypeFinding:
    return SupertypeFinding(
        bare,
        rel,
        owner.lineno,
        owner.name,
        _SPECIAL_WHY,
        verb=_SPECIAL_VERB,
        reason=OVERRIDE_REASON,
        lead=SPECIAL_LEAD,
    )


def _walk(reader: _Reader, start: _Class, bare: str) -> SupertypeFinding | None:
    stack = [start]
    seen: set[tuple[str, int]] = set()
    while stack:
        cls = stack.pop()
        key = (cls.module.rel, id(cls.node))
        if key in seen:
            continue
        if len(seen) >= _CLASSES_MAX:
            return _external(cls, "?", "whose bases are too many to follow")
        seen.add(key)
        found, bases = _class_bases(reader, cls, bare)
        if found is not None:
            return found
        stack.extend(reversed(bases))
    return None


def _class_bases(
    reader: _Reader, cls: _Class, bare: str
) -> tuple[SupertypeFinding | None, list[_Class]]:
    scopes = _scopes_for(cls.module, cls.node)
    bases: list[_Class] = []
    for expr in cls.node.bases:
        try:
            value = _base_value(reader, cls.module, scopes, expr)
        except RecursionError:
            value = "a base too deeply nested to follow"
        if isinstance(value, _Class):
            bases.append(value)
            continue
        target = expr.value if isinstance(expr, ast.Subscript) else expr
        clause = " ".join(ast.unparse(target).split())[:80]
        if value is not None:
            why = value if isinstance(value, str) else "a module, not a class"
            return _external(cls, clause, why), []
        origin = _origin(reader, cls.module, scopes, target)
        members = None if origin is None else known_members(origin)
        if origin is None or members is None:
            why = f"a class outside the project that may define or call `{bare}`"
            return _external(cls, clause, why), []
        if bare in members or (_sunder(bare) and origin.startswith("enum.")):
            why = f"a class outside the project that defines `{bare}`"
            return _external(cls, clause, why), []
    for keyword in cls.node.keywords:
        found = _metaclass(reader, cls, scopes, keyword, bare)
        if found is not None:
            return found, []
    return None, bases


def _metaclass(
    reader: _Reader,
    cls: _Class,
    scopes: list[ast.AST],
    keyword: ast.keyword,
    bare: str,
) -> SupertypeFinding | None:
    """An external metaclass may call any member of the class it creates."""
    if keyword.arg != "metaclass":
        return None  # ``**kw`` and project metaclasses: the base walk's business
    try:
        value = _eval(reader, cls.module, scopes, keyword.value, 0)
    except RecursionError:
        return None  # the base walk already fails closed on it
    if value is not None:
        return None
    if _origin(reader, cls.module, scopes, keyword.value) in _PLAIN_METACLASSES:
        return None
    clause = " ".join(ast.unparse(keyword.value).split())[:80]
    return SupertypeFinding(
        f"metaclass={clause}",
        cls.module.rel,
        cls.node.lineno,
        cls.node.name,
        f"a metaclass outside the project that may call `{bare}`",
        verb="has class keyword",
        reason=OVERRIDE_REASON,
        lead=EXTERNAL_LEAD,
    )


def _external(cls: _Class, clause: str, why: str) -> SupertypeFinding:
    return SupertypeFinding(
        clause,
        cls.module.rel,
        cls.node.lineno,
        cls.node.name,
        why,
        verb="has base",
        reason=OVERRIDE_REASON,
        lead=EXTERNAL_LEAD,
    )


# --- what an external base is ---------------------------------------------------------


def _origin(
    reader: _Reader, module: _Module, scopes: list[ast.AST], expr: ast.expr
) -> str | None:
    """``module.Class`` an external base expression names; None if not provable."""
    parts: list[str] = []
    node: ast.expr = expr
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.reverse()
    head = _name_origin(reader, module, scopes, node.id, bool(parts))
    if head is None:
        return None
    return ".".join([head, *parts])


def _name_origin(
    reader: _Reader,
    module: _Module,
    scopes: list[ast.AST],
    name: str,
    dotted: bool,
) -> str | None:
    """What ``name`` is bound to: ``m.X`` for ``from m import X``, ``m`` for an
    import of module ``m`` (only as the head of a dotted path), ``builtins.X``."""
    entries: list[ast.AST] = []
    for scope in scopes:
        entries = list(module.bindings(scope).get(name, ()))
        if entries:
            break
    if not entries:
        if not dotted and _lookup(reader, module, name, 0) is _MISSING:
            return f"builtins.{name}"
        return None
    if len(entries) != 1 or not isinstance(entries[0], ast.alias):
        return None
    alias = entries[0]
    stmt = module.parents.get(id(alias))
    if isinstance(stmt, ast.Import):
        if not dotted:
            return None
        return alias.name if alias.asname else alias.name.split(".", 1)[0]
    if isinstance(stmt, ast.ImportFrom) and not stmt.level and stmt.module:
        return None if dotted else f"{stmt.module}.{alias.name}"
    return None


def known_members(origin: str) -> frozenset[str] | None:
    """Every member name of an external class whose member set is closed; else None."""
    module, _, name = origin.rpartition(".")
    if module in _TYPING_MODULES:
        module = "typing"
    return _members(module, name)


@cache
def _members(module: str, name: str) -> frozenset[str] | None:
    if module == "builtins":
        value = vars(builtins).get(name)
    elif module == "abc" and name == "ABC":
        value = abc.ABC
    elif module == "typing" and name in ("Generic", "Protocol"):
        value = getattr(typing, name)
    elif module == "typing" and name == "NamedTuple":
        return _mro_names(tuple) | _NAMED_TUPLE_EXTRA
    elif module == "typing" and name == "TypedDict":
        return _mro_names(dict)
    elif module == "enum":
        value = getattr(enum, name, None)
        if not (isinstance(value, type) and issubclass(value, enum.Enum)):
            return None
    else:
        return None
    return _mro_names(value) if isinstance(value, type) else None


def _mro_names(klass: type) -> frozenset[str]:
    return frozenset(name for part in klass.__mro__ for name in vars(part))


__all__ = [
    "EXTERNAL_LEAD",
    "SPECIAL_LEAD",
    "is_special",
    "known_members",
    "python_override_finding",
]
