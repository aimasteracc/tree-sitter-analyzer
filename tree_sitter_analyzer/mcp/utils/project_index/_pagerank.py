"""
PageRank helpers for project_index.

Provides pure-Python power-iteration PageRank over the call graph extracted
from source files. No external dependencies.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ._models import _PAGERANK_STDLIB_BLOCKLIST

logger = logging.getLogger(__name__)


def compute_pagerank(
    edges: list[tuple[str, str]],
    top_n: int = 10,
    alpha: float = 0.85,
    max_iter: int = 100,
) -> list[dict[str, Any]]:
    """Compute PageRank on the call graph and return top_n nodes.

    Pure-Python power iteration — no external dependencies.
    Returns [] gracefully if the edge list is empty.

    Each returned dict has: name, pagerank (float), inbound_refs (int).

    r37ee (dogfood): 78 lines → ~20 of dispatch. ``_pagerank_build_graph``
    builds the adjacency lists; ``_pagerank_iterate`` runs the power
    iteration to convergence; ``_pagerank_top_n_rows`` filters and
    formats the top-``top_n`` result rows.
    """
    if not edges:
        return []

    try:
        out_edges, inbound, node_list = _pagerank_build_graph(edges)
        if not node_list:
            return []
        scores = _pagerank_iterate(out_edges, node_list, alpha, max_iter)
        return _pagerank_top_n_rows(scores, inbound, top_n)
    except Exception as exc:  # noqa: BLE001
        logger.debug("PageRank computation failed: %s", exc)
        return []


def _pagerank_build_graph(
    edges: list[tuple[str, str]],
) -> tuple[dict[str, set[str]], dict[str, int], list[str]]:
    """Build the adjacency lists used by ``compute_pagerank``.

    Returns ``(out_edges, inbound, sorted_nodes)`` where ``out_edges`` maps
    a source node to its set of destinations, ``inbound`` maps a
    destination node to its in-degree, and ``sorted_nodes`` is the
    deterministic order used as the iteration basis.
    """
    out_edges: dict[str, set[str]] = {}
    inbound: dict[str, int] = {}
    nodes: set[str] = set()
    for src, dst in edges:
        nodes.add(src)
        nodes.add(dst)
        out_edges.setdefault(src, set()).add(dst)
        inbound[dst] = inbound.get(dst, 0) + 1
    return out_edges, inbound, sorted(nodes)


def _pagerank_iterate(
    out_edges: dict[str, set[str]],
    node_list: list[str],
    alpha: float,
    max_iter: int,
) -> dict[str, float]:
    """Run power iteration until convergence (or ``max_iter``).

    r37e3 (dogfood): inner power-iteration step lifted to ``_pagerank_step``
    so the outer loop stays at ≤3 nesting; this function now only owns
    the convergence-detection bookkeeping.
    """
    n = len(node_list)
    scores: dict[str, float] = dict.fromkeys(node_list, 1.0 / n)
    dangling = {nd for nd in node_list if nd not in out_edges}
    for _ in range(max_iter):
        new_scores = _pagerank_step(scores, node_list, out_edges, dangling, alpha, n)
        err = sum(abs(new_scores[nd] - scores[nd]) for nd in node_list)
        scores = new_scores
        if err < 1.0e-6 * n:
            break
    return scores


def _pagerank_step(
    scores: dict[str, float],
    node_list: list[str],
    out_edges: dict[str, Any],
    dangling: set[str],
    alpha: float,
    n: int,
) -> dict[str, float]:
    """Run one power-iteration step of PageRank.

    Returns the next ``new_scores`` dict. Dangling nodes distribute
    their probability uniformly across all nodes (PageRank random-
    teleportation handling). Edge contributions are added on top of
    the base ``(1 - alpha) / n + dangling_sum`` floor.

    r37e3 (dogfood): lifted from ``_compute_pagerank`` so the outer
    max_iter loop stays at depth 3 instead of 6.
    """
    new_scores: dict[str, float] = {}
    dangling_sum = alpha * sum(scores[nd] for nd in dangling) / n
    base = (1.0 - alpha) / n + dangling_sum
    for nd in node_list:
        new_scores[nd] = base
    for src, dsts in out_edges.items():
        contrib = alpha * scores[src] / len(dsts)
        for dst in dsts:
            new_scores[dst] = new_scores.get(dst, 0.0) + contrib
    return new_scores


def _pagerank_top_n_rows(
    scores: dict[str, float],
    inbound: dict[str, int],
    top_n: int,
) -> list[dict[str, Any]]:
    """Filter stdlib blocklist + take ``top_n`` highest-score rows.

    Filter Python stdlib / typing helpers that look like classes
    in the edge extraction but are not real architectural nodes.
    ``TYPE_CHECKING`` is the worst offender — it surfaces as a
    high-degree node because every type-annotated module imports
    it, but renaming it is meaningless. ``Any``, ``Optional``,
    ``ClassVar`` etc. land in the same bucket.

    The returned rows include ``rank`` (1-based, matches the
    ``architecture_rank`` field on the modification_guard summary
    line) and ``symbol`` (alias for ``name``).
    """
    filtered = [
        (name, score)
        for name, score in sorted(scores.items(), key=lambda kv: -kv[1])
        if name not in _PAGERANK_STDLIB_BLOCKLIST
    ]
    top = filtered[:top_n]
    return [
        {
            "rank": idx,
            "name": name,
            "symbol": name,
            "pagerank": round(score, 4),
            "inbound_refs": inbound.get(name, 0),
        }
        for idx, (name, score) in enumerate(top, 1)
    ]


def collect_critical_nodes(
    all_files: list[str],
    extract_edges_fn: Any,
) -> list[dict[str, Any]]:
    """Run PageRank over the call graph; skip test paths.

    Test base classes (``ESTestCase`` etc.) inflate inbound refs without
    signalling architecture, so files under ``/test/`` / ``/tests/`` /
    ``/testFixtures/`` / ``/testing/`` are excluded from edge extraction.

    Args:
        all_files: list of absolute file paths to analyse.
        extract_edges_fn: callable(Path) -> list[tuple[str, str]] — the
            per-file edge extractor (provided by ProjectIndexManager).
    """
    test_path_markers = {"/test/", "/tests/", "/testFixtures/", "/testing/"}
    edges: list[tuple[str, str]] = []
    for fp in all_files:
        if any(marker in fp for marker in test_path_markers):
            continue
        edges.extend(extract_edges_fn(Path(fp)))
    return compute_pagerank(edges, top_n=10)
