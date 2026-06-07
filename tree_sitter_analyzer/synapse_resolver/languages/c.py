"""C resolver registration (RFC-0010 second wave).

Self-contained, conservative, SAFE per-language callee resolver for C
(``.c`` / ``.h``). It REPLACES the Python cascade for C callers, so it must not
regress: when unsure it returns ``unknown``.

C is structurally SIMPLER than C++ — and that simplicity shapes the cascade:

* **No namespace qualifier tier.** C has no ``std::`` analogue, so there is no
  unspoofable namespace signal. The only classified tier is a conservative
  libc free-function name set (``_c_constants``), gated on project ownership.
* **No member-method dispatch.** C has no classes/methods; a ``a->b`` or ``a.b``
  call is a struct-field / function-pointer access on a *value*, whose target
  type the resolver cannot prove. Any such qualified call stays ``unknown``.

Resolution order (most-specific first):

1. **local** — an UNQUALIFIED call whose simple name is a free function defined
   in the caller's OWN file.
2. **project (single-global)** — exactly one same-language project-wide
   definition of an unqualified name. The single-definition gate avoids the
   ambiguity that wrecks name precision.
3. **libc** — an unqualified name in the conservative libc set, but ONLY when
   the project owns no compatible-language function of that name (project
   shadowing wins; classified ``stdlib``).
4. **unknown** — everything else (struct-field / function-pointer calls through
   a receiver, and unqualified names with no local / single-global / libc hit,
   or an ambiguous multi-global name).

THE MOAT: a C callee is NEVER bound to a symbol in an incompatible-language
file. ``languages_compatible('c', owner_lang)`` gates every project binding.
For C this gate is DIRECTIONAL and asymmetric (see ``_language_family``): a C
caller resolves only ``c`` (including ``.h`` headers, indexed as ``c``) — it
must NOT bind a ``cpp`` / ``objc`` / Python / Go definition that merely shares a
name (``languages_compatible('c', 'cpp')`` is False; the C++ side of the
relation is one-directional). A foreign same-name symbol stays ``unknown``.

KNOWN UPSTREAM DEPENDENCY (shared with the C++ resolver): the ``local`` and
single-global ``project`` tiers read ``file_symbols`` / ``global_name_table``,
populated from ``ast_symbol_rows`` by the shared generic symbol walker
(``_ast_extraction._walk_for_symbols``). That walker records a function-like
node only when it exposes ``child_by_field_name('name')`` — but a tree-sitter C
``function_definition`` exposes its identifier under ``function_declarator``,
so ordinary C free functions are currently ABSENT from those maps. Until the
shared extractor recovers C symbols, the local / single-global tiers stay
dormant on a real index and such calls fall through to the libc tier or
``unknown`` (SAFE — never a mis-wire). The maps-independent libc tier and THE
MOAT hold regardless; both are covered by ``TestRealIndexIntegration`` in
``tests/unit/test_c_method_resolution.py``, and the dormant local tier has a
``strict`` xfail there that flips to a hard PASS the moment the extractor is
fixed (the fix lives in the shared walker, out of this module's scope).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..._language_family import languages_compatible
from .._registry import register_language
from ._c_constants import LIBC_FUNCTIONS_C

#: Extension-derived language tags this resolver owns. Only ``c`` — this module
#: drives callers whose own file is tagged ``c`` (``.c`` and ``.h`` headers,
#: which the detector tags ``c``). C++ / ObjC callers use their own resolvers.
_C_LANGS: frozenset[str] = frozenset({"c"})

#: C access operators that introduce a receiver/qualifier. A call carrying any
#: of these is a struct-field / function-pointer access through a value, whose
#: target type C does not let us prove statically -> always ``unknown``.
_ACCESS_OPERATORS: tuple[str, ...] = ("->", ".")


@dataclass
class CResolverContext:
    """Per-index C resolution maps (built once per pass).

    All file keys are project-relative paths, matching the ``edges`` table.
    Only the maps the conservative cascade needs are kept; everything else is
    deliberately omitted to stay minimal and SAFE.
    """

    # file -> [(name, kind, symbol_id), ...] (shared cross-language map).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # simple name -> [(file, symbol_id), ...] project-wide (single-global).
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # file -> language tag (so every project binding is language-gated: the
    # moat — a same-name symbol in another language must NOT be bound).
    file_languages: dict[str, str] = field(default_factory=dict)


def build_c_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Callable[[], dict[str, Any]],  # lazy thunk (unused)
    **_ignored: Any,
) -> CResolverContext | None:
    """Build the C context, or ``None`` when no C file is indexed.

    Zero cost for non-C projects (gated on ``file_languages``). C has no
    member-method dispatch, so the ``file_class_methods`` lazy thunk is accepted
    for contract compatibility but never stored or called — there is no
    owner-class ambiguity to disambiguate.
    """
    if not any(lang in _C_LANGS for lang in file_languages.values()):
        return None
    return CResolverContext(
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_languages=file_languages,
    )


def _has_receiver(callee_full: str, callee_name: str) -> bool:
    """True when the call carries a struct-field / pointer access operator.

    A C call like ``obj->method`` or ``cfg.handler`` accesses a field on a value
    whose type the resolver cannot prove. Such calls are not free-function
    calls, so they must NOT bind a same-name free function -> ``unknown``. A
    bare ``free_fn`` carries no access operator and is treated as unqualified.
    """
    full = callee_full or callee_name
    return any(op in full for op in _ACCESS_OPERATORS)


#: Symbol kinds a bare (no-receiver) C call may bind to in its own file. C has
#: only free functions at call sites; ``function`` is the sole valid kind.
_LOCAL_KINDS: frozenset[str] = frozenset({"function"})


def _lookup_in_file(
    ctx: CResolverContext,
    file_path: str,
    simple: str,
) -> int | None:
    """Resolve ``simple`` to a same-file free ``function`` symbol, or ``None``."""
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in _LOCAL_KINDS:
            return sym_id
    return None


def _project_owns(ctx: CResolverContext, simple: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE project symbol of name ``simple`` exists.

    The RFC-0008 ownership gate, language-aware: a same-named symbol in an
    incompatible-language file (e.g. a Python ``printf`` or a C++ ``malloc``)
    must NOT count as a C owner — ``languages_compatible('c', ...)`` is False
    for those — so it neither suppresses the libc classification nor gets bound.
    An untagged file is treated as a possible owner (conservative).
    """
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible("c", owner_lang):
            return True
    return False


