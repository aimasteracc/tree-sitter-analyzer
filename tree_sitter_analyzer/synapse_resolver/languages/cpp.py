"""C++ resolver registration (RFC-0010 first wave).

Self-contained, conservative, SAFE per-language callee resolver for C++
(``.cpp`` / ``.cc`` / ``.h`` / ``.hpp``). It REPLACES the Python cascade for
C++ callers, so it must not regress: when unsure it returns ``unknown``.

Resolution order (mirrors the spirit of the Java cascade, far more cautious):

1. **stdlib qualifier** — a call qualified by a standard-library namespace
   (``std::sort``, ``std::make_unique``, ``std::chrono::now``) is ``stdlib``.
   ``std::`` is the canonical, near-unspoofable signal — user code never owns
   ``namespace std``.
2. **local** — no receiver / qualifier (a free function or implicit-``this``
   member call) whose simple name is defined in the caller's OWN file.
3. **project (single-global)** — exactly one same-language project-wide
   definition of an unqualified name. The single-definition gate avoids the
   ambiguity that wrecks method-name precision.
4. **stdlib / external method tiers** — consulted only when the project owns
   no compatible-language method of that name. **Both tiers are empty for the
   first PR** (see ``_cpp_constants``): C++ bare method names collide too
   heavily with user code to classify safely.
5. **unknown** — everything else (instance-receiver calls, qualified calls
   into non-stdlib namespaces, ambiguous names).

THE MOAT: a C++ callee is NEVER bound to a symbol in an incompatible-language
file. ``languages_compatible('cpp', owner_lang)`` gates every project binding,
so a Python / Java / Go symbol that merely shares a name resolves to
``unknown`` (or a same-language def), never the foreign file. C++ MAY resolve
``c`` headers (directional family compat), which is the one legitimate
cross-tag case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..._language_family import languages_compatible
from .._registry import register_language
from ._cpp_constants import (
    EXTERNAL_METHODS_CPP,
    STDLIB_METHODS_CPP,
    is_stdlib_qualifier,
)

#: Extension-derived language tags this resolver owns. ``c`` is intentionally
#: NOT here (pure-C callers use the Python fallback / C handling); this module
#: only drives callers whose own file is tagged ``cpp``.
_CPP_LANGS: frozenset[str] = frozenset({"cpp"})

#: Receiver tokens that denote the current object (an implicit-``this`` call),
#: not a separate type/namespace. A call qualified only by one of these is
#: treated as a local member call.
_SELF_RECEIVERS: frozenset[str] = frozenset({"this", "self", "(*this)", "*this"})


@dataclass
class CppResolverContext:
    """Per-index C++ resolution maps (built once per pass).

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


def build_cpp_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # lazy thunk — unused by the conservative cascade
    **_ignored: Any,
) -> CppResolverContext | None:
    """Build the C++ context, or ``None`` when no C++ file is indexed.

    Zero cost for non-C++ projects (gated on ``file_languages``). The lazy
    ``file_class_methods`` thunk is deliberately NOT called — the conservative
    cascade resolves locals from ``file_symbols`` and projects from the single
    global table, so no class/method map is needed.
    """
    if not any(lang in _CPP_LANGS for lang in file_languages.values()):
        return None
    return CppResolverContext(
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_languages=file_languages,
    )


