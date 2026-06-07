"""Ruby callee resolver (RFC-0010 second wave).

A self-contained, SAFE per-language resolver for ``.rb`` files. It REPLACES the
generic Python cascade for Ruby callers, so it must not regress: when unsure, it
returns ``unknown`` (never a wrong binding).

What it resolves:

* **local** — a same-file call whose simple name is defined in the caller file.
  Two distinct same-scope forms, each by a SEPARATE path:
    * a bare ``foo`` / ``foo()`` call (no receiver) → a top-level ``function``
      (module/private method) defined in the caller file, via the flat
      ``file_symbols`` scan.
    * ``self.foo`` — a method call on the caller's own object. Bound ONLY through
      the unambiguous single-class gate (``file_class_methods`` with exactly one
      class), so ``self.render`` never binds to a sibling class's ``render``.
* **project** — a bare name with exactly ONE project-wide definition that lives
  in a Ruby file, AND that definition is a bare-callable kind (a top-level
  ``function``). The single-global rule, gated by language so a same-named
  Python/Java symbol is never bound.
* **builtin** — a namespaced Ruby core call (``Math.sqrt`` …) matched on the
  FULL dotted call name. Terminal — outside the project, never re-scanned.
  Suppressed when the project itself owns the receiver name in a Ruby file.
* **unknown** — everything else (the conservative default).

THE MOAT — this resolver NEVER binds a callee to a symbol in a non-Ruby file.
Cross-language same-name collisions resolve to ``unknown`` (or the Ruby
same-file definition), never to the foreign file. That is the exact CodeGraph
failure this project exists to beat.

Ruby vs JavaScript note: in Ruby ``self`` IS the current object (so ``self.foo``
is the canonical same-object method call, handled like Java's ``this``). Ruby
has no ``this`` keyword. ``require`` / ``require_relative`` load *files*, not
named symbols, so there is no symbol-level import tier — method resolution is
purely local / single-global / namespaced-core, which is why this resolver is
shaped on the JavaScript resolver rather than the import-driven Java one.
"""

from __future__ import annotations

from typing import Any

from ..._language_family import languages_compatible
from .._registry import register_language
from ._ruby_constants import RUBY_BUILTIN_CALLS

#: The language tag the detector assigns to ``.rb`` files. Ruby is NOT part of
#: any interop family (see ``_language_family._LANGUAGE_FAMILIES``), so the
#: ownership / project gates only ever bind to another ``"ruby"`` file — the
#: moat is enforced by ``languages_compatible("ruby", owner_lang)`` returning
#: True only for ``"ruby"`` (or empty/unknown).
_RUBY_LANG = "ruby"

#: Symbol kinds that a BARE call (no receiver) can legally target. A top-level
#: ``function`` (a Ruby module method / top-level ``def`` / private method) is
#: callable bare; a class ``method`` is NOT a valid bare-call target across
#: files (it needs an owning receiver), and a ``class``/``module`` used bare is
#: a constant reference, not a plain call. ``global_name_table`` drops the kind,
#: so the project tier cross-checks ``file_symbols`` and only binds a
#: bare-callable kind — otherwise ``render`` wires to a same-named method
#: elsewhere (the JS resolver's Codex P2 #346 lesson, applied to Ruby).
_BARE_CALLABLE_KINDS: frozenset[str] = frozenset({"function"})


class RubyResolverContext:
    """Per-index Ruby resolution maps (built once per pass).

    Holds only the shared cross-language maps the resolver consults. All file
    keys are project-relative paths, matching the ``edges`` table.
    """

    __slots__ = (
        "file_symbols",
        "file_class_methods",
        "global_name_table",
        "file_languages",
    )

    def __init__(
        self,
        *,
        file_symbols: dict[str, list[tuple[str, str, int]]],
        file_class_methods: dict[str, dict[str, dict[str, int]]],
        global_name_table: dict[str, list[tuple[str, int]]],
        file_languages: dict[str, str],
    ) -> None:
        self.file_symbols = file_symbols
        self.file_class_methods = file_class_methods
        self.global_name_table = global_name_table
        self.file_languages = file_languages


def build_ruby_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # lazy thunk -> class->method map
    **_ignored: Any,
) -> RubyResolverContext | None:
    """Build the Ruby context, or ``None`` when no ``.rb`` file is indexed.

    Zero cost for non-Ruby projects: gated on ``file_languages`` BEFORE the lazy
    ``file_class_methods`` thunk is forced, so a Python/Java-only index never
    pays to materialise the class-method map for Ruby.
    """
    if not any(lang == _RUBY_LANG for lang in file_languages.values()):
        return None
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    return RubyResolverContext(
        file_symbols=file_symbols,
        file_class_methods=fcm or {},
        global_name_table=global_name_table,
        file_languages=file_languages,
    )


