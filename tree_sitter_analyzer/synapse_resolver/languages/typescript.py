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

#: Instance receivers — a method call on the enclosing object. ``this``/``super``
#: must resolve WITHIN the caller's class (Codex P2 #347): they never bind a
#: top-level free function, and never bleed across class boundaries in the file.
_THIS_RECEIVERS = ("this", "super")


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
    # file -> {local_name, ...} bound by an import in THAT file. A local name
    # bound here shadows the same-named JS global (Codex P2 #347), per-file.
    import_locals_by_file: dict[str, frozenset[str]] = field(default_factory=dict)


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
        import_locals_by_file=_import_locals(imports_by_file),
    )


def _import_locals(
    imports_by_file: dict[str, Any],
) -> dict[str, frozenset[str]]:
    """Collect, per file, the set of local names bound by an import.

    These names shadow same-named JS/TS globals in that file. The bound local
    name is recorded — e.g. ``import { Map } from './x'`` binds ``Map`` and
    ``import { Map as M } from './x'`` binds ``M`` (the ``local_name``). A name
    appearing as an import local is treated as project-owned for the shadowing
    gate (Codex P2 #347).
    """
    out: dict[str, set[str]] = {}
    for file_path, entries in (imports_by_file or {}).items():
        names = out.setdefault(file_path, set())
        for entry in entries or []:
            local = getattr(entry, "local_name", "") or ""
            if local and local != "*":
                names.add(local)
    return {fp: frozenset(names) for fp, names in out.items()}


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a TS call's full name."""
    full = callee_full or callee_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or callee_name


def _lookup_free_symbol(
    ctx: TypeScriptResolverContext, file_path: str, simple: str
) -> int | None:
    """A bare ``foo()`` call: a top-level free ``function`` or ``class`` in the
    same file. Methods are deliberately excluded — a bare name does not name an
    instance method without a receiver, and including methods would let a
    no-receiver call grab an unrelated class's method (Codex P2 #347)."""
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "class"):
            return sym_id
    return None


def _lookup_this_method(
    ctx: TypeScriptResolverContext, file_path: str, simple: str
) -> int | None:
    """Resolve a ``this``/``super`` method call WITHIN the caller's class.

    The resolver is not handed the caller's enclosing-class name, so it cannot
    pick a class directly. It binds ONLY when the method name is UNAMBIGUOUS —
    exactly one class in the file defines it. When two classes both define
    ``foo`` (``class A { foo(){} } class B { bar(){ this.foo(); } foo(){} }``),
    binding either would risk the wrong edge (``B.bar -> A.foo``), so it stays
    ``unknown`` (Codex P2 #347). It never consults the file-wide free-symbol
    scan: a ``this.foo()`` is not a free function ``foo``.
    """
    found: int | None = None
    for methods in ctx.file_class_methods.get(file_path, {}).values():
        mid = methods.get(simple)
        if mid is None:
            continue
        if found is not None and found != mid:
            return None  # ambiguous across classes — conservative unknown.
        found = mid
    return found


def _name_is_shadowed(
    ctx: TypeScriptResolverContext, caller_file: str, simple: str
) -> bool:
    """True when ``simple`` is shadowed for ``caller_file`` so the ``builtin``
    global-object classification must NOT claim it.

    Two shadowing sources are consulted:

    * **Project-defined symbols** (``global_name_table``) in a COMPATIBLE-LANGUAGE
      (TS/JS-family) file. The gate is LANGUAGE-AWARE — a same-named symbol in an
      incompatible-language file (a Python ``console``) does NOT count, because
      ``languages_compatible("typescript", "python")`` is False. Files with an
      unknown language tag are treated as possible owners (conservative). This is
      THE MOAT: an incompatible-language owner never suppresses or binds.
    * **Import locals in the caller's own file** (Codex P2 #347): a name bound by
      an import in this file — ``import { Map } from './map'``,
      ``import Promise from 'bluebird'`` — rebinds the global LOCALLY, so
      ``Map.of`` / ``Promise.all`` must stay non-``builtin``. An import in a
      *different* file does not shadow this file's global.

    The variable case (``const Map = require('./map')``) is not yet detectable —
    the resolver context carries no variable symbols — and stays a conservative
    known limitation; it can only over-classify toward ``builtin``, never
    mis-bind cross-language.
    """
    if simple in ctx.import_locals_by_file.get(caller_file, frozenset()):
        return True

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

    # 1. local (instance) — ``this.foo()`` / ``super.foo()``: a method call on the
    #    enclosing object. Resolve WITHIN the caller's class only — never a
    #    top-level free function, never another class's same-named method when
    #    ambiguous (Codex P2 #347). Otherwise ``unknown``.
    if receiver in _THIS_RECEIVERS:
        mid = _lookup_this_method(ctx, caller_file, simple)
        if mid is not None:
            return mid, "local", caller_file
        return None, "unknown", ""

    # 2. local (bare) — no receiver: a same-file top-level ``function``/``class``.
    if receiver == "":
        sym_id = _lookup_free_symbol(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # A bare unresolved call stays unknown — NO global single-name binding,
        # because that is exactly where cross-language mis-wires creep in.
        return None, "unknown", ""

    # 3. builtin — receiver head is a distinctive JS/TS global object
    #    (``console``/``JSON``/``Math``…). Gated on the global name NOT being
    #    shadowed (a compatible-language project symbol OR an import local in this
    #    file). The head, not the tail, is the global ("console" in "console.log").
    head = receiver.split(".", 1)[0]
    if head in TYPESCRIPT_GLOBAL_OBJECTS and not _name_is_shadowed(
        ctx, caller_file, head
    ):
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
