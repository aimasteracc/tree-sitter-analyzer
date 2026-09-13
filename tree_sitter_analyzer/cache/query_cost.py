"""RFC-0027 L6.2 — declare what an expensive route will cost.

A budget-bound agent chooses between routes, so the cost must be stated in
terms the caller can act on rather than discovered by hitting a timeout.

``estimated_ms`` is derived from *observations*.  No observation source exists
yet (the L9 calibration ledger is unimplemented), so it is ``None`` — which is
the contract, not a placeholder: the RFC forbids a hardcoded guess, and a
number invented here would be indistinguishable from a measured one.

``tier`` is derived from state this process can actually observe:

* ``index_build`` — the on-disk index holds no rows, so a route that reads it
  will have to build one first.
* ``cached`` / ``cold`` — for an answer-cacheable route, whether this exact
  call is already answerable from the cache.  This is the distinction the L5
  baseline measures: ``edit action=safe`` computed in 3453 ms and then served
  in 51-69 ms, so a cache miss is the expensive call and a hit is not.
* ``warm`` — anything else: the index exists and no cache answers this call.

``cold`` is therefore only claimed where a cache miss proves the route has not
been answered for this generation.  Routes without an answer cache get ``warm``,
never a guessed ``cold``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .answer_cache import get_answer_cache
from .answer_cache_policy import build_answer_key, is_cacheable

Tier = Literal["cached", "warm", "cold", "index_build"]


@dataclass(frozen=True)
class QueryCost:
    """The declared cost of one route, as reported to the caller."""

    tier: Tier
    estimated_ms: int | None
    requires_index_build: bool
    cheaper_alternative: str | None


@dataclass(frozen=True)
class _Route:
    """Static facts about an expensive route that no runtime probe can supply."""

    #: Whether the route reads the AST index.  ``edit action=safe`` does not:
    #: the L5 baseline computed it in 3453 ms with ``ast_index_before.status``
    #: ABSENT, so a missing index is not a cost for it.
    reads_index: bool
    cheaper_alternative: str | None


#: Routes whose cost a caller must be able to see before committing.
#:
#: Membership is evidence-based rather than a ranking of everything slow.
#: RFC-0027's dogfood table names ``edit action=safe`` (seconds on the path
#: taken before every edit) and ``nav action=callers`` (a 24.8 s -> 16 ms
#: cold/warm cliff).  ``health action=project`` measured 202 s on a
#: 268-package TypeScript monorepo, past the 60 s per-call default most MCP
#: clients apply, so it is the third.  ``structure action=outline`` is
#: deliberately absent: the answer-cache policy records it at 2.9 ms warm,
#: where a declaration would be noise.
EXPENSIVE_ROUTES: dict[tuple[str, str], _Route] = {
    ("nav", "callers"): _Route(
        reads_index=True,
        cheaper_alternative="nav action=context (1-hop, warm)",
    ),
    ("edit", "safe"): _Route(reads_index=False, cheaper_alternative=None),
    ("health", "project"): _Route(
        reads_index=True,
        cheaper_alternative="health action=file (one file, warm)",
    ),
}


def _index_holds_rows(project_root: str | None) -> bool:
    """Whether the on-disk index holds rows.

    The same definition ``CodeGraphAutoIndexTool`` reports as ``indexed``: the
    in-memory guard marker says only that *this* process warmed something, and
    a fresh process facing a fully built cache must not read that as absent.
    """
    if not project_root:
        return False
    try:
        from ..ast_cache import ASTCache

        cache = ASTCache(project_root)
        try:
            stats = cache.get_stats()
        finally:
            cache.close()
    except Exception:
        return False
    return bool(stats and stats.get("total_files", 0) > 0)


def query_cost(
    tool: str,
    action: str,
    project_root: str | None,
    arguments: dict[str, Any] | None = None,
) -> QueryCost | None:
    """Return the declared cost for ``(tool, action)``, or ``None`` if unlisted.

    ``None`` means "this route makes no claim", which is different from a
    declared cost with unknown timing.  Only routes in :data:`EXPENSIVE_ROUTES`
    answer, so an ordinary route pays nothing to be asked.
    """
    route = EXPENSIVE_ROUTES.get((tool, action))
    if route is None:
        return None

    if route.reads_index and not _index_holds_rows(project_root):
        return QueryCost(
            tier="index_build",
            estimated_ms=None,
            requires_index_build=True,
            cheaper_alternative=route.cheaper_alternative,
        )

    tier: Tier = "warm"
    if is_cacheable(tool, action):
        key = build_answer_key(tool, action, arguments or {}, project_root)
        if key is not None:
            tier = "cached" if get_answer_cache().lookup(key) is not None else "cold"

    return QueryCost(
        tier=tier,
        estimated_ms=None,
        requires_index_build=False,
        cheaper_alternative=route.cheaper_alternative,
    )


def cost_fields(cost: QueryCost | None) -> dict[str, Any]:
    """Render a cost declaration for a response envelope.

    Absent by default: a route that declares no cost omits the key entirely
    rather than emitting ``null``, so an envelope never gains a field that
    carries no information.
    """
    if cost is None:
        return {}
    return {
        "query_cost": {
            "tier": cost.tier,
            "estimated_ms": cost.estimated_ms,
            "requires_index_build": cost.requires_index_build,
            "cheaper_alternative": cost.cheaper_alternative,
        }
    }
