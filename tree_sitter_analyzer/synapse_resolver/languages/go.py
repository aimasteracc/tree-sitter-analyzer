"""Go callee resolver (RFC-0010, first wave).

Self-contained and SAFE — it REPLACES the Python cascade for Go callers, so
its only jobs are:

1. **local** — resolve a same-file ``func``/method call against the caller
   file's own symbols (same-language by construction → no cross-language
   binding is even possible).
2. **stdlib** — classify a package-qualified call (``fmt.Println``,
   ``strings.Split``) when the qualifier is a conservative canonical stdlib
   package name AND the project does not itself define that name (shadowing
   preserved). See :mod:`._go_constants`.
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
from ._go_constants import STDLIB_PACKAGES_GO


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


def build_go_resolver_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy; unused)
    **_ignored: Any,
) -> GoResolverContext | None:
    """Build the Go context, or ``None`` when no Go file is indexed.

    Zero cost for non-Go projects (gated on ``file_languages``). ``file_symbols``
    is the shared cross-language map; the resolver reads only the caller file's
    own entry, so carrying the full map is safe. The class-method thunk is not
    needed (Go receiver types are not inferable from the edge), so it is never
    called — preserving the lazy "pay nothing if you opt out early" property.
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
    return GoResolverContext(
        file_symbols=file_symbols,
        project_names=frozenset(project_names),
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

    # 2. stdlib — a package-qualified call whose package head is a conservative
    #    canonical stdlib package AND is not shadowed by a project symbol.
    head = qualifier.split(".", 1)[0]
    if head in STDLIB_PACKAGES_GO and head not in ctx.project_names:
        return None, "stdlib", ""

    # 3. unknown — receiver method calls (``s.Run`` — type not inferable),
    #    third-party packages, shadowed names. Never guess.
    return None, "unknown", ""


register_language("go", build_go_resolver_context, resolve_go_callee)


__all__ = [
    "GoResolverContext",
    "build_go_resolver_context",
    "resolve_go_callee",
]
