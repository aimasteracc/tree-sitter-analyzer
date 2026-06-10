#!/usr/bin/env python3
"""
Feature 1 (Synapse) — Index-time cross-file callee resolution.

Public API:
    ``ResolverContext``     — project-wide indices, built once per pass.
    ``ResolvedCallee``      — output of one resolution.
    ``resolve_callee``      — one callee → ResolvedCallee, per priority cascade.
    ``parse_imports``       — import-statement text -> structured rows.
    ``build_resolver_context`` — populate a ResolverContext from the cache.
    ``is_enabled``          — honour the ``TSA_SYNAPSE`` env var.
    ``BUILTINS_PY``         — Python builtin callable names.
    ``STDLIB_NAMES_PY``     — Python stdlib top-level module names.

Priority cascade implemented by ``resolve_callee``:
  1. local      – same-file function/method match.
  2. self/cls   – ``self.X`` or ``cls.X`` on the same class.
  3. import     – name imported via ``from M import X``, or module alias
                  qualifier (``bb.baz`` after ``from . import b as bb``).
  4. stdlib     – allowlist of stdlib modules / builtins.
  5. single     – exactly one project-wide definition with that name.
  6. unknown    – nothing matched.

Star imports get an ``ast_imports`` row with ``is_star=1`` but the
resolver does NOT promote star-imported names to ``project`` in 3a.
"""

from __future__ import annotations

from dataclasses import dataclass

from .._language_family import languages_compatible
from ._constants import (
    BUILTIN_QUALIFIED_PY,
    BUILTINS_PY,
    EXTERNAL_METHODS_PY,
    STDLIB_METHODS_PY,
    STDLIB_NAMES_PY,
)
from ._context import ResolverContext, build_resolver_context, is_enabled
from ._imports import ImportEntry, parse_imports


@dataclass(frozen=True)
class ResolvedCallee:
    """One resolution per call edge — written into the unified ``edges`` table."""

    callee_symbol_id: int | None
    resolution: str
    resolved_file: str


def _split_qualifier(name: str) -> tuple[str, str]:
    """Split ``"a.b.c"`` into ``("a.b", "c")``. Returns ``("", name)`` if no dot."""
    if "." in name:
        head, tail = name.rsplit(".", 1)
        return head, tail
    return "", name


def _lookup_symbol_id(file: str, name: str, ctx: ResolverContext) -> int | None:
    """Find a project symbol id for ``name`` in ``file``."""
    for sym_name, kind, sym_id in ctx.file_symbols.get(file, []):
        if sym_name == name and kind in ("function", "method", "class"):
            return sym_id
    return None


def _item_symbol_id(item: object) -> int | None:
    if isinstance(item, dict):
        value = item.get("id")
        return int(value) if value is not None else None
    value = getattr(item, "id", None)
    return int(value) if value is not None else None


def _item_file(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("file", item.get("file_path", "")))
    return str(getattr(item, "file", getattr(item, "file_path", "")))


def _try_self_method(
    base: str,
    qualifier: str,
    caller_file: str,
    caller_name: str,
    ctx: ResolverContext,
) -> ResolvedCallee | None:
    if qualifier not in ("self", "cls"):
        return None
    classes = ctx.file_class_methods.get(caller_file, {})
    # P2 (Codex review): restrict self.X to the CALLER's enclosing class, not
    # every class in the file. The enclosing class is the one that defines the
    # caller method (caller_name). Without this, `A.f` calling `self.helper()`
    # would wrongly resolve to `B.helper` when only B defines it.
    enclosing = [cls for cls, methods in classes.items() if caller_name in methods]
    if len(enclosing) == 1:
        sym_id = classes[enclosing[0]].get(base)
        return (
            ResolvedCallee(sym_id, "local", caller_file) if sym_id is not None else None
        )
    # Enclosing class unknown/ambiguous → only resolve when base is defined in
    # exactly ONE class (no cross-class guess).
    defs = [methods[base] for methods in classes.values() if base in methods]
    if len(defs) == 1:
        return ResolvedCallee(defs[0], "local", caller_file)
    return None


