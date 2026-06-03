"""Java import parsing (L1) and call-target resolution (L2).

This module is the Java half of the language-agnostic resolver. It
mirrors the Python logic in ``__init__`` / ``_context`` but uses Java
import / package / FQN semantics instead of Python dotted-module
semantics.

Two halves:

* :func:`parse_java_imports` — turns one ``import`` / ``package``
  statement (raw text) into structured :class:`ImportEntry` rows that
  land in ``ast_imports`` (reusing the existing schema; no new columns).
* :class:`JavaResolverContext` + :func:`resolve_java_callee` — the
  10-stage resolution cascade. Crucially, JDK / platform calls are
  tagged ``external`` (a *terminal* resolution) rather than ``unknown``,
  which keeps them out of the backfill re-scan set.

The cascade returns a plain ``(symbol_id, resolution, resolved_file)``
tuple; the package ``__init__`` wraps it into a ``ResolvedCallee`` so
this module stays free of import cycles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ._imports import ImportEntry
from ._java_constants import JAVA_LANG_TYPES, is_jdk_prefix

# A ``package a.b.c;`` declaration. ``module_path`` here is reused to
# carry the package name; ``local_name`` marks the row as a package row.
_PKG_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;?\s*$")
# ``import [static] a.b.C[.member][.*] ;``
_IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([\w.]+)(\.\*)?\s*;?\s*$")

# Sentinel module-path used to record the file's own package declaration
# without adding a new ``ast_imports`` column. A package row is
# ``local_name == _PACKAGE_MARKER`` and ``module_path == <package name>``.
_PACKAGE_MARKER = "\x00package"


def parse_java_imports(
    text: str, file_path: str = "", line: int = 0
) -> list[ImportEntry]:
    """Parse one Java ``import`` / ``package`` statement into rows.

    * ``package a.b.c;``      -> 1 package-marker row (module_path='a.b.c').
    * ``import a.b.C;``        -> 1 row (local_name='C', module_path='a.b.C').
    * ``import a.b.*;``        -> 1 star row (module_path='a.b', is_star=1).
    * ``import static a.b.C.m;`` -> 1 row (local_name='m', module_path='a.b.C').
    * ``import static a.b.C.*;`` -> 1 star row (module_path='a.b.C', is_star=1).

    ``is_static`` has no dedicated column in v1; static imports are stored
    as ordinary rows. Resolution treats an unqualified call whose simple
    name matches an import binding as a static-member call, so a separate
    flag is not required for the v1 cascade.
    """
    text = text.strip()
    if not text:
        return []

    m_pkg = _PKG_RE.match(text)
    if m_pkg:
        return [
            ImportEntry(
                file_path=file_path,
                language="java",
                module_path=m_pkg.group(1),
                local_name=_PACKAGE_MARKER,
                is_relative=False,
                is_star=False,
                alias_of="",
                line=line,
            )
        ]

    m_imp = _IMPORT_RE.match(text)
    if not m_imp:
        return []

    is_wildcard = bool(m_imp.group(3))
    fqn = m_imp.group(2)

    if is_wildcard:
        # ``import a.b.*`` (or ``import static a.b.C.*``): the prefix is a
        # package (or class for static) under which simple names resolve.
        return [
            ImportEntry(
                file_path=file_path,
                language="java",
                module_path=fqn,
                local_name="",
                is_relative=False,
                is_star=True,
                alias_of="",
                line=line,
            )
        ]

    # Single-type / single-static-member import. The bound simple name is
    # the last dotted segment; ``module_path`` keeps the full FQN.
    simple = fqn.rsplit(".", 1)[-1] if "." in fqn else fqn
    return [
        ImportEntry(
            file_path=file_path,
            language="java",
            module_path=fqn,
            local_name=simple,
            is_relative=False,
            is_star=False,
            alias_of="",
            line=line,
        )
    ]


@dataclass
class JavaResolverContext:
    """Per-index Java resolution maps (built once per pass).

    All file keys are project-relative paths, matching ``ast_call_edges``.
    """

    # package name -> files declaring that package (same-package + wildcard).
    package_to_files: dict[str, list[str]] = field(default_factory=dict)
    # ``a.b.C`` -> file defining that top-level type.
    fqn_to_file: dict[str, str] = field(default_factory=dict)
    # file -> {simple name -> FQN} from type-import + static-import binds.
    simple_to_fqn_by_file: dict[str, dict[str, str]] = field(default_factory=dict)
    # file -> {static-member simple name -> owning class FQN}.
    static_imports_by_file: dict[str, dict[str, str]] = field(default_factory=dict)
    # file -> [package FQN, ...] from ``import a.b.*`` wildcard rows.
    wildcard_pkgs_by_file: dict[str, list[str]] = field(default_factory=dict)
    # file -> its declared package name.
    file_package: dict[str, str] = field(default_factory=dict)
    # file -> {class -> {method -> symbol_id}} (shared cross-language map).
    file_class_methods: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=dict
    )
    # file -> [(name, kind, symbol_id), ...] (shared cross-language map).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # simple name -> [(file, symbol_id), ...] project-wide (single-global).
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


def build_java_context(
    imports_by_file: dict[str, list[ImportEntry]],
    file_symbols: dict[str, list[tuple[str, str, int]]],
    file_class_methods: dict[str, dict[str, dict[str, int]]],
    global_name_table: dict[str, list[tuple[str, int]]],
) -> JavaResolverContext:
    """Assemble the Java resolution maps from already-loaded cache data.

    ``imports_by_file`` must contain only the Java-language rows. Package
    declarations are carried as marker rows (see :func:`parse_java_imports`).
    """
    ctx = JavaResolverContext(
        file_class_methods=file_class_methods,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
    )

    for caller_file, entries in imports_by_file.items():
        simple_map: dict[str, str] = {}
        static_map: dict[str, str] = {}
        wildcards: list[str] = []
        for entry in entries:
            if entry.local_name == _PACKAGE_MARKER:
                ctx.file_package[caller_file] = entry.module_path
                continue
            if entry.is_star:
                wildcards.append(entry.module_path)
                continue
            if entry.local_name:
                # A single-type import binds simple -> FQN. A single
                # static-member import binds member -> owning class FQN.
                # We register both maps; resolution consults the right one
                # based on whether the call carries a receiver.
                simple_map.setdefault(entry.local_name, entry.module_path)
                owner = entry.module_path.rsplit(".", 1)[0]
                static_map.setdefault(entry.local_name, owner)
        if simple_map:
            ctx.simple_to_fqn_by_file[caller_file] = simple_map
        if static_map:
            ctx.static_imports_by_file[caller_file] = static_map
        if wildcards:
            ctx.wildcard_pkgs_by_file[caller_file] = wildcards

    # Build package_to_files + fqn_to_file from declared packages and the
    # top-level class symbols in each file.
    for file_path, pkg in ctx.file_package.items():
        ctx.package_to_files.setdefault(pkg, []).append(file_path)
    for file_path, symbols in file_symbols.items():
        pkg = ctx.file_package.get(file_path, "")
        for name, kind, _sym_id in symbols:
            if kind != "class":
                continue
            fqn = f"{pkg}.{name}" if pkg else name
            ctx.fqn_to_file.setdefault(fqn, file_path)
    return ctx


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a Java call's full name."""
    full = callee_full or callee_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or callee_name


