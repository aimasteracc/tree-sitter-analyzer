r"""PHP callee resolver (RFC-0010, second wave).

Self-contained and SAFE. It REPLACES the Python cascade for PHP callers
(``file_languages == "php"``) without regressing: it resolves SAME-FILE/
SAME-LANGUAGE local calls, classifies a curated set of global built-in free
functions as ``builtin``, and returns ``unknown`` for everything else.

PHP call shapes and how each is handled:

* **bare ``foo()``** (no receiver) — a free-function call. Resolved ``local`` to
  a same-file ``function``/``class`` definition first; else, if ``foo`` is a
  curated global built-in NOT shadowed by a project free function, ``builtin``;
  else ``unknown``. A namespaced free call (``\App\foo`` / ``App\foo``) is
  treated as bare on its LAST segment.
* **``$this->m()`` / ``self::m()`` / ``static::m()`` / ``parent::m()``** — a
  method call on the current object/class. Bound ``local`` ONLY when exactly one
  class in the caller file defines ``m`` (the caller's enclosing class is not
  carried by the edge, so an ambiguous name across two classes stays
  ``unknown`` — never the file-wide first match, the wave-1 Codex P2 lesson).
* **``Foo::m()`` (static) / ``$obj->m()`` (instance)** — a receiver call whose
  class type the edge does not carry. Never guessed → ``unknown``.

THE MOAT — never cross-language bind. The resolver only ever consults the
CALLER file's own ``file_symbols`` / ``file_class_methods`` for a ``local``
match and never looks up a symbol in another file, so a same-named symbol in a
different language's file can never be bound. Built-in classification produces
no symbol/file at all. PHP has no interop family (``languages_compatible`` is
True only for the identical tag), so even the ownership/shadow gate is
same-language by construction.

Conservative tiers only (the RFC-0008 lesson): the bare built-in set is a small
hand-audited list of global functions a project almost never shadows; the
external tier is EMPTY. Receiver-qualified method names stay ``unknown``.

Contract (RFC-0010): the module ends with
``register_language("php", build_php_context, resolve_php_callee)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..._language_family import languages_compatible
from .._registry import register_language
from ._php_constants import PHP_BUILTIN_FUNCTIONS

#: ``file_languages`` tag for every ``.php`` file.
_PHP_LANG = "php"

#: Receivers that mean "the current object / class" — a class-scoped method
#: call. The caller's enclosing class is NOT available to the resolver, so these
#: bind only through the unambiguous single-class gate (never the file-wide
#: first match). A BARE (empty) receiver is handled separately: a bare ``foo()``
#: is a free-function call, not a class-method call.
_SELF_RECEIVERS = frozenset({"$this", "this", "self", "static", "parent"})

#: Symbol kinds a bare ``foo()`` call can legally target: a top-level
#: ``function``. A ``class`` is a construction (``new Foo()``), not a plain
#: call, and a ``method`` needs an owning receiver — matching either here would
#: bind a bare ``render()`` to a sibling class's method (a concrete wrong edge).
_BARE_CALLABLE_KINDS = frozenset({"function"})

#: Separators that can appear between a PHP receiver and the call name in the
#: edge's full name: ``::`` (static / class-const), ``->`` (instance), ``\``
#: (namespace), and ``.`` (a normalised form some extractors emit). We split on
#: the LAST occurrence of any of these so ``App\Util::run`` -> receiver
#: ``App\Util``, name ``run`` and ``\App\helper`` -> receiver ``\App``, name
#: ``helper``.
_RECEIVER_SPLIT = re.compile(r"(?:::|->|\\|\.)")


@dataclass
class PhpResolverContext:
    """Per-index PHP resolution maps (built once per pass).

    Holds only the shared cross-language maps the resolver consults. All file
    keys are project-relative paths, matching the ``edges`` table. The resolver
    reads only the CALLER file's own entries for a ``local`` match, so carrying
    the full maps is safe.
    """

    # file -> [(name, kind, symbol_id), ...] (shared cross-language map).
    file_symbols: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    # file -> {class -> {method -> symbol_id}} (shared cross-language map).
    file_class_methods: dict[str, dict[str, dict[str, int]]] = field(
        default_factory=dict
    )
    # simple name -> [(file, symbol_id), ...] project-wide (single-global). Used
    # ONLY by the built-in shadow gate (a project free function shadows a
    # built-in of the same name); never to bind a project symbol.
    global_name_table: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    # file -> language tag (so the shadow gate stays language-aware).
    file_languages: dict[str, str] = field(default_factory=dict)


def build_php_context(
    *,
    imports_by_file: dict[str, Any],
    file_languages: dict[str, str],
    file_symbols: dict[str, Any],
    global_name_table: dict[str, Any],
    file_class_methods: Any,  # zero-arg thunk -> class->method map (lazy)
    **_ignored: Any,
) -> PhpResolverContext | None:
    """Build the PHP context, or ``None`` when no PHP file is indexed.

    Zero cost for non-PHP projects: gated on ``file_languages`` BEFORE the lazy
    ``file_class_methods`` thunk is forced, so a Python/Java-only index never
    pays to materialise the class-method map for PHP.
    """
    if not any(lang == _PHP_LANG for lang in file_languages.values()):
        return None
    fcm = file_class_methods() if callable(file_class_methods) else file_class_methods
    return PhpResolverContext(
        file_symbols=file_symbols,
        file_class_methods=fcm or {},
        global_name_table=global_name_table,
        file_languages=file_languages,
    )


def _split_receiver(callee_full: str, callee_name: str) -> tuple[str, str, str]:
    """Return ``(receiver, simple_name, separator)`` from a PHP call's full name.

    Splits on the LAST of ``::`` / ``->`` / ``\\`` / ``.``; ``separator`` is the
    matched text of that LAST split (``""`` for a bare name), which tells the
    resolver the call SHAPE — a ``\\``-terminated split is a namespace-qualified
    FREE function, whereas ``::``/``->`` is a class/instance RECEIVER call:

    * ``helper``            -> ``("", "helper", "")``          (bare free fn)
    * ``\\App\\helper``      -> ``("\\App", "helper", "\\")``     (namespaced free fn)
    * ``$this->process``    -> ``("$this", "process", "->")``  (instance self-call)
    * ``self::make``        -> ``("self", "make", "::")``      (static self-call)
    * ``Foo::bar``          -> ``("Foo", "bar", "::")``        (static receiver)
    * ``App\\Util::run``     -> ``("App\\Util", "run", "::")``   (ns static receiver)
    * ``$obj->bar``         -> ``("$obj", "bar", "->")``       (instance receiver)
    """
    full = callee_full or callee_name
    matches = list(_RECEIVER_SPLIT.finditer(full))
    if matches:
        last = matches[-1]
        receiver = full[: last.start()]
        simple = full[last.end() :]
        return receiver, (simple or callee_name), last.group(0)
    return "", full or callee_name, ""


def _lookup_in_file(ctx: PhpResolverContext, file_path: str, simple: str) -> int | None:
    """Symbol id of a same-file BARE-CALLABLE named ``simple`` in ``file_path``.

    Restricted to a top-level ``function`` (see ``_BARE_CALLABLE_KINDS``): a bare
    ``foo()`` cannot legitimately target a class ``method`` (needs a receiver)
    nor a ``class`` (that is construction). Real resolver contexts populate
    ``file_symbols`` with EVERY method in the file, so matching ``method`` here
    would bind a bare call to a sibling class's method — a wrong edge.
    """
    for name, kind, sym_id in ctx.file_symbols.get(file_path, []):
        if name == simple and kind in _BARE_CALLABLE_KINDS:
            return sym_id
    return None


def _unique_class_method(
    ctx: PhpResolverContext, file_path: str, simple: str
) -> int | None:
    """Symbol id when EXACTLY ONE class in ``file_path`` defines ``simple``.

    For a ``$this``/``self``/``static``/``parent`` call the caller's enclosing
    class is not available to the resolver, so a name defined by two classes in
    the same file is ambiguous. Conservatively resolve only the unambiguous
    (single-owner) case — never the file-wide first match, which would mis-bind
    ``B.bar -> A.foo`` (wave-1 Codex P2 lesson)."""
    found: int | None = None
    for methods in ctx.file_class_methods.get(file_path, {}).values():
        mid = methods.get(simple)
        if mid is None:
            continue
        if found is not None and found != mid:
            return None  # defined by >1 class — ambiguous, stay unknown.
        found = mid
    return found


def _project_owns_function(ctx: PhpResolverContext, simple: str) -> bool:
    """True when a SAME-LANGUAGE (PHP) project symbol named ``simple`` exists.

    The shadow gate for the built-in tier: if the project itself defines a free
    function (or any symbol) named like a built-in, the ``builtin``
    classification must NOT claim it. The gate is LANGUAGE-AWARE — a same-named
    symbol in another language's file (a Python ``count``) does NOT count,
    because ``languages_compatible("php", "python")`` is False (PHP has no
    interop family). Unknown-language owner files are treated as possible owners
    (conservative)."""
    for owner_file, _sym_id in ctx.global_name_table.get(simple, []):
        owner_lang = ctx.file_languages.get(owner_file, "")
        if not owner_lang or languages_compatible(_PHP_LANG, owner_lang):
            return True
    return False


def resolve_php_callee(
    callee_name: str,
    callee_full: str,
    caller_file: str,
    lang_ctx: PhpResolverContext,
) -> tuple[int | None, str, str]:
    """Resolve one PHP call edge.

    Returns ``(symbol_id, resolution, resolved_file)`` where ``resolution`` is
    one of ``local`` / ``builtin`` / ``unknown``. Conservative by construction:
    anything not provably a same-file local call or a curated built-in is
    ``unknown`` — never a cross-language bind.
    """
    ctx = lang_ctx
    receiver, simple, separator = _split_receiver(callee_full, callee_name)

    # 1. local — a bare free-function call. This is either a truly bare name
    #    (no separator) OR a namespace-qualified free call whose LAST separator
    #    is ``\`` (``\App\helper`` / ``App\helper``): a namespace path is NOT a
    #    class/instance receiver, so the call targets a top-level free function.
    #    A ``::``/``->`` split is a RECEIVER call and is intentionally excluded
    #    here (even when the receiver text contains a ``\`` namespace, e.g.
    #    ``App\Util::run``). The file-wide symbol lookup is safe because a bare
    #    call can only target a top-level ``function`` (``_BARE_CALLABLE_KINDS``).
    if separator in ("", "\\"):
        sym_id = _lookup_in_file(ctx, caller_file, simple)
        if sym_id is not None:
            return sym_id, "local", caller_file
        # 2. builtin — a bare global built-in free function the project does not
        #    itself define (shadowing preserved). No project-wide single-name
        #    bind: that is exactly where cross-file / cross-language mis-wires
        #    creep in, so an unresolved bare name that is not a curated built-in
        #    stays ``unknown``.
        if simple in PHP_BUILTIN_FUNCTIONS and not _project_owns_function(ctx, simple):
            return None, "builtin", ""
        return None, "unknown", ""

    # 1b. local — ``$this``/``self``/``static``/``parent`` method call: class-
    #     scoped. Resolve ONLY when exactly one class in the file defines the
    #     method (the caller's enclosing class is not carried by the edge). An
    #     ambiguous name (two classes) or a top-level function stays ``unknown``.
    if receiver in _SELF_RECEIVERS:
        mid = _unique_class_method(ctx, caller_file, simple)
        if mid is not None:
            return mid, "local", caller_file
        return None, "unknown", ""

    # 3. unknown — a ``Foo::bar`` static or ``$obj->bar`` instance call whose
    #    class type the edge does not carry. Never guessed: classifying these by
    #    bare method name would mis-wire domain calls (the CodeGraph failure this
    #    project beats).
    return None, "unknown", ""


register_language(_PHP_LANG, build_php_context, resolve_php_callee)


__all__ = [
    "PhpResolverContext",
    "build_php_context",
    "resolve_php_callee",
]
