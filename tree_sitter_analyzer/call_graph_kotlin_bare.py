"""#1926: bind a Kotlin bare call ``m()`` (and ``this.m()``) by its implicit receivers.

A bare call to a member inside a Kotlin class means ``this.m()``: the enclosing
class's own ``m`` is the static target and every subclass override is a possible
one. Before #1926 only Java read a bare call as ``this``, so an override reached
only through ``make()`` in its base class answered ``complete`` with 0 callers.

The extractor records which implicit receivers the call may use
(:mod:`.kotlin_call_scope`). The rule:

* **open site** -- an enclosing lambda / anonymous function / extension may bring a
  receiver, a lambda is passed to a function the project defines (it may take
  ``T.() -> R``; for ``apply { }`` / ``run { }`` on the implicit ``this`` only a
  receiver-less function or a method of the caller's class or a supertype
  counts), or the index predates #1926 (no scope recorded): ``m()`` may be
  any type's method. Nothing is certain; every project method named ``m`` and the
  static candidates are possible targets. When the project has no method ``m`` the
  binding is unchanged (only functions can answer).
* **top-level code** -- no implicit receiver: unchanged.
* **class member** -- the caller's class declares exactly one ``m`` in its file and
  that file has no function ``m`` without a receiver (local, top-level): that
  method is certain, the subclass overrides possible. Otherwise the site is open
  (an inherited, outer-class or companion member, or a shadowing function).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .kotlin_call_scope import KOTLIN_SCOPE_KEY, MEMBER, THIS_HOST_PREFIX, TOP

if TYPE_CHECKING:
    from .call_graph import FunctionRef

_KOTLIN_SUFFIXES = (".kt", ".kts")
#: Receivers that make a call a "bare" Kotlin call for this rule.
_BARE_QUALIFIERS = frozenset({"", "this"})


@dataclass(frozen=True)
class KotlinSite:
    """The recorded implicit-receiver scope of one bare / ``this`` call."""

    #: ``member`` / ``top`` / ``receiver``; None when the index has no scope.
    scope: str | None
    #: Functions the enclosing lambdas are passed to (no receiver in the stdlib).
    hosts: tuple[str, ...] = ()


class _Resolver(Protocol):
    def _own_method(
        self, caller_file: str, caller_class: str, base_name: str
    ) -> FunctionRef | None: ...

    def _with_overrides(
        self,
        certain: list[FunctionRef],
        possible: list[FunctionRef],
        base_name: str,
        qualifier: str,
        caller_class: str,
    ) -> list[FunctionRef]: ...


def kotlin_site(
    edge: dict[str, Any], qualifier: str, caller_file: str
) -> KotlinSite | None:
    """The site of a Kotlin bare / ``this`` call; None for anything else."""
    if qualifier not in _BARE_QUALIFIERS:
        return None
    if edge.get("language") != "kotlin" and not caller_file.endswith(_KOTLIN_SUFFIXES):
        return None
    raw = edge.get(KOTLIN_SCOPE_KEY)
    if not isinstance(raw, str) or not raw:
        return KotlinSite(None)
    scope, _, hosts = raw.partition(":")
    return KotlinSite(scope, tuple(host for host in hosts.split(",") if host))


def kotlin_targets(
    resolver: _Resolver,
    functions_by_name: dict[str, list[FunctionRef]],
    static: list[FunctionRef],
    site: KotlinSite,
    base_name: str,
    qualifier: str,
    caller_class: str | None,
    caller_file: str,
) -> tuple[list[FunctionRef], list[FunctionRef]] | None:
    """``(certain, possible)`` for the site; None keeps the static binding."""
    if not _open(site, functions_by_name, caller_class, resolver):
        if site.scope == TOP:
            return None
        own = (
            resolver._own_method(caller_file, caller_class, base_name)
            if caller_class
            else None
        )
        if own is not None and not (
            not qualifier and _shadowed(functions_by_name, base_name, caller_file)
        ):
            assert caller_class is not None
            rest = [ref for ref in static if ref != own]
            return [own], resolver._with_overrides(
                [own], rest, base_name, "this", caller_class
            )
    named = functions_by_name.get(base_name, [])
    if not any(ref.receiver for ref in named):
        return None
    possible = list(static)
    present = set(possible)
    # Every definition: an extension (no receiver in the index) is reachable from a
    # receiver lambda as well.
    for ref in named:
        if ref not in present:
            present.add(ref)
            possible.append(ref)
    return [], possible


def _open(
    site: KotlinSite,
    functions_by_name: dict[str, list[FunctionRef]],
    caller_class: str | None,
    resolver: Any,
) -> bool:
    if site.scope not in (MEMBER, TOP):
        return True  # ``receiver``, or no scope recorded (index before #1926)
    for host in site.hosts:
        if host.startswith(THIS_HOST_PREFIX):
            if _replaces_this_host(
                functions_by_name, host[len(THIS_HOST_PREFIX) :], caller_class, resolver
            ):
                return True
        elif functions_by_name.get(host):
            return True  # the project's own ``host`` may take ``T.() -> R``
    return False


def _replaces_this_host(
    functions_by_name: dict[str, list[FunctionRef]],
    host: str,
    caller_class: str | None,
    resolver: Any,
) -> bool:
    """A project definition may replace the standard ``apply`` / ``run`` that is
    called on the implicit ``this``: a function without a receiver (an imported
    extension), or a method of the caller's class or one of its supertypes (any
    method when the caller's class is unknown)."""
    refs = functions_by_name.get(host, [])
    if any(not ref.receiver for ref in refs):
        return True
    methods = {ref.receiver for ref in refs}
    if not methods:
        return False
    if not caller_class:
        return True
    subclasses = getattr(resolver, "_subclasses", None)
    ancestors = subclasses.ancestors(caller_class) if subclasses is not None else None
    return bool(methods & {caller_class, *(ancestors or ())})


def _shadowed(
    functions_by_name: dict[str, list[FunctionRef]], base_name: str, caller_file: str
) -> bool:
    """A function ``base_name`` without a receiver in the caller's file.

    A local function outranks the member for the bare name. A top-level or
    extension function does not in Kotlin's resolution order, but one in the same
    file is treated as open too (the index cannot tell local from top-level by
    name alone). Functions in other files cannot shadow the member.
    """
    return any(
        not ref.receiver and ref.file_path == caller_file
        for ref in functions_by_name.get(base_name, [])
    )


__all__ = ["KotlinSite", "kotlin_site", "kotlin_targets"]
