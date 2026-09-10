"""BFS traversal of import dependency graph for --trace-from.

Forward traversal: entry -> files it imports (directly or transitively).
Accepts a pre-built DependencyMatrix to avoid double-indexing.
"""
from __future__ import annotations

import sys
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer.dependency_matrix import DependencyMatrix

MAX_DEPTH_CAP = 5


def bfs_reachable(
    entry: str,
    import_edges: dict[str, dict[str, int]],
    max_depth: int,
) -> dict[str, int]:
    """Return {file: hop_distance} for all files reachable from entry (forward).

    entry itself is included with hops=0.
    max_depth is the maximum number of hops (inclusive).
    """
    visited: dict[str, int] = {entry: 0}
    queue: deque[tuple[str, int]] = deque([(entry, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target in import_edges.get(node, {}):
            if target not in visited:
                visited[target] = depth + 1
                queue.append((target, depth + 1))
    return visited


def get_subgraph(
    dm: DependencyMatrix,
    entry_path: str,
    depth: int,
) -> dict[str, int] | None:
    """Return reachable {file: hops} dict or None if entry_path is not in index.

    Caps depth at MAX_DEPTH_CAP, emitting a stderr warning if exceeded.
    """
    if depth > MAX_DEPTH_CAP:
        print(
            f"WARNING: --depth {depth} exceeds maximum ({MAX_DEPTH_CAP}); "
            f"capping at {MAX_DEPTH_CAP}",
            file=sys.stderr,
        )
        depth = MAX_DEPTH_CAP

    all_known: set[str] = set(dm._import_edges.keys())
    for src in dm._import_edges:
        all_known.update(dm._import_edges[src].keys())

    if entry_path not in all_known:
        return None  # caller converts to entry_point_not_found error

    return bfs_reachable(entry_path, dm._import_edges, depth)
