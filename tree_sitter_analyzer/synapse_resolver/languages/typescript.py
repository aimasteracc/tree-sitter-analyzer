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

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .._registry import register_language
from .._typescript_bindings import TypeScriptBindings
from ._typescript_constants import TYPESCRIPT_GLOBAL_OBJECTS

#: ``file_languages`` tag for every ``.ts``/``.tsx``/``.mts``/``.cts`` file.
_TYPESCRIPT_LANG = "typescript"

#: Receivers that mean "the current object" — a class-scoped ``this``/``super``
#: method call. A *bare* (empty) receiver is handled separately because a bare
#: ``foo()`` is a module-level function call, not a class-method call.
_SELF_RECEIVERS = ("this", "super")


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
    # file -> {names shadowed by a local variable / import binding}. These are
    # NOT in ``global_name_table`` (which is function/method/class-only), so the
    # builtin gate consults this map too — ``const Promise = require('bluebird')``
    # or ``import { Map } from './map'`` must suppress the ``builtin`` claim
    # (Codex P2 #2/#3). File-scoped: a shadow in one file does not affect another.
    shadow_locals: dict[str, set[str]] = field(default_factory=dict)
    #: #1764：相对导入 / 再导出绑定；None 表示不启用（测试注入的旧式上下文）。
    bindings: TypeScriptBindings | None = None


#: Binding names introduced by a TS ``import`` statement. The TS plugin stores
#: the *raw statement text* under the ``import`` symbol's ``text`` field
#: (``ast_imports`` is empty for TS — Codex P2 #3), so the resolver extracts the
#: bound locals itself.
_IMPORT_DEFAULT_RE = re.compile(r"import\s+([A-Za-z_$][\w$]*)\s*(?:,|\s+from\b)")
_IMPORT_NAMESPACE_RE = re.compile(r"import\s+\*\s+as\s+([A-Za-z_$][\w$]*)")
_IMPORT_NAMED_BLOCK_RE = re.compile(r"\{([^}]*)\}")
_IMPORT_NAMED_ITEM_RE = re.compile(
    r"[A-Za-z_$][\w$]*\s+as\s+([A-Za-z_$][\w$]*)|([A-Za-z_$][\w$]*)"
)


def _import_binding_names(statement: str) -> set[str]:
    """Extract the local binding names introduced by one TS ``import`` line.

    Handles ``import D from 'm'`` (default), ``import * as N from 'm'``
    (namespace), and ``import { A, B as C } from 'm'`` (named, honoring ``as``).
    The *local* name is what shadows a global, so ``B as C`` binds ``C``.
    """
    names: set[str] = set()
    m = _IMPORT_NAMESPACE_RE.search(statement)
    if m:
        names.add(m.group(1))
    m = _IMPORT_DEFAULT_RE.search(statement)
    if m:
        names.add(m.group(1))
    block = _IMPORT_NAMED_BLOCK_RE.search(statement)
    if block:
        for item in _IMPORT_NAMED_ITEM_RE.finditer(block.group(1)):
            names.add(item.group(1) or item.group(2))
    names.discard("from")
    names.discard("type")
    return names


def _build_shadow_locals(conn: Any) -> dict[str, set[str]]:
    """Build file -> {variable / import binding names} for every TS file.

    These names are NOT in ``global_name_table`` (function/method/class-only) yet
    they legitimately shadow a builtin global (``const Map = ...`` / ``import {
    Map }``). The builtin gate consults this map so shadowed calls stay
    ``unknown``/project-owned instead of being mis-classified ``builtin``.
    """
    return _scan_ts_payloads(conn)[0]


def _scan_ts_payloads(
    conn: Any,
) -> tuple[dict[str, set[str]], dict[str, Any], dict[str, Any]]:
    """一次扫描：shadow locals，以及 #1764 的 ``ts_imports`` / ``ts_exports``。"""
    out: dict[str, set[str]] = {}
    imports: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    try:
        rows = conn.execute("SELECT file_path, symbols_json FROM ast_index").fetchall()
    except Exception:  # nosec B110 — missing-table tolerance, mirrors _context.py.
        return out, imports, exports
    for row in rows:
        try:
            symbols = json.loads(row["symbols_json"])
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
        if isinstance(symbols.get("ts_imports"), dict):
            imports[row["file_path"]] = symbols["ts_imports"]
        if isinstance(symbols.get("ts_exports"), dict):
            exports[row["file_path"]] = symbols["ts_exports"]
        names: set[str] = set()
        for sym in symbols.get("symbols", []):
            kind = sym.get("kind")
            if kind == "variable":
                name = sym.get("name")
                if name:
                    names.add(name)
            elif kind == "import":
                # The generic AST extractor emits TS imports as
                # ``{"kind": "import", "text": "<raw statement>"}`` — the bound
                # locals live in ``text``, NOT ``name``/``source`` (Codex P2 #4).
                # ``name``/``source`` are kept as fallbacks for other emitters.
                statement = (
                    sym.get("text") or sym.get("name") or sym.get("source") or ""
                )
                names |= _import_binding_names(statement)
        if names:
            out[row["file_path"]] = names
    return out, imports, exports


