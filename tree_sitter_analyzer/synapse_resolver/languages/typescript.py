"""TypeScript per-language callee resolver (RFC-0010, first wave).

Self-contained and SAFE. Replaces the Python cascade for ``.ts``/``.tsx`` callers
(``file_languages == "typescript"``) without regressing: it resolves SAME-FILE/
SAME-LANGUAGE local calls, classifies a small, distinctive set of built-in global
objects as ``builtin``, and returns ``unknown`` for everything else.

THE MOAT — never cross-language bind. ``_project_owns`` is language-aware: a
same-named symbol in an incompatible-language file (e.g. a Python ``console``)
never counts as an owner and is never bound, because
``languages_compatible("typescript", "python")`` is False. JS/TS dialects are one
family, so a ``.js`` owner does count (gradual-migration repos cross-import).

Conservative tiers only (the RFC-0008 lesson): the bare-method-name stdlib/
external tables are EMPTY by design — generic JS method names (``map``/``push``/
``substring``/``then``) collide with domain methods and, without receiver-type
inference, would be mis-classified. They stay ``unknown``, which is correct.

Contract (RFC-0010): the module ends with
``register_language("typescript", build_typescript_resolver_context,
resolve_typescript_callee)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._registry import register_language
from ._typescript_constants import TYPESCRIPT_GLOBAL_OBJECTS

#: ``file_languages`` tag for every ``.ts``/``.tsx``/``.mts``/``.cts`` file.
_TYPESCRIPT_LANG = "typescript"

#: Receivers that mean "the current object" — a no-receiver-style local call.
_SELF_RECEIVERS = ("", "this", "super")


@dataclass
class TypeScriptResolverContext:
    """Per-index TypeScript resolution maps (built once per pass).

    Only the shared, already-loaded cache structures are kept; the resolver does
    no extra indexing. All file keys are project-relative paths.
    """

    # file -> [(name, kind, symbol_id), ...] (shared cross-language map).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # file -> {class -> {method -> symbol_id}} (shared cross-language map).
    file_class_methods: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=dict
    )
    # simple name -> [(file, symbol_id), ...] project-wide (single-global).
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # file -> language tag (so the ownership gate is language-aware).
    file_languages: dict[str, str] = field(default_factory=dict)


def build_typescript_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy)
    **_ignored: Any,
) -> TypeScriptResolverContext | None:
    """Build the TS context, or ``None`` when no TypeScript file is indexed.

    Zero cost for non-TS projects (gated on ``file_languages``). The
    ``file_class_methods`` thunk is only invoked when a TS file is present, so a
    Python/Java-only project pays nothing.
    """
    if not any(lang == _TYPESCRIPT_LANG for lang in file_languages.values()):
        return None
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    return TypeScriptResolverContext(
        file_symbols=file_symbols,
        file_class_methods=fcm or {},
        global_name_table=global_name_table,
        file_languages=file_languages,
    )


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a TS call's full name."""
    full = callee_full or callee_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or callee_name


def _lookup_in_file(
    ctx: TypeScriptResolverContext, file_path: str, simple: str
) -> int | None:
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return sym_id
    return None


def _project_owns(ctx: TypeScriptResolverContext, simple: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE (TS/JS-family) project symbol named
    ``simple`` exists.

    The shadowing gate: if the project owns the name in a JS/TS-family file, the
    ``builtin`` global-object classification must NOT claim it. The gate is
    LANGUAGE-AWARE — a same-named symbol in an incompatible-language file (a
    Python ``console``) does NOT count, because
    ``languages_compatible("typescript", "python")`` is False. Files with an
    unknown language tag are treated as possible owners (conservative).
    """
    from ..._language_family import languages_compatible

    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible(_TYPESCRIPT_LANG, owner_lang):
            return True
    return False


def resolve_typescript_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: TypeScriptResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one TypeScript call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``builtin`` / ``unknown``. Conservative by design: every
    path that is not a confident same-file local call or a distinctive built-in
    global-object call returns ``unknown`` — never a cross-language bind.
    """
    receiver, simple = _split_receiver(callee_full, callee_name)

    # 1. local — no receiver (or ``this``/``super``): a same-file definition.
    if receiver in _SELF_RECEIVERS:
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # 1b. this/super methods captured in the class-method map.
        for _cls, methods in ctx.file_class_methods.get(caller_file, {}).items():
            mid = methods.get(simple)
            if mid is not None:
                return mid, "local", caller_file
        # A bare unresolved call stays unknown — NO global single-name binding,
        # because that is exactly where cross-language mis-wires creep in.
        return None, "unknown", ""

    # 2. builtin — receiver head is a distinctive JS/TS global object
    #    (``console``/``JSON``/``Math``…). Gated on the project NOT owning that
    #    global name as a compatible-language symbol (shadowing preserved). The
    #    head, not the tail, is the global ("console" in "console.log").
    head = receiver.split(".", 1)[0]
    if head in TYPESCRIPT_GLOBAL_OBJECTS and not _project_owns(ctx, head):
        return None, "builtin", ""

    # 3. unknown — no confident same-language resolution. Conservative tiers keep
    #    bare-method names (``substring``/``push``/``map``) out of any classified
    #    bucket; they remain ``unknown`` rather than risk a domain mis-wire.
    return None, "unknown", ""


register_language(
    _TYPESCRIPT_LANG,
    build_typescript_resolver_context,
    resolve_typescript_callee,
)


__all__ = [
    "TypeScriptResolverContext",
    "build_typescript_resolver_context",
    "resolve_typescript_callee",
]
