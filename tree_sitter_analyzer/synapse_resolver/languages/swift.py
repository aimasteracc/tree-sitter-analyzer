"""Swift resolver registration (RFC-0010).

A SAFE, self-contained per-language callee resolver for Swift. It:

* resolves SAME-FILE / SAME-LANGUAGE local calls from ``file_symbols`` (bare
  free-function calls and ``self.method`` / ``Self.method`` calls), and
* classifies a tiny, CONSERVATIVE std tier — a curated set of near-exclusive
  Swift global functions (``print``, ``assert``, ``fatalError``, …) — as
  ``stdlib``, and
* returns ``unknown`` for everything else.

THE MOAT (the #1 correctness requirement): this resolver NEVER binds a Swift
callee to a symbol in a different language's file. This is the exact failure
mode that makes a name-only indexer wire Python ``sorted()`` to a Swift
``func sorted`` — here, every binding is gated by ``languages_compatible`` and
local resolution only ever consults the caller's OWN file. A same-name symbol in
another language (or another Swift file, absent type evidence) is left
``unknown``, never wired across.
"""

from __future__ import annotations

from typing import Any

from .._registry import register_language
from ._swift_constants import is_swift_stdlib_function

_SELF_RECEIVERS = frozenset({"self", "Self"})


class SwiftResolverContext:
    """Per-index Swift resolution maps (built once per pass).

    All file keys are project-relative paths, matching the ``edges`` table. Only
    cross-language-safe maps are retained; no global single-name table is used to
    BIND a callee (it feeds the language-aware ownership gate only).
    """

    __slots__ = ("file_languages", "file_symbols", "global_name_table")

    def __init__(
        self,
        *,
        file_symbols: dict[str, list[tuple[str, str, int]]],
        file_languages: dict[str, str],
        global_name_table: dict[str, list[tuple[str, int]]],
    ) -> None:
        self.file_symbols = file_symbols
        self.file_languages = file_languages
        self.global_name_table = global_name_table


def build_swift_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy, unused)
    **_ignored: Any,
) -> SwiftResolverContext | None:
    """Build the Swift context, or ``None`` when no Swift file is indexed.

    Zero cost for non-Swift projects (gated on ``file_languages``). Same-file
    methods are recovered from ``file_symbols`` (kind ``method``/``function``),
    so the costly class→method thunk is never materialised.
    """
    if not any(lang == "swift" for lang in file_languages.values()):
        return None
    return SwiftResolverContext(
        file_symbols=file_symbols,
        file_languages=file_languages,
        global_name_table=global_name_table,
    )


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a Swift call's full name.

    Swift qualifies with ``.`` (``self.greet``, ``obj.process``, ``Type.make``).
    The receiver is the text before the final dot; a bare call has no receiver.
    """
    full = callee_full or callee_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or callee_name


def _lookup_in_file(
    ctx: SwiftResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id of a same-file ``simple`` def, or ``None``."""
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return sym_id
    return None


def _lookup_unique_method_in_file(
    ctx: SwiftResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id of a same-file ``simple`` METHOD def, but ONLY when it
    is unique in the file.

    ``self.foo`` must bind to a member, never a free function, and never guess
    when two types in the same file both define ``foo`` (→ ``unknown``). Mirrors
    the Rust/Kotlin receiver guard.
    """
    matches = [
        sym_id
        for name, kind, sym_id in ctx.file_symbols.get(file_path, [])
        if name == simple and kind == "method"
    ]
    return matches[0] if len(matches) == 1 else None


def _project_owns(ctx: SwiftResolverContext, simple: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE (Swift) project symbol named ``simple``
    exists — the language-aware RFC-0008 ownership gate.

    A same-named symbol in an incompatible-language file (a Python ``print``)
    must NOT count as a Swift owner, so it neither suppresses the std tier nor is
    ever bound. An untagged file is treated as a possible owner (conservative).
    """
    from ..._language_family import languages_compatible

    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible("swift", owner_lang):
            return True
    return False


def resolve_swift_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: SwiftResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Swift call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is one
    of ``local`` / ``stdlib`` / ``unknown``. ``project``/``external`` are not
    emitted in this first wave — cross-file binding needs type/import resolution
    not yet available, and guessing would cross the moat; ``unknown`` is correct.
    """
    receiver, simple = _split_receiver(callee_full, callee_name)

    # 1a. local (bare call) — a receiver-less call resolves to a same-file def in
    #     the caller's OWN file only (the moat holds).
    if receiver == "":
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file

    # 1b. local (self-qualified) — ``self.foo`` / ``Self.foo``. Bind only to a
    #     UNIQUE same-file method (never a free function, never an ambiguous
    #     cross-type guess). Resolution stays in the caller's own file.
    elif receiver in _SELF_RECEIVERS:
        sym_id = _lookup_unique_method_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file

    # 2. std global fn (terminal stdlib) — a near-exclusive Swift global function
    #    called WITHOUT a receiver, and only when the project does not own a
    #    compatible-language symbol of that name (project shadowing wins).
    if (
        receiver == ""
        and is_swift_stdlib_function(simple)
        and not _project_owns(ctx, simple)
    ):
        return None, "stdlib", ""

    # 3. unknown — everything else (cross-file calls, receiver calls on unknown
    #    types, ambiguous names) is left unresolved rather than risk a mis-bind.
    return None, "unknown", ""


register_language("swift", build_swift_resolver_context, resolve_swift_callee)


__all__ = [
    "SwiftResolverContext",
    "build_swift_resolver_context",
    "resolve_swift_callee",
]