def _split_receiver(full_name: str, bare_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a Ruby call's full name."""
    full = full_name or bare_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or bare_name


def _lookup_in_file(
    ctx: RubyResolverContext, file_path: str, simple: str
) -> int | None:
    """Symbol id of a same-file BARE-CALLABLE named ``simple`` in ``file_path``.

    Restricted to a top-level ``function`` (see ``_BARE_CALLABLE_KINDS``): a bare
    ``foo`` is the only same-scope form routed here, and a bare call cannot
    target a class ``method`` (it needs an owning receiver). Real resolver
    contexts populate ``file_symbols`` with EVERY method in the file, so matching
    ``method`` here would bind a bare ``render`` to a sibling class's method — a
    concrete wrong edge. ``self.<method>`` is bound separately through the
    unambiguous single-class gate, not here.
    """
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in _BARE_CALLABLE_KINDS:
            return sym_id
    return None


def _owner_kind(ctx: RubyResolverContext, owner_file: str, sym_id: int) -> str:
    """Kind (``function``/``method``/``class``) of ``sym_id`` in ``owner_file``.

    Recovered from ``file_symbols`` because the shared ``global_name_table``
    carries only ``(file, id)`` and drops the kind. Returns ``""`` when the owner
    row is not present (so the caller treats it conservatively).
    """
    for _name, kind, sid in ctx.file_symbols.get(owner_file, []):
        if sid == sym_id:
            return kind
    return ""


def _ruby_project_owns(ctx: RubyResolverContext, simple: str) -> bool:
    """True when a RUBY project symbol is named ``simple``.

    Language-aware ownership gate: a same-named symbol in an incompatible
    language (a Python ``sqrt``, a Java ``log``) does NOT count, so it can never
    suppress a builtin classification. Ruby is in no interop family, so only a
    ``"ruby"`` owner (or an empty/unknown tag) qualifies — the moat.
    """
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if languages_compatible(_RUBY_LANG, owner_lang):
            return True
    return False


def resolve_ruby_callee(
    bare_name: str,
    full_name: str,
    caller_file: str,
    lang_ctx: RubyResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Ruby call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``project`` / ``builtin`` / ``unknown``. Conservative by
    construction: anything not provably one of the first three is ``unknown``.
    """
    ctx = lang_ctx
    receiver, simple = _split_receiver(full_name, bare_name)

    # 1. local — a call into the caller's own file. The two same-scope forms are
    #    resolved by SEPARATE paths because they have different binding rules:
    #
    #    * bare ``foo`` (no receiver) — never a cross-receiver method call, so
    #      the flat ``file_symbols`` scan is safe: it can only legitimately hit a
    #      same-file top-level ``function`` (a module/private method).
    #    * ``self.foo`` — a METHOD call on the caller's own object. In Ruby
    #      ``self`` IS the current object, but a flat ``file_symbols`` scan must
    #      NOT be used: real contexts populate ``file_symbols`` with EVERY method
    #      in the file (sibling classes included), so a flat lookup of
    #      ``self.render`` from ``A#run`` would find a SIBLING ``B#render`` and
    #      bind a concrete wrong edge. It may bind ONLY through
    #      ``file_class_methods`` AND only when the file defines exactly ONE class
    #      (so ``self`` is unambiguous). With 2+ classes we lack the caller's
    #      enclosing class → stay ``unknown``.
    if receiver == "":
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
    elif receiver == "self":
        classes = ctx.file_class_methods.get(caller_file, {})
        if len(classes) == 1:
            ((_cls, methods),) = classes.items()
            mid = methods.get(simple)
            if mid is not None:
                return mid, "local", caller_file

    # 2. builtin — a namespaced Ruby core call matched on the FULL dotted name
    #    (``Math.sqrt`` …). Terminal: outside the project. Suppressed if the
    #    project itself owns the receiver name in a Ruby file (a domain constant
    #    literally named ``Math`` shadowing the core module).
    if receiver:
        full = full_name or f"{receiver}.{simple}"
        head = receiver.split(".", 1)[0]
        if full in RUBY_BUILTIN_CALLS and not _ruby_project_owns(ctx, head):
            return None, "builtin", ""

    # 3. project — exactly one Ruby project-wide definition of a BARE name, AND
    #    that definition must be a bare-callable kind (a top-level ``function``).
    #    A class ``method`` is not callable without a receiver and a bare
    #    ``class``/``module`` name is a constant reference, not a plain call.
    #    Gated by language so a same-name Python/Java symbol is never bound (the
    #    MOAT).
    if not receiver:
        ruby_cands = [
            (owner_file, sym_id)
            for owner_file, sym_id in ctx.global_name_table.get(simple, [])
            if languages_compatible(_RUBY_LANG, ctx.file_languages.get(owner_file, ""))
            and _owner_kind(ctx, owner_file, sym_id) in _BARE_CALLABLE_KINDS
        ]
        if len(ruby_cands) == 1:
            target_file, sym_id = ruby_cands[0]
            return sym_id, "project", target_file

    # 4. unknown — the conservative default. Never a cross-language binding.
    return None, "unknown", ""


register_language(_RUBY_LANG, build_ruby_context, resolve_ruby_callee)
