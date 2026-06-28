"""Kotlin callee resolver (RFC-0010, second wave).

Self-contained and SAFE — it REPLACES the Python cascade for Kotlin callers
(``file_languages == "kotlin"``; ``.kt`` / ``.kts`` files), so it must never
regress: when unsure it returns ``unknown``. Its jobs are:

1. **local (bare call)** — a receiver-less call (``helper()``) to a top-level
   function / class defined in the CALLER's OWN file. Same file == same language
   by construction, so this can never cross-bind.
2. **local (``this``/``super`` member call)** — a ``this.helper()`` /
   ``super.helper()`` call binds a same-file ``method`` row ONLY when exactly one
   method of that name exists in the file (the owner-class map disambiguates). An
   ambiguous name (two classes in the file define it) stays ``unknown`` — the
   resolver carries no caller-owner class (Codex P2 wave-1 lesson). A receiver
   call NEVER binds a top-level function.
3. **stdlib** — a bare (receiver-less) call to one of a tiny set of
   AUTO-IMPORTED Kotlin stdlib top-level functions (``listOf`` / ``println`` /
   ``require`` …), gated on the project NOT owning that name in a
   compatible-language file (shadowing preserved). See ``_kotlin_constants``.
4. **unknown** — everything else: receiver method calls on a variable
   (``items.map`` — the receiver type the edge does not carry), cross-file
   project calls, qualified third-party calls, ambiguous names.

THE MOAT (the #1 correctness requirement): a Kotlin callee is NEVER bound to a
symbol in a different language's file. The ``local`` tiers only ever consult the
caller's OWN file; the stdlib-ownership gate is language-aware via
``languages_compatible``. Critically, Kotlin and Java are NOT one
``languages_compatible`` family, so even on the JVM a Kotlin caller never binds a
Java symbol (and a Java ``listOf`` never suppresses Kotlin's stdlib tier). Real
Kotlin/Java interop would need import/type evidence this resolver does not carry;
modelling it would risk the exact cross-language mis-wire this machinery exists
to beat, so it is deliberately out of scope — ``unknown`` is the safe answer.

NOTE: Kotlin call-edge extraction is not yet enabled in
``function_extraction._CALL_NODE_TYPES`` (python/js/ts/java/go/c/cpp only), so a
real index produces no Kotlin ``calls`` edges and this resolver is dormant
end-to-end until that (separate, out-of-scope) extractor change lands. The
resolver is correct and tested at its contract surface now, so it activates with
zero further work the moment Kotlin edges are produced.

Contract (RFC-0010): the module ends with
``register_language("kotlin", build_kotlin_resolver_context,
resolve_kotlin_callee)``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.language_family import languages_compatible
from .._registry import register_language
from ._kotlin_constants import STDLIB_BARE_FUNCTIONS_KOTLIN

#: ``file_languages`` tag for every ``.kt`` / ``.kts`` file.
_KOTLIN_LANG = "kotlin"

#: Receiver tokens that denote the current object (a member call), not a separate
#: variable/type. A call qualified only by one of these is a class-scoped method
#: call resolved against the caller's own file.
_SELF_RECEIVERS: frozenset[str] = frozenset({"this", "super"})

#: Symbol kinds a bare (receiver-less) call may bind to in its own file: a
#: top-level function or a class (constructor-style call).
_LOCAL_KINDS: frozenset[str] = frozenset({"function", "method", "class"})


@dataclass
class KotlinResolverContext:
    """Per-index Kotlin resolution maps (built once per pass).

    All file keys are project-relative paths, matching the ``edges`` table. Only
    the maps the conservative cascade needs are kept; everything else is omitted
    to stay minimal and SAFE.
    """

    # file -> [(name, kind, symbol_id), ...] (shared cross-language map; only the
    # CALLER file's own entry is ever read for a local bind).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # simple name -> [(file, symbol_id), ...] project-wide. Used ONLY by the
    # language-aware ownership gate (never to BIND a callee), so a same-name
    # symbol in another file is never wired across.
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # file -> language tag (so the stdlib-ownership gate is language-aware: the
    # moat — a same-name symbol in another language must NOT suppress/bind).
    file_languages: dict[str, str] = field(default_factory=dict)
    # LAZY thunk -> {file: {class_name: {method_name: symbol_id}}}. Used only to
    # disambiguate a ``this``/``super`` member call when a file declares >1 class
    # with a colliding method name. Held as a thunk + memoised so non-member
    # workloads pay nothing.
    class_methods_thunk: Callable[[], dict[str, Any]] | None = None
    _class_methods: dict[str, Any] | None = field(default=None, repr=False)

    def member_owner_class_count(self, file_path: str, method_name: str) -> int:
        """Return how many classes in ``file_path`` define ``method_name``.

        Drives the conservative member-call gate: a ``this``/``super`` call may
        bind a same-file ``method`` only when this count is exactly 1. A count of
        0 means the owner-class map did not record it (e.g. an unpopulated map);
        callers treat 0 as "no class-ambiguity evidence" and fall back to a plain
        unique-method scan. The thunk is materialised lazily and memoised.
        """
        if self.class_methods_thunk is None:
            return 0
        if self._class_methods is None:
            self._class_methods = self.class_methods_thunk() or {}
        per_class = self._class_methods.get(file_path, {})
        return sum(1 for methods in per_class.values() if method_name in methods)


def build_kotlin_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Callable[[], dict[str, Any]],  # lazy thunk
    **_ignored: Any,
) -> KotlinResolverContext | None:
    """Build the Kotlin context, or ``None`` when no Kotlin file is indexed.

    Zero cost for non-Kotlin projects (gated on ``file_languages``). The lazy
    ``file_class_methods`` thunk is STORED but NOT called here — it is
    materialised at most once, on the first ``this``/``super`` member call that
    needs owner-class disambiguation. The bare-local and stdlib tiers never touch
    it, so a project with no such ambiguity pays nothing for the class map.
    """
    if not any(lang == _KOTLIN_LANG for lang in file_languages.values()):
        return None
    return KotlinResolverContext(
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_languages=file_languages,
        class_methods_thunk=file_class_methods,
    )


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a Kotlin call's full name.

    Kotlin uses ``.`` for both member access (``this.helper``) and qualified
    references (``factory.build``). The receiver is everything before the final
    dot; the simple name is the trailing identifier. A bare ``helper`` ->
    ``("", "helper")``.
    """
    full = callee_full or callee_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or callee_name