def _lookup_in_file(
    ctx: JavaResolverContext, file_path: str, simple: str
) -> int | None:
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return sym_id
    return None


def resolve_java_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: JavaResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Java call edge per the 10-stage cascade.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution``
    is one of ``local`` / ``project`` / ``external`` / ``unknown``.
    """
    receiver, simple = _split_receiver(callee_full, callee_name)

    # 1. local — no receiver (implicit ``this``) or ``this``/``super``.
    if receiver in ("", "this", "super"):
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # 1b. this/super methods captured in the class-method map.
        for _cls, methods in ctx.file_class_methods.get(caller_file, {}).items():
            mid = methods.get(simple)
            if mid is not None:
                return mid, "local", caller_file

    # 3. static-import — unqualified call whose name is a static member.
    if not receiver:
        owner_fqn = ctx.static_imports_by_file.get(caller_file, {}).get(simple)
        if owner_fqn:
            target = ctx.fqn_to_file.get(owner_fqn)
            if target:
                return _lookup_in_file(ctx, target, simple), "project", target
            if is_jdk_prefix(owner_fqn):
                return None, "external", ""

    if receiver and receiver not in ("this", "super"):
        # Two candidate type names from the receiver:
        # * ``head`` = first segment — the type for a ``Type.field.m()`` or
        #   ``Type.m()`` static call (``System`` in ``System.out.println``).
        # * ``tail`` = last segment — the type for a fully-qualified class
        #   reference (``C`` in ``a.b.C.m()``).
        head = receiver.split(".", 1)[0]
        tail = receiver.rsplit(".", 1)[-1] if "." in receiver else receiver

        # 4. type-import — receiver head is an imported simple class name.
        for type_name in (head, tail):
            fqn = ctx.simple_to_fqn_by_file.get(caller_file, {}).get(type_name)
            if not fqn:
                continue
            target = ctx.fqn_to_file.get(fqn)
            if target:
                return _lookup_in_file(ctx, target, simple), "project", target
            if is_jdk_prefix(fqn):
                return None, "external", ""

        # 5. same-package — receiver type defined in the caller's package.
        caller_pkg = ctx.file_package.get(caller_file, "")
        if caller_pkg:
            for type_name in (head, tail):
                same_pkg_fqn = f"{caller_pkg}.{type_name}"
                target = ctx.fqn_to_file.get(same_pkg_fqn)
                if target:
                    return _lookup_in_file(ctx, target, simple), "project", target

        # 6. fqn-direct — receiver itself is a known project FQN.
        target = ctx.fqn_to_file.get(receiver)
        if target:
            return _lookup_in_file(ctx, target, simple), "project", target

        # 7. wildcard — receiver type under an ``import a.b.*`` package.
        type_name = head
        for pkg in ctx.wildcard_pkgs_by_file.get(caller_file, []):
            cand_fqn = f"{pkg}.{type_name}"
            target = ctx.fqn_to_file.get(cand_fqn)
            if target:
                return _lookup_in_file(ctx, target, simple), "project", target
            if is_jdk_prefix(pkg + "."):
                return None, "external", ""

        # 8. jdk / external (terminal) — receiver is a JDK FQN or its head
        # is a known ``java.lang`` simple type (``System`` in
        # ``System.out.println``). external == "outside project, never
        # re-scan", which is what breaks the unknown -> rescan loop.
        if is_jdk_prefix(receiver + ".") or is_jdk_prefix(receiver):
            return None, "external", ""
        if head in JAVA_LANG_TYPES:
            return None, "external", ""

    # 9. single-global — exactly one project-wide definition of the name.
    if not receiver:
        cands = ctx.global_name_table.get(simple, [])
        if len(cands) == 1:
            target_file, sym_id = cands[0]
            return sym_id, "project", target_file

    # 10. unknown.
    return None, "unknown", ""


__all__ = [
    "JavaResolverContext",
    "build_java_context",
    "parse_java_imports",
    "resolve_java_callee",
]
