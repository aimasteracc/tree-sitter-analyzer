"""Go callee resolver (RFC-0010, first wave).

Self-contained and SAFE — it REPLACES the Python cascade for Go callers, so
its only jobs are:

1. **local** — resolve a same-file ``func``/method call against the caller
   file's own symbols (same-language by construction → no cross-language
   binding is even possible).
2. **stdlib** — classify a package-qualified call (``fmt.Println``,
   ``strings.Split``) when the qualifier is a conservative canonical stdlib
   package name, is ACTUALLY IMPORTED under that qualifier in the caller file
   (import evidence — a variable that merely shares a stdlib package's name is
   not imported and stays ``unknown``), AND the project does not itself define
   that name (shadowing preserved). See :mod:`._go_constants`.
3. **unknown** — everything else: receiver method calls (``s.Run()`` — the
   receiver is a variable whose struct type the edge does not carry, so we
   never guess), third-party package calls, and any unresolved bare name.

THE MOAT (never cross-language bind): the resolver only ever consults the
caller file's own ``file_symbols`` for a ``local`` match and never looks up a
symbol in another file, so a same-name symbol in a different language's file
can never be bound. Package-qualified calls resolve to ``stdlib``/``unknown``
only — never to a project file.

The cascade returns a plain ``(symbol_id, resolution, resolved_file)`` tuple;
the package ``__init__`` wraps it into a ``ResolvedCallee``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._registry import register_language
from ._go_constants import parse_go_import_block


@dataclass
class GoResolverContext:
    """Per-index Go resolution maps (built once per pass).

    File keys are project-relative paths, matching the ``edges`` table.
    """

    # file -> [(name, kind, symbol_id), ...] (shared cross-language map; we
    # only ever read the CALLER file's own entry, never another file's).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # set of names the project defines anywhere — used to let a project symbol
    # SHADOW a stdlib package qualifier (precision over recall).
    project_names: frozenset[str] = field(default_factory=frozenset)
    # file -> {local package qualifier -> imported stdlib package} for stdlib
    # imports only. A ``pkg.Func`` call classifies as stdlib ONLY when ``pkg``
    # is a key here for the CALLER file (import evidence required — a variable
    # that merely shares a stdlib package's name is NOT imported, so it stays
    # ``unknown``). Aliases map the alias to the underlying stdlib package;
    # blank (``_``) and dot (``.``) imports are excluded (not usable as a
    # qualifier).
    imported_stdlib_by_file: dict[str, frozenset[str]] = field(default_factory=dict)


def _go_import_blocks_from_conn(
    conn: Any, file_languages: dict[str, str]
) -> dict[str, str]:
    """Read each Go file's raw ``import`` text from the AST cache.

    The indexer stores a Go import block (single or grouped) as one
    ``kind='import'`` symbol whose ``name`` is the verbatim block text. We
    concatenate all such rows per file so a file with several import blocks is
    fully covered. Tolerant of a missing/legacy table (returns ``{}``) — the
    resolver then has no import evidence and conservatively classifies every
    package-qualified call ``unknown`` (precision over recall).
    """
    blocks: dict[str, str] = {}
    if conn is None:
        return blocks
    try:
        rows = conn.execute(
            "SELECT file_path, name FROM ast_symbol_rows WHERE kind = 'import'"
        ).fetchall()
    except Exception:  # nosec B110 — table-missing tolerance.
        return blocks
    for row in rows:
        file_path = row["file_path"]
        if file_languages.get(file_path) != "go":
            continue
        blocks[file_path] = blocks.get(file_path, "") + "\n" + (row["name"] or "")
    return blocks


def build_go_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy; unused)
    conn: Any = None,
    go_import_blocks: dict[str, str] | None = None,
    **_ignored: Any,
) -> GoResolverContext | None:
    """Build the Go context, or ``None`` when no Go file is indexed.

    Zero cost for non-Go projects (gated on ``file_languages``). ``file_symbols``
    is the shared cross-language map; the resolver reads only the caller file's
    own entry, so carrying the full map is safe. The class-method thunk is not
    needed (Go receiver types are not inferable from the edge), so it is never
    called — preserving the lazy "pay nothing if you opt out early" property.

    Stdlib classification is gated on **import evidence**: each Go file's raw
    ``import`` text (a ``kind='import'`` symbol) is parsed into the set of
    package qualifiers it actually imports. A ``pkg.Func`` call only classifies
    as stdlib when ``pkg`` is genuinely imported in the caller file — a variable
    that merely shares a stdlib package's name (``var http Client; http.Get()``
    with no ``net/http`` import) is NOT imported and stays ``unknown``. Tests may
    inject ``go_import_blocks`` (file -> raw import text) directly; production
    reads it from ``conn``.
    """
    if not any(lang == "go" for lang in file_languages.values()):
        return None
    # Project-defined names that may SHADOW a stdlib package qualifier. Union
    # the global name table with the per-file symbol names so shadowing is
    # detected regardless of which map a caller populated (the production build
    # fills both; a direct unit build may pass only file_symbols).
    project_names = set(global_name_table)
    for symbols in file_symbols.values():
        for name, _kind, _sym_id in symbols:
            project_names.add(name)

    # Per-file imported stdlib qualifiers (import evidence for the stdlib tier).
    raw_blocks = (
        go_import_blocks
        if go_import_blocks is not None
        else _go_import_blocks_from_conn(conn, file_languages)
    )
    imported_stdlib_by_file: dict[str, frozenset[str]] = {
        file_path: frozenset(parse_go_import_block(raw))
        for file_path, raw in raw_blocks.items()
    }

    return GoResolverContext(
        file_symbols=file_symbols,
        project_names=frozenset(project_names),
        imported_stdlib_by_file=imported_stdlib_by_file,
    )


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(qualifier, simple_name)`` from a Go call's full name.

    ``fmt.Println`` -> ``("fmt", "Println")``; ``s.Run`` -> ``("s", "Run")``;
    bare ``helper`` -> ``("", "helper")``. For a multi-segment receiver only
    the LAST dotted segment is the call name; the qualifier is everything
    before it (e.g. ``a.b.C`` -> ``("a.b", "C")``).
    """
    full = callee_full or callee_name
    if "." in full:
        qualifier, simple = full.rsplit(".", 1)
        return qualifier, simple
    return "", full or callee_name


