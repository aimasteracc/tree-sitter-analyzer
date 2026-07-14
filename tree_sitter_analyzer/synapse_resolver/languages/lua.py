"""Lua callee resolver (RFC-0010).

Minimal claim-the-slot resolver for Lua. Its ONLY job is to occupy the
``lua`` language slot in the registry so the Python cascade cannot
mis-classify Lua global names, built-in functions (``print``, ``type``,
``pairs``, ``ipairs``, ``table``, ``string``, ``math``, etc.) or
method-call syntax as Python builtins or stdlib symbols.

Resolution always returns ``(None, "unknown", "")`` — Lua's dynamic
dispatch (metatables, first-class functions, ``require()`` at runtime,
varargs) cannot be statically resolved without full interpreter semantics.

THE MOAT: by registering ``lua``, the language-dispatch in the outer
resolve loop calls ``resolve_lua_callee`` instead of falling through to
the Python cascade for ``.lua`` caller files. This prevents a Lua
``print`` or ``type`` call from being classified as a Python builtin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._registry import register_language


@dataclass
class LuaResolverContext:
    """Per-index Lua resolution context.

    Currently empty: Lua resolution is always ``unknown``. The class
    exists so that ``build_lua_resolver_context`` can return a typed
    non-``None`` sentinel and the registry contract (``Any | None``) is
    satisfied.
    """


def build_lua_resolver_context(
    *,
    file_languages: dict[str, str],
    **_ignored: Any,
) -> LuaResolverContext | None:
    """Build the Lua context, or ``None`` when no Lua file is indexed.

    Zero cost for non-Lua projects. When at least one ``.lua`` file is
    present the returned context acts as a sentinel: the registry
    dispatches to ``resolve_lua_callee`` instead of the Python cascade.
    """
    if not any(lang == "lua" for lang in file_languages.values()):
        return None
    return LuaResolverContext()


def resolve_lua_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: LuaResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve a Lua call edge — always returns ``unknown``.

    Lua's dynamic semantics (metatables, ``__index`` chains, ``require``
    at runtime) make static callee resolution unreliable. This resolver
    claims the language slot to prevent cross-language mis-binding and
    conservatively returns ``unknown`` for every call.

    Returns ``(symbol_id, resolution, resolved_file)``.
    """
    return (None, "unknown", "")


register_language("lua", build_lua_resolver_context, resolve_lua_callee)
