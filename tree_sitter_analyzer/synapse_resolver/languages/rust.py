"""Rust resolver registration (RFC-0010).

A SAFE, self-contained per-language callee resolver for Rust. It:

* resolves SAME-FILE / SAME-LANGUAGE local calls from ``file_symbols``
  (bare free-fn calls and ``self.method`` / ``Self::method`` calls), and
* classifies a tiny, CONSERVATIVE std tier — ``std::``/``core::``/``alloc::``-
  pathed calls and a curated ``StdContainer::ctor`` set (``Vec::new``,
  ``Box::new``, …) — as ``stdlib``, and
* returns ``unknown`` for everything else.

THE MOAT (the #1 correctness requirement): this resolver NEVER binds a Rust
callee to a symbol in a different language's file. Local resolution only ever
consults the caller's OWN file; the single-global step is intentionally NOT
implemented because a same-name symbol in another Rust file (let alone another
language) is not safe to bind without receiver-type evidence. The std-ownership
gate is language-aware via ``languages_compatible`` so a Python ``swap`` never
suppresses Rust's std tier and is never bound.

NOTE: Rust call-edge extraction is not yet enabled in
``function_extraction._CALL_NODE_TYPES`` (python/js/ts/java/go/c/cpp only), so a
real index produces no Rust ``calls`` edges and this resolver is dormant
end-to-end until that (separate, out-of-scope) extractor change lands. The
resolver is correct and tested at its contract surface now, so it activates with
zero further work the moment Rust edges are produced.
"""

from __future__ import annotations

from typing import Any

from .._registry import register_language
from .._rust_constants import is_std_assoc_call, is_std_path


class RustResolverContext:
    """Per-index Rust resolution maps (built once per pass).

    All file keys are project-relative paths, matching the ``edges`` table.
    Only the cross-language-safe maps are retained; no global single-name table
    is used for binding (see the module docstring — the moat).
    """

    __slots__ = ("file_languages", "file_symbols", "global_name_table")

    def __init__(
        self,
        *,
        file_symbols: dict[str, list[tuple[str, str, int]]],
        file_languages: dict[str, str],
        global_name_table: dict[str, list[tuple[str, int]]],
    ) -> None:
        # file -> [(name, kind, symbol_id), ...] (shared cross-language map).
        self.file_symbols = file_symbols
        # file -> language tag (so the std-ownership gate is language-aware).
        self.file_languages = file_languages
        # simple name -> [(file, symbol_id), ...] project-wide. Used ONLY by the
        # language-aware ownership gate (never to BIND a callee), so a same-name
        # symbol in another file is never wired across.
        self.global_name_table = global_name_table


def build_rust_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy, unused)
    **_ignored: Any,
) -> RustResolverContext | None:
    """Build the Rust context, or ``None`` when no Rust file is indexed.

    Zero cost for non-Rust projects (gated on ``file_languages``). The lazy
    ``file_class_methods`` thunk is intentionally NOT called: same-file methods
    are recovered from ``file_symbols`` (kind ``method``/``function``), so the
    costly class→method map is never materialised for Rust.
    """
    if not any(lang == "rust" for lang in file_languages.values()):
        return None
    return RustResolverContext(
        file_symbols=file_symbols,
        file_languages=file_languages,
        global_name_table=global_name_table,
    )


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a Rust call's full name.

    Rust paths use ``::`` (``Vec::new``, ``std::mem::swap``) while method calls
    use ``.`` (``self.helper``). Both separators are handled; the receiver is the
    text before the final separator, the simple name the text after it.
    """
    full = callee_full or callee_name
    # Prefer the path separator when present anywhere, else the method dot.
    if "::" in full:
        receiver, simple = full.rsplit("::", 1)
        return receiver, simple
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or callee_name


def _lookup_in_file(
    ctx: RustResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id of a same-file ``simple`` def, or ``None``."""
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return sym_id
    return None


