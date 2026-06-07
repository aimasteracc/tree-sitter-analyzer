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

from ..._language_family import languages_compatible
from .._javascript_constants import JS_BUILTIN_CALLS
from .._registry import register_language

#: Receivers that denote a same-file call rather than an external object.
#: ``self`` is DELIBERATELY EXCLUDED — in browser/worker JavaScript ``self`` is
#: the global scope (``Window.self`` / ``WorkerGlobalScope.self``), not the
#: current object. Treating ``self.foo()`` as a same-file call would bind it to
#: any local helper named ``foo`` — a concrete wrong edge. Only ``this`` (and a
#: bare call) denote the caller's own scope (Codex P2 #346).
_SELF_RECEIVERS: frozenset[str] = frozenset({"", "this"})

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
    """Symbol id of a function/method/class named ``simple`` in ``file_path``."""
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return sym_id
    return None


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

    # 1. local — no receiver (``foo()``) or ``this`` (``this.foo()``): a call
    #    into the caller's own file. ``self`` is NOT here — it is the JS global
    #    scope, not the current object (Codex P2 #346).
    if receiver in _SELF_RECEIVERS:
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        for _cls, methods in ctx.file_class_methods.get(caller_file, {}).items():
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

    # 3. project — exactly one JS-family project-wide definition of a BARE name.
    #    Gated by language so a same-name Python/Java symbol is never bound.
    if not receiver:
        js_cands = [
            (owner_file, sym_id)
            for owner_file, sym_id in ctx.global_name_table.get(simple, [])
            if languages_compatible(
                "javascript", ctx.file_languages.get(owner_file, "")
            )
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