def _lookup_in_file(ctx: GoResolverContext, file_path: str, simple: str) -> int | None:
    """Find a same-file symbol id for ``simple`` in ``file_path`` only."""
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in ("function", "method", "class"):
            return sym_id
    return None


def resolve_go_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: GoResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one Go call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``stdlib`` / ``unknown``. Conservative by design: when
    unsure, ``unknown`` is the correct (moat-safe) answer.
    """
    qualifier, simple = _split_receiver(callee_full, callee_name)

    # 1. local — a bare call (no qualifier) defined in the CALLER file itself.
    #    Same file == same language, so this can never cross-bind.
    if not qualifier:
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # Bare name not defined in the caller file: do NOT guess a project-wide
        # match (could collide across files/languages). Stay unknown.
        return None, "unknown", ""

    # 2. stdlib — a package-qualified call whose package head is BOTH a
    #    conservative canonical stdlib package AND actually imported under that
    #    qualifier in the CALLER file (import evidence), AND not shadowed by a
    #    project symbol. Requiring the import distinguishes a real package
    #    qualifier from a variable receiver that merely shares the name
    #    (``var http Client; http.Get()`` with no ``net/http`` import → unknown).
    head = qualifier.split(".", 1)[0]
    # ``imported`` holds the caller file's actually-imported stdlib qualifiers
    # (plain package names AND aliases). Membership already proves the qualifier
    # is a stdlib import, so no extra STDLIB_PACKAGES_GO check is needed —
    # checking it would wrongly reject a valid alias (``strs "strings"``).
    imported = ctx.imported_stdlib_by_file.get(caller_file, frozenset())
    if head in imported and head not in ctx.project_names:
        return None, "stdlib", ""

    # 3. unknown — receiver method calls (``s.Run`` — type not inferable),
    #    non-imported names (variables that shadow a stdlib package name),
    #    third-party packages, shadowed names. Never guess.
    return None, "unknown", ""


register_language("go", build_go_resolver_context, resolve_go_callee)


__all__ = [
    "GoResolverContext",
    "build_go_resolver_context",
    "resolve_go_callee",
]