def _split_qualifier(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(qualifier, simple_name)`` from a C++ call's full name.

    Splits on the C++ access operators ``::`` (scope), ``->`` (pointer), and
    ``.`` (member) — whichever is the LAST separator wins, so the qualifier is
    everything before the final access and the simple name is the trailing
    identifier. ``std::chrono::now`` -> ``("std::chrono", "now")``;
    ``obj->run`` -> ``("obj", "run")``; ``free_fn`` -> ``("", "free_fn")``.
    """
    full = callee_full or callee_name
    if not full:
        return "", callee_name
    # Find the last access operator; ``::`` and ``->`` are two chars, ``.`` one.
    best_idx = -1
    best_len = 0
    for sep in ("::", "->", "."):
        idx = full.rfind(sep)
        if idx > best_idx:
            best_idx = idx
            best_len = len(sep)
    if best_idx < 0:
        return "", full
    qualifier = full[:best_idx]
    simple = full[best_idx + best_len :]
    return qualifier, simple or callee_name


#: Symbol kinds a bare (no-receiver) call may bind to in its own file: a free
#: function, a member method, or a class (constructor-style call).
_LOCAL_KINDS: frozenset[str] = frozenset({"function", "method", "class"})
#: Symbol kinds an explicit-self (``this->`` / ``self``) call may bind to. The
#: receiver PROVES the target is a member, so only ``method`` qualifies — a
#: same-file free function or class is NOT a valid member-call target, and
#: binding one would be a false ``local`` edge.
_MEMBER_KINDS: frozenset[str] = frozenset({"method"})


def _lookup_in_file(
    ctx: CppResolverContext,
    file_path: str,
    simple: str,
    kinds: frozenset[str],
) -> int | None:
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in kinds:
            return sym_id
    return None


def _project_owns(ctx: CppResolverContext, simple: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE project symbol of name ``simple`` exists.

    The RFC-0008 ownership gate, language-aware: a same-named symbol in an
    incompatible-language file (e.g. a Python ``sort``) must NOT count as a C++
    owner — ``languages_compatible('cpp', 'python')`` is False — so it neither
    suppresses a stdlib/external classification nor gets bound. An untagged
    file is treated as a possible owner (conservative).
    """
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible("cpp", owner_lang):
            return True
    return False


def resolve_cpp_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: CppResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one C++ call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``project`` / ``stdlib`` / ``external`` / ``unknown``.
    """
    qualifier, simple = _split_qualifier(callee_full, callee_name)
    is_unqualified = qualifier == ""
    is_self_receiver = qualifier in _SELF_RECEIVERS

    # 1. stdlib qualifier — ``std::...`` and friends are terminal stdlib. This
    #    wins first: the qualifier is unambiguous evidence and never a project
    #    binding (user code never owns ``namespace std``).
    if is_stdlib_qualifier(qualifier):
        return None, "stdlib", ""

    # 2. local — resolved in the caller's OWN file. An UNQUALIFIED call may bind
    #    any local symbol (free function / member / class). An explicit SELF
    #    receiver (``this->`` / ``self``) asserts the target is a member, so it
    #    may bind ONLY a same-file ``method`` — never a free function or class.
    #    If it cannot prove a member target it must NOT fall through to a free
    #    function; an ``unknown`` edge is correct, a false ``local`` is not.
    if is_unqualified or is_self_receiver:
        kinds = _LOCAL_KINDS if is_unqualified else _MEMBER_KINDS
        sym_id = _lookup_in_file(ctx, caller_file, simple, kinds)
        if sym_id is not None:
            return sym_id, "local", caller_file

    # 3. project (single-global) — exactly one same-language project-wide
    #    definition of an UNQUALIFIED name. THE MOAT: gate every candidate by
    #    language compatibility so a foreign-language same-name symbol is never
    #    bound; if the sole candidate is foreign, fall through to unknown.
    #    An explicit SELF receiver is EXCLUDED here: a ``this->`` member call can
    #    never reach a cross-file global, so binding one would be a false edge.
    if is_unqualified:
        compatible = [
            (target_file, sym_id)
            for target_file, sym_id in ctx.global_name_table.get(simple, [])
            if languages_compatible("cpp", ctx.file_languages.get(target_file, ""))
        ]
        if len(compatible) == 1:
            target_file, sym_id = compatible[0]
            return sym_id, "project", target_file

    # 4. stdlib / external METHOD tiers — empty for the first PR, but wired so
    #    a future safe set classifies only when the project owns no
    #    compatible-language method of that name (preserves shadowing).
    if simple in STDLIB_METHODS_CPP and not _project_owns(ctx, simple):
        return None, "stdlib", ""
    if simple in EXTERNAL_METHODS_CPP and not _project_owns(ctx, simple):
        return None, "external", ""

    # 5. unknown — instance-receiver calls, non-stdlib qualified calls, and
    #    ambiguous unqualified names. ``unknown`` is correct: never a mis-wire.
    return None, "unknown", ""


__all__ = [
    "CppResolverContext",
    "build_cpp_context",
    "resolve_cpp_callee",
]


register_language("cpp", build_cpp_context, resolve_cpp_callee)