def resolve_c_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: CResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one C call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``project`` / ``stdlib`` / ``unknown``.
    """
    # A receiver-qualified call (``obj->fn`` / ``cfg.fn``) accesses a struct
    # field / function pointer whose target type C does not let us prove. It is
    # not a free-function call, so it must never bind one -> unknown.
    if _has_receiver(callee_full, callee_name):
        return None, "unknown", ""

    simple = callee_name

    # 1. local — an unqualified call resolved to a same-file free function.
    sym_id = _lookup_in_file(ctx, caller_file, simple)
    if sym_id is not None:
        return sym_id, "local", caller_file

    # 2. project (single-global) — exactly one same-language project-wide
    #    definition. THE MOAT: gate every candidate by language compatibility so
    #    a foreign-language same-name symbol is never bound; if the sole
    #    candidate is foreign, fall through (eventually to unknown).
    compatible = [
        (target_file, candidate_id)
        for target_file, candidate_id in ctx.global_name_table.get(simple, [])
        if languages_compatible("c", ctx.file_languages.get(target_file, ""))
    ]
    if len(compatible) == 1:
        target_file, candidate_id = compatible[0]
        return candidate_id, "project", target_file

    # 3. libc tier — a conservative libc free-function name, classified
    #    ``stdlib`` ONLY when the project owns no compatible-language function of
    #    that name (project shadowing wins).
    if simple in LIBC_FUNCTIONS_C and not _project_owns(ctx, simple):
        return None, "stdlib", ""

    # 4. unknown — receiver calls (handled above), ambiguous multi-global names,
    #    and names with no local / single-global / libc hit. ``unknown`` is
    #    correct: never a mis-wire.
    return None, "unknown", ""


__all__ = [
    "CResolverContext",
    "build_c_context",
    "resolve_c_callee",
]


register_language("c", build_c_context, resolve_c_callee)