def _lookup_bare_in_file(
    ctx: KotlinResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id of a same-file top-level ``function``/``class`` (or a
    ``method``) named ``simple`` in ``file_path``, or ``None``.

    A bare receiver-less call may legitimately reach a top-level function, a
    class constructor, or — in a single-class file — an implicit-receiver member.
    A Kotlin file cannot declare two top-level functions of one name, so the
    first match is the unique def.
    """
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in _LOCAL_KINDS:
            return sym_id
    return None


def _lookup_unique_method_in_file(
    ctx: KotlinResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id of a same-file ``method`` named ``simple``, but ONLY
    when it is unambiguous; otherwise ``None``.

    Codex P2 (wave-1 lesson): a ``this.helper()`` / ``super.helper()`` call
    carries no caller-owner class, so when two classes in the file both define
    ``helper`` the receiver is ambiguous and must NOT bind. Disambiguation uses
    the owner-class map (count of classes defining the name); when that map is
    silent (count 0) we fall back to counting ``method`` rows so a genuinely
    unique method still binds. ONLY ``method`` rows are candidates — a
    ``this``/``super`` receiver can never mean a top-level function.
    """
    if ctx.member_owner_class_count(file_path, simple) > 1:
        return None  # owned by >1 class — ambiguous, stay unknown.
    matches = [
        sym_id
        for name, kind, sym_id in ctx.file_symbols.get(file_path, [])
        if name == simple and kind == "method"
    ]
    return matches[0] if len(matches) == 1 else None


def _project_owns(ctx: KotlinResolverContext, simple: str, caller_file: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE (Kotlin) project symbol named ``simple``
    exists.

    The RFC-0008 ownership gate, language-aware: a same-named symbol in an
    incompatible-language file (a Java / Python ``listOf``) must NOT count as a
    Kotlin owner — ``languages_compatible('kotlin', 'java')`` is False — so it
    neither suppresses the stdlib tier nor gets bound. An untagged file is
    treated as a possible owner (conservative). The caller file is included via
    the global table, so a same-file top-level def shadows the stdlib name.
    """
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible(_KOTLIN_LANG, owner_lang):
            return True
    return False


def resolve_kotlin_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: KotlinResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Kotlin call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``stdlib`` / ``unknown``. Conservative by design: every
    path that is not a confident same-file local call or a distinctive
    auto-imported stdlib builder returns ``unknown`` — never a cross-language
    bind.
    """
    receiver, simple = _split_receiver(callee_full, callee_name)

    # 1. local — bare (receiver-less) call. A top-level function / class def, or a
    #    single-class implicit-receiver member, in the CALLER's OWN file. This
    #    wins before the stdlib tier so a project ``fun println()`` shadows the
    #    stdlib classification.
    if receiver == "":
        sym_id = _lookup_bare_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # 2. stdlib — a bare auto-imported stdlib builder (``listOf`` / ``println``
        #    / ``require``) NOT owned by a compatible-language project symbol.
        #    Gated on import-free auto-imports only; a project def already won
        #    above (and ``_project_owns`` re-checks cross-file ownership).
        if simple in STDLIB_BARE_FUNCTIONS_KOTLIN and not _project_owns(
            ctx, simple, caller_file
        ):
            return None, "stdlib", ""
        # A bare unresolved call stays unknown — NO global single-name binding,
        # because that is exactly where cross-language mis-wires creep in.
        return None, "unknown", ""

    # 3. local — ``this``/``super`` member call. The caller's enclosing class is
    #    NOT available, so bind only an UNAMBIGUOUS same-file ``method`` row
    #    (never a top-level function; never when two classes define the name).
    if receiver in _SELF_RECEIVERS:
        mid = _lookup_unique_method_in_file(ctx, caller_file, simple)
        if mid is not None:
            return mid, "local", caller_file
        return None, "unknown", ""

    # 4. unknown — a receiver-qualified call on a variable / type
    #    (``items.map`` / ``factory.listOf``). The receiver type is not carried by
    #    the edge, so we never guess: bare-method-name tiers are intentionally
    #    empty (RFC-0008 precision lesson). A qualified stdlib NAME is NOT the
    #    bare auto-imported function, so it does not classify stdlib here.
    return None, "unknown", ""


register_language(_KOTLIN_LANG, build_kotlin_resolver_context, resolve_kotlin_callee)


__all__ = [
    "KotlinResolverContext",
    "build_kotlin_resolver_context",
    "resolve_kotlin_callee",
]
