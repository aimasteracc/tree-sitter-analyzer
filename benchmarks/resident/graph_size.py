"""Size and memory of today's in-process call graph state (RFC-0042 §8).

Usage::

    python benchmarks/resident/graph_size.py --repo PATH [--out out.json]

Builds ``CachedCallGraph(persist=False)`` over the published index under
``tracemalloc`` and reports: indexed files and symbols, graph nodes
(definitions), certain and name-only (possible) edges, retained and peak MB,
and bytes per (node + edge). This is the state ``call_graph_memo`` keeps in a
long-running server, i.e. what RFC-0042 P1 loads at start.
"""

from __future__ import annotations

import argparse
import gc
import sqlite3
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import write_json  # noqa: E402


def index_counts(db_path: str | None) -> dict[str, Any]:
    if not db_path:
        return {}
    out: dict[str, Any] = {}
    conn = sqlite3.connect(Path(db_path).absolute().as_uri() + "?mode=ro", uri=True)
    try:
        for label, sql in (
            ("files", "SELECT COUNT(*) FROM ast_index"),
            ("symbols", "SELECT COUNT(*) FROM ast_symbol_rows"),
            ("call_edge_rows", "SELECT COUNT(*) FROM edges"),
        ):
            try:
                out[label] = conn.execute(sql).fetchone()[0]
            except sqlite3.Error as exc:
                out[label] = f"n/a: {exc}"
    finally:
        conn.close()
    return out


def measure(repo: str) -> dict[str, Any]:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    cache = ASTCache(repo)
    try:
        rec: dict[str, Any] = {"repo": Path(repo).name}
        rec.update(index_counts(getattr(cache, "db_path", None)))
        gc.collect()
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        t0 = time.perf_counter()
        graph = CachedCallGraph(repo, cache=cache, fallback=False, persist=False)
        graph.build()
        rec["build_s_under_tracemalloc"] = round(time.perf_counter() - t0, 2)
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        certain = sum(len(v) for v in graph._callers.values())
        possible = sum(len(v) for v in graph._possible_callers.values())
        nodes = len(graph._functions)
        from tree_sitter_analyzer import call_graph_memo

        # RFC-0043 §4: the byte budget's estimate must never fall below retained.
        estimate = call_graph_memo.estimate_state_bytes(graph._export_state())
        rec["memo_estimate_mb"] = round(estimate / 1e6, 1)
        rec.update(
            built=bool(graph._built),
            nodes=nodes,
            certain_edges=certain,
            possible_edges=possible,
            nodes_plus_edges=nodes + certain + possible,
            retained_mb=round((current - base) / 1e6, 1),
            peak_mb=round((peak - base) / 1e6, 1),
            bytes_per_node_edge=round(
                (current - base) / max(1, nodes + certain + possible)
            ),
        )
        return rec
    finally:
        cache.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    write_json(args.out, measure(args.repo))


if __name__ == "__main__":
    main()
