"""C# resolver registration (RFC-0010, second wave).

Self-contained, conservative, SAFE per-language callee resolver for C#
(``.cs``). It REPLACES the Python cascade for C# callers, so it must not
regress: when unsure it returns ``unknown``.

Resolution order (mirrors the spirit of the C++ resolver, equally cautious):

1. **System.* qualifier** — a call qualified by the fully-qualified BCL root
   namespace (``System.Console.WriteLine``, ``System.Linq.Enumerable.Select``)
   is ``stdlib``. ``System.`` is the canonical, near-unspoofable signal — user
   code never owns ``namespace System``. This wins first and needs no shadow
   gate.
2. **local** — no receiver (a bare method/function call) or an explicit
   ``this``/``base`` receiver whose simple name is defined in the caller's OWN
   file. A ``this``/``base`` member call binds only when exactly ONE class in
   the file owns that method name (else the caller's class is unprovable →
   unknown).
3. **project (single-global)** — exactly one same-language project-wide
   definition of an UNQUALIFIED name. The single-definition gate avoids the
   ambiguity that wrecks method-name precision. Excluded for ``this``/``base``
   member calls (a member call can never reach a cross-file global).
4. **BCL static-type qualifier tier** — a bare static-type-qualified call
   (``Console.WriteLine``, ``Math.Max``, ``String.Format``) is ``stdlib`` ONLY
   when the project does not itself define a compatible-language symbol of that
   type name (shadowing preserved). See ``_csharp_constants``.
5. **stdlib / external METHOD tiers** — consulted only when the project owns no
   compatible-language symbol of that name. **Both are EMPTY for this PR** (C#
   bare method names collide too heavily with user code to classify safely).
6. **unknown** — everything else (instance-receiver calls, qualified calls into
   non-System / non-BCL types, ambiguous names).

THE MOAT (never cross-language bind): every project binding is gated by
``languages_compatible('csharp', owner_lang)``. C# is its own family (no
directional/symmetric compat with any other tag), so a Python / Java / Go
symbol that merely shares a name resolves to ``unknown`` (or a same-language
def), NEVER the foreign file. The ``System.*`` and BCL tiers resolve to
``stdlib`` only — never to a project file.

The cascade returns a plain ``(symbol_id, resolution, resolved_file)`` tuple;
the package ``__init__`` wraps it into a ``ResolvedCallee``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..._language_family import languages_compatible
from .._registry import register_language
from ._csharp_constants import (
    BCL_STATIC_TYPES_CSHARP,
    EXTERNAL_METHODS_CSHARP,
    STDLIB_METHODS_CSHARP,
    is_system_qualifier,
)

#: Extension-derived language tag this resolver owns (``.cs`` -> ``csharp``).
_CSHARP_LANG: str = "csharp"

#: Receiver tokens that denote the current/base object (a member call), not a
#: separate type/namespace. A call qualified only by one of these is treated as
#: a local member call.
_SELF_RECEIVERS: frozenset[str] = frozenset({"this", "base"})

#: Symbol kinds a bare (no-receiver) call may bind to in its own file: a method,
#: a free function (top-level statements / local functions), or a class
#: (constructor-style call).
_LOCAL_KINDS: frozenset[str] = frozenset({"function", "method", "class"})
#: Symbol kinds an explicit-self (``this.`` / ``base.``) call may bind to. The
#: receiver PROVES the target is a member, so only ``method`` qualifies — a
#: same-file class or free function is NOT a valid member-call target.
_MEMBER_KINDS: frozenset[str] = frozenset({"method"})


@dataclass
class CSharpResolverContext:
    """Per-index C# resolution maps (built once per pass).

    All file keys are project-relative paths, matching the ``edges`` table.
    Only the maps the conservative cascade needs are kept; everything else is
    deliberately omitted to stay minimal and SAFE.
    """

    # file -> [(name, kind, symbol_id), ...] (shared cross-language map; we only
    # ever read the CALLER file's own entry for a ``local`` match).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # simple name -> [(file, symbol_id), ...] project-wide (single-global).
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # file -> language tag (so every project binding is language-gated: the
    # moat — a same-name symbol in another language must NOT be bound).
    file_languages: dict[str, str] = field(default_factory=dict)
    # LAZY thunk -> {file: {class_name: {method_name: symbol_id}}}. Used only to
    # disambiguate a ``this``/``base`` member call when a file declares >1 class
    # owning the same method name: the caller's class is not threaded through the
    # resolver, so a name owned by >1 class is ambiguous and stays unknown. Held
    # as a thunk so non-C# projects and member-free workloads pay nothing — it is
    # materialised at most once, on the first member-call disambiguation.
    class_methods_thunk: Callable[[], dict[str, Any]] | None = None
    # Memoised result of ``class_methods_thunk`` (None until first use).
    _class_methods: dict[str, Any] | None = field(default=None, repr=False)

    def member_owner_class_count(self, file_path: str, method_name: str) -> int:
        """Return how many classes in ``file_path`` define ``method_name``.

        Drives the conservative member-call gate: a ``this``/``base`` call may
        bind a same-file ``method`` only when this count is exactly 1. A count of
        0 (owner-class map silent on the name) means "no ambiguity evidence" and
        the plain same-file lookup stands. The thunk is materialised lazily and
        memoised, so non-member workloads never pay for it.
        """
        if self.class_methods_thunk is None:
            return 0
        if self._class_methods is None:
            self._class_methods = self.class_methods_thunk() or {}
        per_class = self._class_methods.get(file_path, {})
        return sum(1 for methods in per_class.values() if method_name in methods)


def build_csharp_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Callable[[], dict[str, Any]],  # lazy thunk
    **_ignored: Any,
) -> CSharpResolverContext | None:
    """Build the C# context, or ``None`` when no C# file is indexed.

    Zero cost for non-C# projects (gated on ``file_languages``). The lazy
    ``file_class_methods`` thunk is STORED but deliberately NOT called here — it
    is materialised at most once, on the first ``this``/``base`` member call that
    needs owner-class disambiguation (a file declaring >1 class with a colliding
    method name). The plain local / single-global tiers never touch it, so a
    project with no such ambiguity still pays nothing for the class/method map.
    """
    if not any(lang == _CSHARP_LANG for lang in file_languages.values()):
        return None
    return CSharpResolverContext(
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_languages=file_languages,
        class_methods_thunk=file_class_methods,
    )


def _split_qualifier(callee_full: str, callee_name: str) -> tuple[str, str]:
    """Return ``(qualifier, simple_name)`` from a C# call's full name.

    C# member access is the single ``.`` operator; the LAST ``.`` separates the
    qualifier from the call name. ``System.Console.WriteLine`` ->
    ``("System.Console", "WriteLine")``; ``this.World`` -> ``("this", "World")``;
    bare ``Helper`` -> ``("", "Helper")``.
    """
    full = callee_full or callee_name
    if not full:
        return "", callee_name
    if "." in full:
        qualifier, simple = full.rsplit(".", 1)
        return qualifier, simple or callee_name
    return "", full


def _lookup_in_file(
    ctx: CSharpResolverContext,
    file_path: str,
    simple: str,
    kinds: frozenset[str],
) -> int | None:
    """Resolve ``simple`` to a same-file symbol of an allowed ``kind``.

    OWNER-CLASS GATE: when the matched symbol is a ``method`` and the file
    declares more than one class that defines a method of this name, the
    resolver cannot prove which class a ``this``/``base`` call targets (the
    caller's class is not threaded through). Binding either is a false ``local``
    edge, so the ambiguous method is SKIPPED. A ``function`` / ``class`` symbol
    is file-scoped (no owning class), so the gate never applies to it. Count 0
    means "no ambiguity evidence" and the plain match stands.
    """
    ambiguous_method = (
        "method" in kinds and ctx.member_owner_class_count(file_path, simple) > 1
    )
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name != simple or kind not in kinds:
            continue
        if kind == "method" and ambiguous_method:
            # Skip the class-ambiguous method, but keep scanning: an unqualified
            # call may still bind a file-scoped free function / class of the
            # same name (those are not class-owned, so unaffected by the gate).
            continue
        return sym_id
    return None


def _project_owns(ctx: CSharpResolverContext, simple: str) -> bool:
    """True when a COMPATIBLE-LANGUAGE project symbol of name ``simple`` exists.

    The RFC-0008 ownership gate, language-aware: a same-named symbol in an
    incompatible-language file (e.g. a Python ``Console``) must NOT count as a C#
    owner — ``languages_compatible('csharp', 'python')`` is False — so it neither
    suppresses a BCL classification nor gets bound. An untagged file is treated
    as a possible owner (conservative).
    """
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible(_CSHARP_LANG, owner_lang):
            return True
    return False


def resolve_csharp_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    ctx: CSharpResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one C# call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``project`` / ``stdlib`` / ``external`` / ``unknown``.
    Conservative by design: when unsure, ``unknown`` is the correct (moat-safe)
    answer — never a cross-language bind.
    """
    qualifier, simple = _split_qualifier(callee_full, callee_name)
    is_unqualified = qualifier == ""
    is_self_receiver = qualifier in _SELF_RECEIVERS

    # 1. System.* qualifier — fully-qualified BCL namespace. This wins first:
    #    the qualifier is unambiguous evidence and never a project binding (user
    #    code never owns ``namespace System``).
    if is_system_qualifier(qualifier):
        return None, "stdlib", ""

    # 2. local — resolved in the caller's OWN file. An UNQUALIFIED call may bind
    #    any local symbol (method / free function / class). An explicit SELF
    #    receiver (``this.`` / ``base.``) asserts the target is a member, so it
    #    may bind ONLY a same-file ``method`` — never a class or free function.
    if is_unqualified or is_self_receiver:
        kinds = _LOCAL_KINDS if is_unqualified else _MEMBER_KINDS
        sym_id = _lookup_in_file(ctx, caller_file, simple, kinds)
        if sym_id is not None:
            return sym_id, "local", caller_file

    # 3. project (single-global) — exactly one same-language project-wide
    #    definition of an UNQUALIFIED name. THE MOAT: gate every candidate by
    #    language compatibility so a foreign-language same-name symbol is never
    #    bound; if the sole candidate is foreign, fall through to unknown. An
    #    explicit SELF receiver is EXCLUDED here: a ``this.`` member call can
    #    never reach a cross-file global, so binding one would be a false edge.
    if is_unqualified:
        compatible = [
            (target_file, sym_id)
            for target_file, sym_id in ctx.global_name_table.get(simple, [])
            if languages_compatible(
                _CSHARP_LANG, ctx.file_languages.get(target_file, "")
            )
        ]
        if len(compatible) == 1:
            target_file, sym_id = compatible[0]
            return sym_id, "project", target_file

    # 4. BCL static-type qualifier tier — a bare static-type-qualified call
    #    (``Console.WriteLine``, ``Math.Max``) whose qualifier head is a
    #    near-exclusive BCL static type AND the project does not itself define a
    #    compatible-language symbol of that name (shadowing preserved). The head,
    #    not the tail, is the type (``Console`` in ``Console.WriteLine``).
    if not is_unqualified and not is_self_receiver:
        head = qualifier.split(".", 1)[0]
        if head in BCL_STATIC_TYPES_CSHARP and not _project_owns(ctx, head):
            return None, "stdlib", ""

    # 5. stdlib / external METHOD tiers — empty for this PR, but wired so a
    #    future safe set classifies only when the project owns no
    #    compatible-language symbol of that name (preserves shadowing).
    if simple in STDLIB_METHODS_CSHARP and not _project_owns(ctx, simple):
        return None, "stdlib", ""
    if simple in EXTERNAL_METHODS_CSHARP and not _project_owns(ctx, simple):
        return None, "external", ""

    # 6. unknown — instance-receiver calls, non-System / non-BCL qualified calls,
    #    and ambiguous unqualified names. ``unknown`` is correct: never a mis-wire.
    return None, "unknown", ""


register_language("csharp", build_csharp_context, resolve_csharp_callee)


__all__ = [
    "CSharpResolverContext",
    "build_csharp_context",
    "resolve_csharp_callee",
]