def build_typescript_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy)
    conn: Any = None,
    shadow_locals: dict[str, set[str]] | None = None,
    **_ignored: Any,
) -> TypeScriptResolverContext | None:
    """Build the TS context, or ``None`` when no TypeScript file is indexed.

    Zero cost for non-TS projects (gated on ``file_languages``). The
    ``file_class_methods`` thunk is only invoked when a TS file is present, so a
    Python/Java-only project pays nothing. ``shadow_locals`` is derived from the
    DB ``conn`` (TS ``import``/``variable`` rows) at build time; tests may inject
    it directly.
    """
    if not any(lang == _TYPESCRIPT_LANG for lang in file_languages.values()):
        return None
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    imports: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    if conn is not None:
        scanned, imports, exports = _scan_ts_payloads(conn)
        if shadow_locals is None:
            shadow_locals = scanned
    return TypeScriptResolverContext(
        file_symbols=file_symbols,
        file_class_methods=fcm or {},
        global_name_table=global_name_table,
        file_languages=file_languages,
        shadow_locals=shadow_locals or {},
        bindings=TypeScriptBindings(
            imports=imports,
            exports=exports,
            file_symbols=file_symbols,
            file_class_methods=fcm or {},
            indexed=frozenset(file_languages),
        ),
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


def _unique_class_method(
    ctx: TypeScriptResolverContext, file_path: str, simple: str
) -> int | None:
    """Return the symbol id when EXACTLY ONE class in ``file_path`` defines a
    method named ``simple``; otherwise ``None``.

    For a ``this``/``super`` call the caller's enclosing class is not available
    to the resolver, so a name defined by two classes in the same file is
    ambiguous. Conservatively we resolve only the unambiguous (single-owner)
    case — never the file-wide first match, which would mis-bind ``B.bar ->
    A.foo`` (Codex P2 #1)."""
    found: int | None = None
    for methods in ctx.file_class_methods.get(file_path, {}).values():
        mid = methods.get(simple)
        if mid is None:
            continue
        if found is not None and found != mid:
            return None  # defined by >1 class — ambiguous, stay unknown.
        found = mid
    return found


def _project_owns(
    ctx: TypeScriptResolverContext, simple: str, caller_file: str
) -> bool:
    """True when a COMPATIBLE-LANGUAGE (TS/JS-family) project symbol named
    ``simple`` exists, OR the caller file shadows ``simple`` with a local
    variable / import binding.

    The shadowing gate: if the project owns the name in a JS/TS-family file, the
    ``builtin`` global-object classification must NOT claim it. The gate is
    LANGUAGE-AWARE — a same-named symbol in an incompatible-language file (a
    Python ``console``) does NOT count, because
    ``languages_compatible("typescript", "python")`` is False. Files with an
    unknown language tag are treated as possible owners (conservative).

    Variable / import shadows (``const Promise = ...`` / ``import { Map }``) are
    file-scoped and never appear in ``global_name_table``, so they are consulted
    via ``shadow_locals`` for the CALLER file only (Codex P2 #2/#3).
    """
    from tree_sitter_analyzer.languages.language_family import languages_compatible

    if simple in ctx.shadow_locals.get(caller_file, set()):
        return True
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible(_TYPESCRIPT_LANG, owner_lang):
            return True
    return False


def _bound(
    ctx: TypeScriptResolverContext, receiver: str, simple: str, caller_file: str
) -> tuple[int, str, str] | None:
    """#1764：导入绑定证明的跨文件目标 ``(符号 id, "project", 文件)``；否则 None。"""
    if ctx.bindings is None:
        return None
    hit = ctx.bindings.resolve(receiver, simple, caller_file)
    if hit is None:
        return None
    sym_id, target_file = hit
    return sym_id, "project", target_file


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

    # 1. local — bare receiver: a same-file top-level function/method/class def.
    #    A bare ``foo()`` is module-scoped, so the file-wide symbol lookup is
    #    correct here (it cannot mis-bind to another class — methods on ``this``
    #    are handled separately below).
    if receiver == "":
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # #1764：经相对具名导入（可经 index.ts 再导出）到达唯一的顶层函数。
        bound = _bound(ctx, "", simple, caller_file)
        if bound is not None:
            return bound
        # A bare unresolved call stays unknown — NO global single-name binding,
        # because that is exactly where cross-language mis-wires creep in.
        return None, "unknown", ""

    # 1b. local — ``this``/``super`` method: class-scoped. The caller's enclosing
    #     class is NOT available to the resolver, so resolve ONLY when exactly one
    #     class in the file defines the method. An ambiguous name (two classes) or
    #     a top-level function (not a method) stays ``unknown`` — never the
    #     file-wide first match that would mis-bind ``B.bar -> A.foo`` (P2 #1).
    if receiver in _SELF_RECEIVERS:
        mid = _unique_class_method(ctx, caller_file, simple)
        if mid is not None:
            return mid, "local", caller_file
        return None, "unknown", ""

    # 2. builtin — receiver head is a distinctive JS/TS global object
    #    (``console``/``JSON``/``Math``…). Gated on the project NOT owning that
    #    global name as a compatible-language symbol OR shadowing it with a local
    #    variable / import binding (shadowing preserved). The head, not the tail,
    #    is the global ("console" in "console.log").
    head = receiver.split(".", 1)[0]
    if head in TYPESCRIPT_GLOBAL_OBJECTS and not _project_owns(ctx, head, caller_file):
        return None, "builtin", ""

    # 2b. #1764 — ``ns.f()`` / ``ns.sub.f()`` through a relative namespace import (and
    #     ``export * as``), or ``Cls.m()`` on a relatively imported class.
    bound = _bound(ctx, receiver, simple, caller_file)
    if bound is not None:
        return bound

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
