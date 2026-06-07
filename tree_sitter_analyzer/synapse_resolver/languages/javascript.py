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
_SELF_RECEIVERS: frozenset[str] = frozenset({"", "this", "self"})


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


def build_javascript_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # lazy thunk -> class->method map
    **_ignored: Any,
) -> JavaScriptResolverContext | None:
    """Build the JS context, or ``None`` when no ``.js``/``.jsx`` file is indexed.

    Zero cost for non-JavaScript projects: gated on ``file_languages`` BEFORE the
    lazy ``file_class_methods`` thunk is forced, so a Python/Java-only index
    never pays to materialise the class-method map for JavaScript.
    """
    if not any(lang == "javascript" for lang in file_languages.values()):
        return None
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    return JavaScriptResolverContext(
        file_symbols=file_symbols,
        file_class_methods=fcm or {},
        global_name_table=global_name_table,
        file_languages=file_languages,
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
    """True when a JS-FAMILY project file defines a symbol named ``simple``.

    Language-aware ownership gate: a same-named symbol in an incompatible
    language (a Python ``parse``, a Java ``keys``) does NOT count, so it can
    never suppress a builtin classification or be mis-bound as ``project``.
    """
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

    # 1. local — no receiver (``foo()``) or ``this``/``self`` (``this.foo()``):
    #    a call into the caller's own file.
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


register_language("javascript", build_javascript_context, resolve_javascript_callee)
