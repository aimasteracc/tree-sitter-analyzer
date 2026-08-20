#!/usr/bin/env python3
"""Generation-keyed answer cache (RFC-0027 L6.1).

Why this exists
---------------
``edit action=safe`` is the one call an agent makes before **every** edit, and
it was the only route in ``docs/baselines/rfc0025-l5-latency-windows-e0.json``
that stayed in *seconds* once warm (3.3-3.8 s p95). A profile of a warm call
shows why: it re-reads every source file in the repository on each invocation
(5,799 ``Path.read_text`` calls, ~2.0 s of the 3.7 s) to find importers, test
references and fixture evidence. None of that work depends on anything but the
source tree, so the answer is memoizable with a sound key.

The primary user is an AI coding agent, and an agent silently routes around a
slow tool — adoption failure is invisible. That is what makes this a
correctness-shaped problem rather than an optimisation: a cache that lies about
freshness is **worse than no cache**, because the agent has no way to tell.

Soundness fences (all fail-closed, RFC-0027 L6.1)
------------------------------------------------
1. Read-only actions only — see :mod:`.answer_cache_policy`.
2. Only certified answers are stored (:func:`is_certified`).
3. Whole-cache eviction on any key-component bump. There is no partial
   invalidation: proving which answers a file change can affect is exactly the
   unresolved-edge problem and cannot be proved sound.
4. Bounded by ``ANSWER_CACHE_BUDGET_MB`` (default 128 MiB), LRU eviction.
5. A cache hit is visible: ``provenance.served_from`` is exactly ``"cache"`` or
   ``"computed"``, carrying every key component.

Scope
-----
**Process-local and in-memory. Persistence is deliberately out of scope** (see
RFC-0027 open question 1): a persisted cache needs file locking, rotation and
corruption handling, which is its own change. The MCP server is a long-lived
process, so process-local already captures the case the primary user lives in.
Nothing here forecloses persistence — :class:`AnswerKey` is a frozen dataclass
of plain strings (directly serialisable) and the store is reachable only
through :func:`get_answer_cache`.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, fields
from typing import Any

from ..task.freshness import FRESHNESS_STATES

#: Bumped whenever the *shape* of a cached payload or the key derivation
#: changes. Folded into ``producer_version`` so a bump misses every entry.
ANSWER_CACHE_SCHEMA_VERSION = "answer-cache/v1"

#: Default budget, mirroring the RFC-0022 P0.1 registry's boundedness style.
DEFAULT_BUDGET_MB = 128

#: Separator between the global and route halves of ``producer_version``.
_ROUTE_VERSION_TAG = "pvr1"

#: The ONLY freshness values that may be cached. ``fresh`` is self-explanatory;
#: ``not_applicable`` is cacheable because it means no graph evidence was used,
#: so there is nothing that could have gone stale.
CERTIFIED_FRESHNESS: frozenset[str] = frozenset({"fresh", "not_applicable"})

#: Everything else in RFC-0022's closed ``FRESHNESS_STATES`` domain. **Derived,
#: never hand-listed**: this function's failure mode is a *permanent* lie, so a
#: sixth freshness state must default to "refuse", not to "cacheable". A
#: hand-written denylist would silently admit it.
NON_CERTIFIED_FRESHNESS: frozenset[str] = frozenset(
    FRESHNESS_STATES - CERTIFIED_FRESHNESS
)

#: RFC-0022 P0.4 ``access_state`` values that mean capability access was NOT
#: certified. The same soundness rule as ``freshness`` applies in the capability
#: dimension: ``edit action=safe`` with ``access_mode=read_existing`` returns
#: ``access_state="unknown"`` / ``READ_EXISTING_AUTHORITY_UNCERTIFIED`` on any
#: platform where the source oracle cannot run, and replaying *that* from cache
#: would turn a one-off "I could not certify this" into a persistent verdict.
NON_CERTIFIED_ACCESS_STATE: frozenset[str] = frozenset({"stale", "missing", "unknown"})

_ENV_BUDGET_MB = "ANSWER_CACHE_BUDGET_MB"


@dataclass(frozen=True)
class AnswerKey:
    """Sound cache key for a certified answer.

    ``generation`` is the source-tree state the answer was derived from. Two
    calls with equal keys are guaranteed to have equal answers because the
    listed components are the only inputs that can change the result.

    The key deliberately has **three** independent components beyond the args.
    ``generation`` alone is not sufficient: the same source tree produces a
    different answer after a TSA upgrade, an ``action_version`` bump, a
    resolver-rule change, or an edit to ``architectural-constraints.yml``. A
    key omitting those would replay the previous release's verdict under a new
    schema.
    """

    tool: str
    action: str
    #: Canonical JSON, keys sorted, project-relative paths.
    normalized_args: str
    #: Source-tree state, project-root-scoped.
    generation: str
    #: action_version + schema version + resolver-rule digest.
    producer_version: str
    #: Digest of declared non-source inputs (config, constraints).
    extra_inputs: str

    @property
    def global_producer_version(self) -> str:
        """The route-INDEPENDENT half of :attr:`producer_version`.

        ``producer_version`` is encoded ``"<global>:pvr1:<route>"``. Only the
        global half may participate in :attr:`prelude`: when the route half was
        included, the two allowlisted routes evicted each other on every switch
        and the cache hit rate was 0% in the prescribed interleaved workflow.
        """
        return self.producer_version.split(f":{_ROUTE_VERSION_TAG}:", 1)[0]

    @property
    def prelude(self) -> tuple[str, str, str]:
        """The components whose bump evicts the **whole** cache.

        Strictly global: a route-scoped component here would make one route's
        arrival wipe every other route's entries. Route identity is already
        carried by :attr:`tool` / :attr:`action` / the route half of
        :attr:`producer_version`, so it still affects *this* entry's identity
        without evicting anyone else's.
        """
        return (self.generation, self.global_producer_version, self.extra_inputs)


@dataclass(frozen=True)
class CachedAnswer:
    """A stored answer plus the key it was certified under."""

    key: AnswerKey
    payload: dict[str, Any]
    size_bytes: int


def is_certified(payload: Any) -> bool:
    """Return whether ``payload`` may be stored (RFC-0027 L6.1 rule 2).

    Fail-closed: anything not positively recognised as a successful, non-error,
    non-stale answer is refused. Storing a ``stale`` / ``missing`` / ``unknown``
    answer would let the cache outlive the reason the answer was uncertain.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is not True:
        return False
    if payload.get("verdict") == "ERROR":
        return False
    for freshness in (payload.get("freshness"), _nested_freshness(payload)):
        if isinstance(freshness, str) and freshness in NON_CERTIFIED_FRESHNESS:
            return False
    access_state = payload.get("access_state")
    if isinstance(access_state, str) and access_state in NON_CERTIFIED_ACCESS_STATE:
        return False
    return True


