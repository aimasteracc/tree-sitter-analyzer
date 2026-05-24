#!/usr/bin/env python3
"""
Feature 1 (Synapse) — Index-time cross-file callee resolution.

Public API:
    ``ResolverContext``     — project-wide indices, built once per pass.
    ``ResolvedCallee``      — output of one resolution.
    ``resolve_callee``      — one callee → ResolvedCallee, per priority cascade.
    ``parse_imports``       — import-statement text -> structured rows.
    ``build_resolver_context`` — populate a ResolverContext from the cache.
    ``is_enabled``          — honour the ``TSA_SYNAPSE`` env var.
    ``BUILTINS_PY``         — Python builtin callable names.
    ``STDLIB_NAMES_PY``     — Python stdlib top-level module names.

Priority cascade implemented by ``resolve_callee``:
  1. local      – same-file function/method match.
  2. self/cls   – ``self.X`` or ``cls.X`` on the same class.
  3. import     – name imported via ``from M import X``, or module alias
                  qualifier (``bb.baz`` after ``from . import b as bb``).
  4. stdlib     – allowlist of stdlib modules / builtins.
  5. single     – exactly one project-wide definition with that name.
  6. unknown    – nothing matched.

Star imports get an ``ast_imports`` row with ``is_star=1`` but the
resolver does NOT promote star-imported names to ``project`` in 3a.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._constants import BUILTINS_PY, STDLIB_NAMES_PY
from ._context import ResolverContext, build_resolver_context, is_enabled
from ._imports import ImportEntry, parse_imports


@dataclass(frozen=True)
class ResolvedCallee:
    """One resolution per call edge — written into ``ast_call_edges``."""

    callee_symbol_id: int | None
    resolution: str
    resolved_file: str


def _split_qualifier(name: str) -> tuple[str, str]:
    """Split ``"a.b.c"`` into ``("a.b", "c")``. Returns ``("", name)`` if no dot."""
    if "." in name:
        head, tail = name.rsplit(".", 1)
        return head, tail
    return "", name


def _lookup_symbol_id(file: str, name: str, ctx: ResolverContext) -> int | None:
    """Find a project symbol id for ``name`` in ``file``."""
    for sym_name, kind, sym_id in ctx.file_symbols.get(file, []):
        if sym_name == name and kind in ("function", "method", "class"):
            return sym_id
    return None


def _try_self_method(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    if qualifier not in ("self", "cls"):
        return None
    for _cls, methods in ctx.file_class_methods.get(caller_file, {}).items():
        sym_id = methods.get(base)
        if sym_id is not None:
            return ResolvedCallee(sym_id, "local", caller_file)
    return None


def _try_local(
    base: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    sym_id = _lookup_symbol_id(caller_file, base, ctx)
    if sym_id is not None:
        return ResolvedCallee(sym_id, "local", caller_file)
    return None


def _try_import(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """Two cases:
    * ``bb.baz()`` after ``from . import b as bb``: alias bb -> b.py.
    * ``baz()`` after ``from .b import baz``: name baz -> b.py.
    """
    if qualifier:
        target = ctx.import_alias_target.get(caller_file, {}).get(qualifier)
        if target is None and "." in qualifier:
            target = ctx.import_alias_target.get(caller_file, {}).get(
                qualifier.split(".", 1)[0]
            )
        if target:
            return ResolvedCallee(
                _lookup_symbol_id(target, base, ctx), "project", target
            )

    target = ctx.name_to_source.get(caller_file, {}).get(base)
    if target:
        return ResolvedCallee(_lookup_symbol_id(target, base, ctx), "project", target)
    return None


def _try_stdlib(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """Two strategies:
    1. ``from <stdlib_mod> import X`` makes ``X()`` stdlib.
    2. ``import <stdlib_mod>`` makes ``<stdlib_mod>.X()`` stdlib.
    """
    stdlib_modules = ctx.stdlib_modules.get("python", frozenset())
    if not stdlib_modules:
        return None
    for imp in ctx.imports_by_file.get(caller_file, []):
        if imp.is_star:
            continue
        top = imp.module_path.lstrip(".").split(".")[0]
        if not top or top not in stdlib_modules:
            continue
        if imp.local_name == base and not qualifier:
            return ResolvedCallee(None, "stdlib", "")
        if qualifier:
            head = qualifier.split(".", 1)[0]
            if imp.local_name == head:
                return ResolvedCallee(None, "stdlib", "")
    return None


def _try_builtin(
    base: str, qualifier: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    if qualifier:
        return None
    if base in ctx.builtins.get("python", frozenset()):
        return ResolvedCallee(None, "stdlib", "")
    return None


def _try_single_global(
    base: str, qualifier: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    if qualifier:
        return None
    cands = ctx.global_name_table.get(base, [])
    if len(cands) == 1:
        target_file, sym_id = cands[0]
        return ResolvedCallee(sym_id, "project", target_file)
    return None


def resolve_callee(
    callee_name: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee:
    """Resolve a single callee per the priority cascade above."""
    qualifier, base = _split_qualifier(callee_name)

    for rule in (
        lambda: _try_self_method(base, qualifier, caller_file, ctx),
        lambda: _try_local(base, caller_file, ctx) if not qualifier else None,
        lambda: _try_import(base, qualifier, caller_file, ctx),
        lambda: _try_stdlib(base, qualifier, caller_file, ctx),
        lambda: _try_builtin(base, qualifier, ctx),
        lambda: _try_single_global(base, qualifier, ctx),
    ):
        out = rule()
        if out is not None:
            return out

    return ResolvedCallee(None, "unknown", "")


__all__ = [
    "BUILTINS_PY",
    "STDLIB_NAMES_PY",
    "ImportEntry",
    "ResolvedCallee",
    "ResolverContext",
    "build_resolver_context",
    "is_enabled",
    "parse_imports",
    "resolve_callee",
]
