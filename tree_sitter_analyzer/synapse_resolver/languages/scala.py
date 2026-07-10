"""Scala callee resolver (RFC-0010).

Replaces the Python cascade for Scala callers. Resolution cascade:
  (a) local symbol in the same file
  (b) explicit named import (import a.b.C → resolves C or a.b.C)
  (c) single project-wide symbol with that bare name
  (d) unknown

Never applies Python stdlib allowlist, builtin names, or self/cls semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._registry import register_language


@dataclass
class ScalaResolverContext:
    """Per-index Scala resolution maps (built once per pass)."""

    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    name_to_source: dict[str, dict[str, str]] = field(default_factory=dict)


def build_scala_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    **_ignored: Any,
) -> ScalaResolverContext | None:
    """Build the Scala context, or None when no Scala file is indexed."""
    if not any(lang == "scala" for lang in file_languages.values()):
        return None

    name_to_source: dict[str, dict[str, str]] = {}
    for caller_file, entries in imports_by_file.items():
        if file_languages.get(caller_file) != "scala":
            continue
        name_map: dict[str, str] = {}
        for entry in entries:
            if entry.is_star or not entry.local_name:
                continue
            name_map[entry.local_name] = entry.module_path
            if entry.module_path:
                name_map[entry.module_path] = entry.module_path
        if name_map:
            name_to_source[caller_file] = name_map

    return ScalaResolverContext(
        file_symbols=file_symbols,
        global_name_table={
            name: list(entries)
            for name, entries in global_name_table.items()
        },
        name_to_source=name_to_source,
    )


def _lookup_in_file(
    ctx: ScalaResolverContext, file_path: str, name: str
) -> int | None:
    """Return symbol_id if name is defined in file_path, else None."""
    for sym_name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if sym_name == name and kind in ("function", "method", "class"):
            return sym_id
    return None


def resolve_scala_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: ScalaResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Scala call edge. Returns (symbol_id, resolution, resolved_file)."""
    name = callee_full or callee_name

    # (a) local
    sym_id = _lookup_in_file(ctx, caller_file, callee_name)
    if sym_id is not None:
        return sym_id, "local", caller_file

    # (b) explicit named import — P0: returns unknown (file resolution is follow-on)
    if caller_file in ctx.name_to_source:
        if callee_name in ctx.name_to_source[caller_file]:
            return None, "unknown", ""

    # (c) single project-wide symbol
    entries = ctx.global_name_table.get(callee_name, [])
    if len(entries) == 1:
        target_file, sym_id = entries[0]
        if target_file in ctx.file_symbols:
            return sym_id, "project", target_file

    # (d) unknown
    _ = name
    return None, "unknown", ""


register_language("scala", build_scala_resolver_context, resolve_scala_callee)


__all__ = [
    "ScalaResolverContext",
    "build_scala_resolver_context",
    "resolve_scala_callee",
]