def _nested_freshness(payload: dict[str, Any]) -> Any:
    provenance = payload.get("provenance")
    return provenance.get("freshness") if isinstance(provenance, dict) else None


def _payload_size_bytes(payload: dict[str, Any]) -> int:
    """Approximate the retained size of ``payload``.

    Serialised length is a cheap, stable proxy: it is what the MCP wire pays
    for, and it never under-counts a large nested payload the way
    ``sys.getsizeof`` on the outer dict would.
    """
    try:
        return len(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        return len(repr(payload))


def _budget_bytes_from_env() -> int:
    """Read ``ANSWER_CACHE_BUDGET_MB``, falling back to the default.

    An unparseable or negative value falls back rather than raising: a bad env
    var must not take the MCP server down, and the fallback is the conservative
    documented default.
    """
    raw = os.environ.get(_ENV_BUDGET_MB)
    if raw is None:
        return DEFAULT_BUDGET_MB * 1024 * 1024
    try:
        megabytes = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_BUDGET_MB * 1024 * 1024
    if megabytes < 0:
        return DEFAULT_BUDGET_MB * 1024 * 1024
    return megabytes * 1024 * 1024


class AnswerCache:
    """Bounded, LRU, generation-keyed store for certified answers.

    Thread-safe: the MCP server dispatches concurrently, and an interleaved
    ``store`` during a whole-cache eviction would otherwise leave entries from
    two different generations in the map at once.
    """

    def __init__(self, budget_bytes: int | None = None) -> None:
        self._budget_bytes = (
            _budget_bytes_from_env() if budget_bytes is None else budget_bytes
        )
        self._entries: OrderedDict[AnswerKey, CachedAnswer] = OrderedDict()
        self._total_bytes = 0
        self._prelude: tuple[str, str, str] | None = None
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._whole_cache_evictions = 0
        self._lock = threading.RLock()

    # -- introspection -----------------------------------------------------

    @property
    def budget_bytes(self) -> int:
        return self._budget_bytes

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def evictions(self) -> int:
        return self._evictions

    @property
    def whole_cache_evictions(self) -> int:
        return self._whole_cache_evictions

    # -- core --------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0
            self._prelude = None

    def lookup(self, key: AnswerKey) -> CachedAnswer | None:
        """Return a cached answer, or ``None``.

        A cached answer is returned ONLY when every key component — including
        the live ``generation`` at call time — matches. A prelude bump evicts
        the whole cache before the miss is reported, so a stale generation can
        never be served, not even to a different question.
        """
        with self._lock:
            self._reconcile_prelude(key)
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return CachedAnswer(
                key=entry.key,
                payload=copy.deepcopy(entry.payload),
                size_bytes=entry.size_bytes,
            )

    def store(self, key: AnswerKey, payload: Any) -> bool:
        """Store ``payload`` under ``key``; return whether it was stored.

        Returns ``False`` — never raises — when the answer is not certified, or
        when it alone exceeds the whole budget. A refusal is a normal outcome
        the caller does not need to handle.
        """
        if not is_certified(payload):
            return False
        size = _payload_size_bytes(payload)
        with self._lock:
            if size > self._budget_bytes:
                return False
            self._reconcile_prelude(key)
            existing = self._entries.pop(key, None)
            if existing is not None:
                self._total_bytes -= existing.size_bytes
            self._entries[key] = CachedAnswer(
                key=key, payload=copy.deepcopy(payload), size_bytes=size
            )
            self._total_bytes += size
            self._evict_to_budget()
            return True

    # -- internals ---------------------------------------------------------

    def _reconcile_prelude(self, key: AnswerKey) -> None:
        """Rule 3: any key-component bump evicts the whole cache.

        Caller must hold ``self._lock``.
        """
        prelude = key.prelude
        if self._prelude is None:
            self._prelude = prelude
            return
        if self._prelude == prelude:
            return
        self._entries.clear()
        self._total_bytes = 0
        self._prelude = prelude
        self._whole_cache_evictions += 1

    def _evict_to_budget(self) -> None:
        """Rule 4: drop least-recently-used entries until inside the budget.

        Caller must hold ``self._lock``.
        """
        while self._entries and self._total_bytes > self._budget_bytes:
            _, victim = self._entries.popitem(last=False)
            self._total_bytes -= victim.size_bytes
            self._evictions += 1


_CACHE: AnswerCache | None = None
_CACHE_LOCK = threading.Lock()


def get_answer_cache() -> AnswerCache:
    """Return the process-local answer cache."""
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = AnswerCache()
        return _CACHE


def reset_answer_cache() -> None:
    """Drop the process-local cache (test isolation; re-reads the budget env)."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None


__all__ = [
    "ANSWER_CACHE_SCHEMA_VERSION",
    "CERTIFIED_FRESHNESS",
    "DEFAULT_BUDGET_MB",
    "NON_CERTIFIED_ACCESS_STATE",
    "NON_CERTIFIED_FRESHNESS",
    "AnswerCache",
    "AnswerKey",
    "CachedAnswer",
    "get_answer_cache",
    "is_certified",
    "reset_answer_cache",
]

# Keep the RFC-pinned component count honest at import time rather than only in
# a test: a field silently added or dropped changes the soundness argument.
# A bare ``assert`` would be stripped under ``python -O`` — i.e. it would vanish
# in exactly the deployment that strips asserts — so this raises explicitly.
if len(fields(AnswerKey)) != 6:  # pragma: no cover - import-time invariant
    raise RuntimeError(
        f"AnswerKey must carry exactly six components, found {len(fields(AnswerKey))}"
    )
