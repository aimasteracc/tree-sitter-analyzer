"""JavaScript callee resolver (RFC-0010 first wave).

A self-contained, SAFE per-language resolver for ``.js`` / ``.jsx`` files. It
REPLACES the generic Python cascade for JavaScript callers, so it must not
regress: when unsure, it returns ``unknown`` (never a wrong binding).

What it resolves:

* **local** — a same-file call (no receiver, or ``this.``) whose simple name is
  defined in the caller file (function / method / class). Pulled from the
  shared ``file_symbols`` / ``file_class_methods`` maps.
* **project** — a bare name with exactly ONE project-wide definition that lives
  in a JS-family file (``.js``/``.ts``/``.jsx``/``.tsx``). The single-global
  rule, gated by language so a same-named Python/Java symbol is never bound.
* **builtin** — a namespaced JS global call (``JSON.parse``, ``Object.keys``,
  ``Math.max`` …) matched on the FULL dotted call name. Terminal — outside the
  project, never re-scanned.
* **unknown** — everything else (the conservative default).

THE MOAT — this resolver NEVER binds a callee to a symbol in a non-JS-family
file. Cross-language same-name collisions resolve to ``unknown`` (or the JS
same-file definition), never to the foreign file. That is the exact CodeGraph
failure this project exists to beat.
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.languages.language_family import languages_compatible

from .._javascript_constants import JS_BUILTIN_CALLS
from .._registry import register_language

#: Same-scope receivers handled by the ``local`` tier, each by a DISTINCT path
#: (see ``resolve_javascript_callee`` step 1):
#:   * ``""``   — a bare ``foo()`` call: a top-level callable in the caller file.
#:   * ``this`` — a method call on the caller's own object, bound only through
#:     the unambiguous single-class gate.
#: ``self`` is DELIBERATELY ABSENT — in browser/worker JavaScript ``self`` is the
#: global scope (``Window.self`` / ``WorkerGlobalScope.self``), not the current
#: object. Treating ``self.foo()`` as a same-file call would bind it to any local
#: helper named ``foo`` — a concrete wrong edge (Codex P2 #346).

#: JS-family dialects this resolver claims. ``.jsx`` files are tagged ``"jsx"``
#: by the language detector and ``resolve_callee`` dispatches by that exact
#: string, so the resolver registers under every JS-family dialect it serves —
#: otherwise JSX callers bypass this SAFE resolver and leak into the Python
#: cascade (e.g. a bare ``len()`` mis-classified as a Python builtin). TS/TSX
#: have their own resolvers; this module owns ``javascript`` and ``jsx`` only
#: (Codex P2 #346).
_JS_DIALECTS: tuple[str, ...] = ("javascript", "jsx")


class JavaScriptResolverContext:
    """Per-index JavaScript resolution maps (built once per pass).

    Holds only the shared cross-language maps the resolver consults. All file
    keys are project-relative paths, matching the ``edges`` table.
    """

    __slots__ = (
        "file_symbols",
        "file_class_methods",
        "global_name_table",
        "file_languages",
        "shadowed_globals",
    )

    def __init__(
        self,
        *,
        file_symbols: dict[str, list[tuple[str, str, int]]],
        file_class_methods: dict[str, dict[str, dict[str, int]]],
        global_name_table: dict[str, list[tuple[str, int]]],
        file_languages: dict[str, str],
        shadowed_globals: frozenset[str],
    ) -> None:
        self.file_symbols = file_symbols
        self.file_class_methods = file_class_methods
        self.global_name_table = global_name_table
        self.file_languages = file_languages
        #: Bare names defined as JS-family ``variable``-kind symbols (``const``/
        #: ``let``/``var``). The shared ``global_name_table`` is built from
        #: function/method/class rows only, so an object-literal shadow such as
        #: ``const Math = {...}`` is otherwise invisible to the ownership gate
        #: (Codex P2 #346).
        self.shadowed_globals = shadowed_globals


def _js_shadowed_globals_from_conn(
    conn: Any, file_languages: dict[str, str]
) -> frozenset[str]:
    """JS-family ``variable``-kind symbol names, for the builtin-shadow gate.

    The shared resolver maps (``global_name_table`` / ``file_symbols``) are built
    from ``kind IN ('function','method','class')`` only, so an object-literal
    shadow such as ``const Math = {...}`` never reaches the ownership gate. This
    single extra query (run once per index pass, JS-projects only) recovers the
    ``variable`` rows so ``Math.max`` on a shadowed ``Math`` stays out of the
    terminal ``builtin`` tier (Codex P2 #346). Best-effort: any DB error yields
    an empty set, degrading to the prior behaviour rather than raising.
    """
    if conn is None:
        return frozenset()
    try:
        rows = conn.execute(
            "SELECT DISTINCT name, language FROM ast_symbol_rows "
            "WHERE kind = 'variable'"
        ).fetchall()
    except Exception:  # nosec B110 — table/fts5 tolerance; degrade to empty.
        return frozenset()
    names: set[str] = set()
    for row in rows:
        if languages_compatible("javascript", row["language"] or ""):
            names.add(row["name"])
    return frozenset(names)


def build_javascript_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # lazy thunk -> class->method map
    conn: Any = None,
    js_shadowed_globals: Any = None,  # test-injection override
    **_ignored: Any,
) -> JavaScriptResolverContext | None:
    """Build the JS context, or ``None`` when no ``.js``/``.jsx`` file is indexed.

    Zero cost for non-JavaScript projects: gated on ``file_languages`` BEFORE the
    lazy ``file_class_methods`` thunk is forced, so a Python/Java-only index
    never pays to materialise the class-method map for JavaScript. The gate
    matches every JS-family dialect this resolver serves (``javascript`` /
    ``jsx``), so a ``.jsx``-only project still builds a context (Codex P2 #346).
    """
    if not any(lang in _JS_DIALECTS for lang in file_languages.values()):
        return None
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    if js_shadowed_globals is not None:
        shadowed = frozenset(js_shadowed_globals)
    else:
        shadowed = _js_shadowed_globals_from_conn(conn, file_languages)
    return JavaScriptResolverContext(
        file_symbols=file_symbols,
        file_class_methods=fcm or {},
        global_name_table=global_name_table,
        file_languages=file_languages,
        shadowed_globals=shadowed,
    )


def _split_receiver(full_name: str, bare_name: str) -> tuple[str, str]:
    """Return ``(receiver, simple_name)`` from a JS call's full name."""
    full = full_name or bare_name
    if "." in full:
        receiver, simple = full.rsplit(".", 1)
        return receiver, simple
    return "", full or bare_name


def _lookup_in_file(
    ctx: JavaScriptResolverContext, file_path: str, simple: str
) -> int | None:
    """Symbol id of a same-file BARE-CALLABLE named ``simple`` in ``file_path``.

    Restricted to a top-level ``function`` (see ``_BARE_CALLABLE_KINDS``): a
    bare ``foo()`` is the only same-scope form routed here, and a bare call
    cannot target a class ``method`` (it needs an owning receiver) nor a
    ``class`` (that is a construction, not a plain call). Real resolver contexts
    populate ``file_symbols`` with EVERY method in the file, so matching
    ``method`` here would bind a bare ``render()`` to a sibling class's method —
    a concrete wrong edge (Codex P2 #346, line 235). ``this.<method>`` is bound
    separately through the unambiguous single-class gate, not here.
    """
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in _BARE_CALLABLE_KINDS:
            return sym_id
    return None


#: Symbol kinds that a BARE call (no receiver, no import) can legally target.
#: A top-level ``function`` is callable as ``foo()``; a class ``method`` is NOT
#: (it needs an owning receiver), and a ``class`` used bare is a construction,
#: not a plain call. ``global_name_table`` drops the kind, so the project tier
#: cross-checks ``file_symbols`` and only binds a bare-callable kind — otherwise
#: ``render()`` wires to a same-named method elsewhere (Codex P2 #346).
_BARE_CALLABLE_KINDS: frozenset[str] = frozenset({"function"})


def _owner_kind(ctx: JavaScriptResolverContext, owner_file: str, sym_id: int) -> str:
    """Kind (``function``/``method``/``class``) of ``sym_id`` in ``owner_file``.

    Recovered from ``file_symbols`` because the shared ``global_name_table``
    carries only ``(file, id)`` and drops the kind. Returns ``""`` when the
    owner row is not present (so the caller can treat it conservatively).
    """
    for _name, kind, sid in ctx.file_symbols.get(owner_file, []):
        if sid == sym_id:
            return kind
    return ""


def _js_project_owns(ctx: JavaScriptResolverContext, simple: str) -> bool:
    """True when a JS-FAMILY project symbol is named ``simple``.

    Language-aware ownership gate: a same-named symbol in an incompatible
    language (a Python ``parse``, a Java ``keys``) does NOT count, so it can
    never suppress a builtin classification or be mis-bound as ``project``.

    Consults BOTH the function/method/class table and the JS-family
    ``variable`` shadows, so an object-literal namespace such as
    ``const Math = {...}`` also counts as ownership and suppresses the builtin
    tier (Codex P2 #346).
    """
    if simple in ctx.shadowed_globals:
        return True
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if languages_compatible("javascript", owner_lang):
            return True
    return False


def resolve_javascript_callee(
    bare_name: str,
    full_name: str,
    caller_file: str,
    lang_ctx: JavaScriptResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one JavaScript call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``project`` / ``builtin`` / ``unknown``. Conservative by
    construction: anything not provably one of the first three is ``unknown``.
    """
    ctx = lang_ctx
    receiver, simple = _split_receiver(full_name, bare_name)

    # 1. local — a call into the caller's own file. ``self`` is NOT here — it is
    #    the JS global scope, not the current object (Codex P2 #346).
    #
    #    The two same-scope forms are resolved by SEPARATE paths because they
    #    have different binding rules:
    #
    #    * bare ``foo()`` (no receiver) — never a method call, so the flat
    #      ``file_symbols`` scan is safe: it can only legitimately hit a
    #      same-file ``function``/``class`` (a top-level callable).
    #    * ``this.foo()`` — a METHOD call. It must NOT go through the flat
    #      ``file_symbols`` scan: real resolver contexts populate
    #      ``file_symbols`` with EVERY method in the file (sibling classes
    #      included), so a flat lookup of ``this.render`` from ``A.run`` would
    #      find a SIBLING ``B.render`` and bind a concrete wrong edge. It may
    #      only bind through ``file_class_methods`` AND only when the file
    #      defines exactly ONE class (so ``this`` is unambiguous). With 2+
    #      classes we lack the caller's enclosing class → stay ``unknown``
    #      (Codex P2 #346, line 235).
    if receiver == "":
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
    elif receiver == "this":
        classes = ctx.file_class_methods.get(caller_file, {})
        if len(classes) == 1:
            ((_cls, methods),) = classes.items()
            mid = methods.get(simple)
            if mid is not None:
                return mid, "local", caller_file

    # 2. builtin — a namespaced JS global call matched on the FULL dotted name
    #    (``JSON.parse``, ``Object.keys`` …). Terminal: outside the project.
    #    Suppressed if the project itself owns the receiver name in a JS file
    #    (a domain object literally named ``Math``/``JSON`` shadowing the global).
    if receiver:
        full = full_name or f"{receiver}.{simple}"
        head = receiver.split(".", 1)[0]
        if full in JS_BUILTIN_CALLS and not _js_project_owns(ctx, head):
            return None, "builtin", ""

    # 3. project — exactly one JS-family project-wide definition of a BARE name,
    #    AND that definition must be a bare-callable kind (a top-level
    #    ``function``). A class ``method`` is not callable without a receiver and
    #    a bare ``class`` name is a construction, not a plain call — binding
    #    ``render()`` to a same-named method elsewhere is a wrong cross-file edge
    #    (Codex P2 #346). Gated by language so a same-name Python/Java symbol is
    #    never bound (the MOAT).
    if not receiver:
        js_cands = [
            (owner_file, sym_id)
            for owner_file, sym_id in ctx.global_name_table.get(simple, [])
            if languages_compatible(
                "javascript", ctx.file_languages.get(owner_file, "")
            )
            and _owner_kind(ctx, owner_file, sym_id) in _BARE_CALLABLE_KINDS
        ]
        if len(js_cands) == 1:
            target_file, sym_id = js_cands[0]
            return sym_id, "project", target_file

    # 4. unknown — the conservative default. Never a cross-language binding.
    return None, "unknown", ""


# Register under every JS-family dialect this resolver serves. ``resolve_callee``
# dispatches by the caller file's exact language tag, and the language detector
# tags ``.jsx`` files as ``"jsx"`` — so without the ``jsx`` registration those
# callers bypass this SAFE resolver and leak into the Python cascade (Codex P2
# #346). TS/TSX have their own resolvers and are intentionally not claimed here.
for _dialect in _JS_DIALECTS:
    register_language(_dialect, build_javascript_context, resolve_javascript_callee)