def _lookup_unique_method_in_file(
    ctx: RustResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id of a same-file ``simple`` def, but ONLY when exactly one
    method/function of that name exists in the file; otherwise ``None``.

    Codex P2 (owner-context safety): a ``self.helper()`` / ``Self::helper()`` call
    carries no caller-owner type, so the resolver cannot tell which impl block's
    ``helper`` the receiver refers to. When two impls in the same file both define
    ``helper`` (``impl A { fn helper }`` + ``impl B { fn helper }``), binding to
    whichever row appears first would corrupt the call edge. The conservative answer
    for an ambiguous receiver-qualified method is therefore ``unknown``.

    Both ``method`` and ``function`` rows are counted: an associated fn called via
    ``Self::ctor()`` can be extracted under either kind, and either one duplicated
    across impls is ambiguous. This guard runs ONLY on the receiver-qualified
    (``self``/``Self``/``this``/``super``) path; a bare free-function call keeps
    ``_lookup_in_file`` (a Rust module cannot define two free fns of one name, so a
    bare match is never ambiguous and stays unaffected).
    """
    matches = [
        sym_id
        for name, kind, sym_id in ctx.file_symbols.get(file_path, [])
        if name == simple and kind in ("function", "method")
    ]
    return matches[0] if len(matches) == 1 else None


def _project_owns(ctx: RustResolverContext, simple: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE (Rust) project symbol of name ``simple``
    exists.

    The RFC-0008 ownership gate, language-aware: a same-named symbol in an
    incompatible-language file (e.g. a Python ``swap``) must NOT count as a Rust
    owner — ``languages_compatible('rust', 'python')`` is False, so the Rust
    caller cannot resolve that symbol and it does not suppress the std tier.

    When a file's language is unknown (no tag), it is treated as a possible owner
    (conservative — same convention as the Java resolver).
    """
    from ..._language_family import languages_compatible

    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible("rust", owner_lang):
            return True
    return False


def resolve_rust_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: RustResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Rust call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is one
    of ``local`` / ``stdlib`` / ``unknown``. ``project`` and ``external`` are not
    emitted in this first wave: cross-file binding needs trait/use resolution that
    is not yet available, and guessing would cross the moat — ``unknown`` is the
    correct, safe answer for an unresolved cross-file call.
    """
    receiver, simple = _split_receiver(callee_full, callee_name)

    # 1a. local (bare call) — a receiver-less call resolves to a same-file def in
    #     the caller's OWN file only (never another file → the moat holds). A Rust
    #     module cannot define two free fns of one name, so the first match is the
    #     unique def.
    if receiver == "":
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file

    # 1b. local (receiver-qualified) — ``self.helper`` / ``Self::helper`` /
    #     ``this`` / ``super``. The caller-owner type is NOT available to this
    #     resolver, so we can only safely bind when the method name is UNIQUE in the
    #     file. If two impls in the same file both define ``helper``, the receiver is
    #     ambiguous and we leave it ``unknown`` rather than mis-bind to the first row
    #     (Codex P2). Resolution stays in the caller's OWN file only → the moat holds.
    elif receiver in ("self", "Self", "this", "super"):
        sym_id = _lookup_unique_method_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file

    # 2. std PATH (terminal stdlib) — ``std::``/``core::``/``alloc::``-pathed call
    #    (``std::mem::swap``). Unambiguous std; safe regardless of receiver split.
    if is_std_path(callee_full or callee_name):
        return None, "stdlib", ""

    # 3. std ASSOCIATED fn (terminal stdlib) — a curated ``StdContainer::ctor``
    #    (``Vec::new``, ``Box::new``). The receiver tail (last path segment) is the
    #    type; only the curated container × constructor-family set matches. The
    #    language-aware ownership gate preserves a project type that shadows the
    #    name (a project ``new`` defined in Rust suppresses the classification).
    if receiver:
        receiver_tail = receiver.rsplit("::", 1)[-1]
        if is_std_assoc_call(receiver_tail, simple) and not _project_owns(ctx, simple):
            return None, "stdlib", ""

    # 4. unknown — everything else. A cross-file project call, an unresolved
    #    associated fn, or a same-name symbol in another file all land here rather
    #    than risk a cross-language / cross-file mis-bind.
    return None, "unknown", ""


register_language("rust", build_rust_resolver_context, resolve_rust_callee)


__all__ = [
    "RustResolverContext",
    "build_rust_resolver_context",
    "resolve_rust_callee",
]