def _try_local(
    base: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    if ctx.callee_resolver is None:
        sym_id = _lookup_symbol_id(caller_file, base, ctx)
        if sym_id is not None:
            return ResolvedCallee(sym_id, "local", caller_file)
        return None
    match = ctx.callee_resolver.resolve_first_item(
        base,
        caller_file,
        include_import=False,
        include_global=False,
    )
    if match is not None:
        item, _confidence = match
        return ResolvedCallee(_item_symbol_id(item), "local", _item_file(item))
    return None


def _try_import(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """Two cases:
    * ``bb.baz()`` after ``from . import b as bb``: alias bb -> b.py.
    * ``baz()`` after ``from .b import baz``: name baz -> b.py.
    """
    if ctx.callee_resolver is None:
        if qualifier:
            target = ctx.import_alias_target.get(caller_file, {}).get(qualifier)
            if target is None and "." in qualifier:
                target = ctx.import_alias_target.get(caller_file, {}).get(
                    qualifier.split(".", 1)[0]
                )
            if target:
                return ResolvedCallee(
                    _lookup_symbol_id(target, base, ctx), "project", target
                )

        target = ctx.name_to_source.get(caller_file, {}).get(base)
        if target:
            return ResolvedCallee(
                _lookup_symbol_id(target, base, ctx), "project", target
            )
        return None

    query = f"{qualifier}.{base}" if qualifier else base
    match = ctx.callee_resolver.resolve_first_item(
        query,
        caller_file,
        include_local=False,
        include_global=False,
    )
    if match is not None:
        item, _confidence = match
        return ResolvedCallee(_item_symbol_id(item), "project", _item_file(item))
    file_match = ctx.callee_resolver.resolve_first_file(
        query,
        caller_file,
        include_unmatched_import=True,
        include_local=False,
        include_global=False,
    )
    if file_match is not None:
        target, _confidence = file_match
        return ResolvedCallee(_lookup_symbol_id(target, base, ctx), "project", target)
    return None


def _try_stdlib(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """Two strategies:
    1. ``from <stdlib_mod> import X`` makes ``X()`` stdlib.
    2. ``import <stdlib_mod>`` makes ``<stdlib_mod>.X()`` stdlib.
    """
    stdlib_modules = ctx.stdlib_modules.get("python", frozenset())
    if not stdlib_modules:
        return None
    for imp in ctx.imports_by_file.get(caller_file, []):
        if imp.is_star:
            continue
        top = imp.module_path.lstrip(".").split(".")[0]
        if not top or top not in stdlib_modules:
            continue
        if imp.local_name == base and not qualifier:
            return ResolvedCallee(None, "stdlib", "")
        if qualifier:
            head = qualifier.split(".", 1)[0]
            if imp.local_name == head:
                return ResolvedCallee(None, "stdlib", "")
    return None


def _try_builtin(
    base: str, qualifier: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    if qualifier:
        return None
    if base in ctx.builtins.get("python", frozenset()):
        return ResolvedCallee(None, "builtin", "")
    return None


def _table_language(ctx: ResolverContext, caller_file: str) -> str:
    """Language key for the RFC-0004/5/7 method tables (stdlib/external/builtin).

    Trusts a populated ``file_languages`` map: a tagged non-Python caller (a JS
    file) looks up its own (absent) table and the tier no-ops, preserving the
    cross-language gate. Falls back to ``"python"`` ONLY when ``file_languages``
    is entirely empty — a pre-built / direct-API ``ResolverContext`` whose public
    constructor does not require it — so Python calls (``path.write_text()``,
    ``monkeypatch.setattr()``) keep their RFC-0004/5/7 classification instead of
    regressing to ``unknown`` (Codex P2 #326). The ownership gate keeps using the
    raw ``caller_lang`` (empty == compatible), so legacy behaviour is unchanged.
    """
    lang = ctx.file_languages.get(caller_file, "")
    if lang:
        return lang
    return "python" if not ctx.file_languages else ""


def _try_stdlib_method(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """RFC-0004 FINAL tier: classify a bare stdlib/builtin method name as
    ``stdlib`` — but only when the project owns no method of that name.

    Runs AFTER every project-binding rule, so a project ``split``/``get``/``items``
    has already resolved to ``project`` before reaching here. The project-symbol
    gate additionally leaves AMBIGUOUS project names (two classes define ``get``)
    as ``unknown`` rather than mislabeling them ``stdlib``.

    The gate is LANGUAGE-AWARE (Codex P2): a same-named symbol in an
    incompatible-language file (e.g. a JavaScript ``split``) must NOT suppress
    the Python stdlib classification — Python ``'x'.split()`` is still stdlib.
    Only a same-/compatible-language project method counts as ownership.

    RFC-0008: the table is selected by the CALLER's language, not hard-coded
    ``"python"``. A Java caller consults the Java stdlib-method table; a caller
    whose language has no registered table looks up an empty frozenset and the
    tier never fires (conservative — no false classification).
    """
    caller_lang = ctx.file_languages.get(caller_file, "")
    if base not in ctx.stdlib_methods.get(
        _table_language(ctx, caller_file), frozenset()
    ):
        return None
    if ctx.callee_resolver is not None:
        matches = ctx.callee_resolver.resolve_items(
            base, "", include_local=False, include_import=False
        )
        for item, _confidence in matches:
            item_lang = ctx.file_languages.get(_item_file(item), "")
            # A project method the caller's language could actually call → the
            # project owns the name; leave ``unknown`` rather than claim stdlib.
            if (
                not caller_lang
                or not item_lang
                or languages_compatible(caller_lang, item_lang)
            ):
                return None
    return ResolvedCallee(None, "stdlib", "")


def _try_external_method(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """RFC-0005 FINAL tier: classify a bare third-party library method name as
    ``external`` — but only when the project owns no compatible-language method
    of that name.

    Runs AFTER ``_try_stdlib_method`` (itself the last tier before ``unknown``),
    so stdlib wins over external, and every project-binding rule still wins first.
    The project-symbol gate is language-aware (same pattern as Codex P2 #319 fix
    in ``_try_stdlib_method``): an incompatible-language symbol does NOT count as
    project ownership.

    Covers pytest, hypothesis, and unittest.mock method names that cannot live in
    the project and would otherwise remain ``unknown``.

    RFC-0008: the table is selected by the CALLER's language (Java consults the
    JUnit/Mockito/AssertJ table); a language with no registered table looks up
    an empty frozenset and the tier never fires.
    """
    caller_lang = ctx.file_languages.get(caller_file, "")
    if base not in ctx.external_methods.get(
        _table_language(ctx, caller_file), frozenset()
    ):
        return None
    if ctx.callee_resolver is not None:
        matches = ctx.callee_resolver.resolve_items(
            base, "", include_local=False, include_import=False
        )
        for item, _confidence in matches:
            item_lang = ctx.file_languages.get(_item_file(item), "")
            # A project method the caller's language could actually call → the
            # project owns the name; leave ``unknown`` rather than claim external.
            if (
                not caller_lang
                or not item_lang
                or languages_compatible(caller_lang, item_lang)
            ):
                return None
    return ResolvedCallee(None, "external", "")


def _try_builtin_method(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """RFC-0007 FINAL tier: classify a qualified Python builtin name as ``builtin``.

    ``_try_builtin`` classifies bare builtin calls (no qualifier) as ``builtin``.
    But ``monkeypatch.setattr(...)`` has a qualifier, so ``_try_builtin`` skips it
    (``if qualifier: return None``) and the edge falls through to ``unknown``.
    This tier recovers those edges for names in BUILTIN_QUALIFIED_PY — builtins
    that legitimately appear with a receiver qualifier.

    Runs AFTER ``_try_external_method`` so every project-binding rule and every
    stdlib/external tier wins first.  The project-symbol gate is language-aware
    (same Codex P2 pattern as RFC-0004/0005): an incompatible-language project
    symbol does NOT suppress Python builtin classification.

    Returns ``ResolvedCallee(None, "builtin", "")`` — no resolved file, because
    Python builtins have no project file.
    """
    if not qualifier:
        # Bare (unqualified) builtins are already handled by _try_builtin; skip.
        return None
    # RFC-0008: gate on TABLE PRESENCE, not a hard-coded ``!= "python"``. Only a
    # caller whose language registers a qualified-builtin table can match here;
    # a caller language with no such table (e.g. Java — which has no
    # monkeypatch.setattr equivalent, static methods are import-resolved) looks
    # up an empty frozenset and the tier never fires. An empty/unknown language
    # tag also yields an empty table, so untyped callers fall through safely.
    caller_lang = ctx.file_languages.get(caller_file, "")
    if base not in ctx.builtin_methods.get(
        _table_language(ctx, caller_file), frozenset()
    ):
        return None
    if ctx.callee_resolver is not None:
        matches = ctx.callee_resolver.resolve_items(
            base, "", include_local=False, include_import=False
        )
        for item, _confidence in matches:
            item_lang = ctx.file_languages.get(_item_file(item), "")
            # A project method the caller's language could actually call → the
            # project owns the name; leave ``unknown`` rather than claim builtin.
            if (
                not caller_lang
                or not item_lang
                or languages_compatible(caller_lang, item_lang)
            ):
                return None
    return ResolvedCallee(None, "builtin", "")


def _try_single_global(
    base: str, qualifier: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    if qualifier:
        return None
    if ctx.callee_resolver is not None:
        matches = ctx.callee_resolver.resolve_items(
            base,
            "",
            include_local=False,
            include_import=False,
        )
        if len(matches) == 1:
            item, _confidence = matches[0]
            return ResolvedCallee(_item_symbol_id(item), "project", _item_file(item))
        return None
    cands = ctx.global_name_table.get(base, [])
    if len(cands) == 1:
        target_file, sym_id = cands[0]
        return ResolvedCallee(sym_id, "project", target_file)
    return None


def _try_class_method(
    base: str, qualifier: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """RFC-0002: receiver-type-aware method resolution.

    When the qualifier is a KNOWN CLASS NAME (the extractor inferred the
    receiver's type from a ``var = ClassName(...)`` assignment and rewrote the
    callee as ``ClassName.method``), resolve ``base`` to that class's method.
    This is what disambiguates NON-unique methods (e.g. ``execute`` defined on
    many classes) that ``_try_unique_method`` deliberately leaves unknown — the
    receiver type pins down which class.
    """
    if not qualifier:
        return None
    # P2 (Codex): a class name may be defined in multiple modules (Client,
    # Config, Handler...). Picking the first match could resolve to the wrong
    # module. Only resolve when the (class, method) is unique project-wide;
    # otherwise stay unknown rather than guess the wrong file.
    found: tuple[str, int] | None = None
    for file_path, classes in ctx.file_class_methods.items():
        methods = classes.get(qualifier)
        if methods is None:
            continue
        sym_id = methods.get(base)
        if sym_id is None:
            continue
        if found is not None and (file_path, sym_id) != found:
            return None  # duplicate class name across modules — ambiguous
        found = (file_path, sym_id)
    if found is not None:
        return ResolvedCallee(found[1], "project", found[0])
    return None


def _try_unique_method(
    base: str, qualifier: str, caller_file: str, ctx: ResolverContext
) -> ResolvedCallee | None:
    """RFC-0002 Phase 1: receiver method call where the method name is unique.

    For ``obj.method()`` whose receiver type we cannot infer, if ``method`` is
    defined on exactly ONE class across the whole project, resolve to it. If it
    is defined on multiple classes (e.g. ``execute``), return ``None`` and stay
    ``unknown`` rather than guess. Requires a qualifier (a receiver); ``self``/
    ``cls`` are already handled by ``_try_self_method``, and bare names by the
    global rules above — so this only fires for true receiver method calls the
    earlier rules left unresolved.

    Builtin-receiver guard (Issue #447): when ``base`` is a well-known stdlib
    method name (``get``, ``append``, ``items``, …) and the receiver type is
    unknown, the caller is almost certainly using a builtin container/string
    method, not a project-defined method. Binding it to a project symbol just
    because it happens to be unique would produce the same-name mis-wire the
    README claims TSA eliminates. Conservative policy: ``unknown > wrong``.
    This guard does NOT affect ``_try_class_method`` (receiver type IS known
    via AST inference) or ``_try_import``/``_try_local`` (explicit import).
    """
    if not qualifier or qualifier in ("self", "cls"):
        return None
    # Builtin-receiver gate: a bare stdlib method name with an unidentifiable
    # receiver must not be claimed as a project symbol via uniqueness.
    # Language-aware: only consult the Python stdlib-method table for Python
    # callers; a Java/JS caller with no registered table looks up an empty
    # frozenset and the gate is a no-op (conservative).
    if base in ctx.stdlib_methods.get(_table_language(ctx, caller_file), frozenset()):
        return None
    found: tuple[str, int] | None = None
    for file_path, classes in ctx.file_class_methods.items():
        for _cls, methods in classes.items():
            sym_id = methods.get(base)
            if sym_id is None:
                continue
            if found is not None and (file_path, sym_id) != found:
                return None  # defined on >1 class — ambiguous, don't guess
            found = (file_path, sym_id)
    if found is not None:
        return ResolvedCallee(found[1], "project", found[0])
    return None


def resolve_callee(
    callee_name: str,
    caller_file: str,
    ctx: ResolverContext,
    callee_full: str | None = None,
    caller_name: str = "",
) -> ResolvedCallee:
    """Resolve a single callee, dispatching by the caller file's language.

    Python keeps the original cascade verbatim. Java routes to the Java
    resolver (when a Java context is present), using ``callee_full`` to
    recover the receiver. Any other language falls through to the Python
    cascade exactly as before B3 (no behaviour change for them).
    """
    # RFC-0010: dispatch to a registered per-language resolver (when one exists
    # AND its context was built), else fall through to the Python cascade. Java is
    # now registered via languages/java.py instead of an inline branch; adding a
    # language requires no edit here.
    language = ctx.file_languages.get(caller_file)
    from . import languages as _languages  # noqa: F401, PLC0415 — ensure registration
    from ._registry import get_language_resolver

    resolver = get_language_resolver(language)
    lang_ctx = ctx.lang_context(language) if resolver is not None and language else None
    if resolver is not None and lang_ctx is not None:
        sym_id, resolution, resolved_file = resolver.resolve_callee(
            callee_name,
            callee_full if callee_full is not None else callee_name,
            caller_file,
            lang_ctx,
        )
        return ResolvedCallee(sym_id, resolution, resolved_file)

    return _resolve_callee_python(
        callee_name, caller_file, ctx, callee_full, caller_name
    )


def _resolve_callee_python(
    callee_name: str,
    caller_file: str,
    ctx: ResolverContext,
    callee_full: str | None = None,
    caller_name: str = "",
) -> ResolvedCallee:
    """Resolve a single callee per the priority cascade above.

    ``callee_name`` is the bare name (receiver stripped); ``callee_full`` keeps
    the receiver (e.g. ``self._scan_disk_files``). The bare name loses the
    ``self``/``cls`` qualifier, so ``self.X`` calls would never reach
    ``_try_self_method`` — the #1 source of ``unknown`` edges. When
    ``callee_full`` carries a ``self``/``cls`` receiver, split on it so those
    method calls resolve.
    """
    # P2 (Codex review): split on callee_full whenever it carries a receiver,
    # not just self/cls — otherwise `pg.all_edges()` (callee_name='all_edges',
    # callee_full='pg.all_edges') loses the `pg` qualifier and _try_unique_method
    # never fires on the production rows it was meant to resolve.
    if callee_full and "." in callee_full:
        qualifier, base = _split_qualifier(callee_full)
    else:
        qualifier, base = _split_qualifier(callee_name)

    caller_lang = ctx.file_languages.get(caller_file, "")
    for rule in (
        lambda: _try_self_method(base, qualifier, caller_file, caller_name, ctx),
        lambda: _try_local(base, caller_file, ctx) if not qualifier else None,
        lambda: _try_import(base, qualifier, caller_file, ctx),
        lambda: _try_stdlib(base, qualifier, caller_file, ctx),
        # Project-wide searches run BEFORE the builtin fallback so that a project
        # function with the same name as a builtin (e.g. a custom ``len``) is
        # resolved to the project definition, not mis-classified as ``builtin``
        # (RFC-0002 criterion 2 — shadowing preserved).
        lambda: _try_single_global(base, qualifier, ctx),
        lambda: _try_class_method(base, qualifier, ctx),
        lambda: _try_unique_method(base, qualifier, caller_file, ctx),
        # Builtin is the last NAME resort: only fires when no project binding exists.
        lambda: _try_builtin(base, qualifier, ctx),
        # RFC-0004: stdlib METHOD names (write_text, strip, items, …) — gated on
        # the project owning no compatible-language method.
        lambda: _try_stdlib_method(base, qualifier, caller_file, ctx),
        # RFC-0005: external (third-party) library method names — pytest, hypothesis,
        # unittest.mock. Runs AFTER stdlib so stdlib wins, and every project-binding
        # rule still wins first. Same language-aware project-ownership gate.
        lambda: _try_external_method(base, qualifier, caller_file, ctx),
        # RFC-0007: qualified Python builtin names (monkeypatch.setattr, obj.getattr,
        # …). _try_builtin skips qualified calls; this tier recovers them. Runs LAST
        # so every project-binding, stdlib, and external rule wins first.
        lambda: _try_builtin_method(base, qualifier, caller_file, ctx),
    ):
        out = rule()
        if out is not None and not _is_cross_language(out, caller_lang, ctx):
            return out

    return ResolvedCallee(None, "unknown", "")


def _is_cross_language(
    out: ResolvedCallee, caller_lang: str, ctx: ResolverContext
) -> bool:
    """True when a project bind crosses a language boundary.

    The project-wide rules (``_try_single_global`` / ``_try_class_method`` /
    ``_try_unique_method``) scan every file regardless of language, so a Python
    ``config.get(...)`` whose ``get`` is defined only on a JavaScript class would
    bind to that JS file — a wrong callee with a foreign-language body inlined
    into the response. Reject such binds so the cascade falls through to
    ``unknown`` rather than crossing languages. ``local``/``stdlib`` binds resolve
    to the caller file or carry no file, so they never trip this.
    """
    if not caller_lang or not out.resolved_file:
        return False
    target_lang = ctx.file_languages.get(out.resolved_file, "")
    return bool(target_lang) and not languages_compatible(caller_lang, target_lang)


__all__ = [
    "BUILTIN_QUALIFIED_PY",
    "BUILTINS_PY",
    "EXTERNAL_METHODS_PY",
    "STDLIB_METHODS_PY",
    "STDLIB_NAMES_PY",
    "ImportEntry",
    "ResolvedCallee",
    "ResolverContext",
    "build_resolver_context",
    "is_enabled",
    "parse_imports",
    "resolve_callee",
]
