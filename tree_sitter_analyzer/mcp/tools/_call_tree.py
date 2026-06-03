"""Pure depth-limited call-tree builder (the ``tree`` primitive).

Mirrors mycelium RFC-0020 (callee tree) / RFC-0021 (caller tree): instead of an
agent iterating ``codegraph_callees`` / ``codegraph_callers`` BFS-style and
accumulating state across many round-trips, build the whole depth-limited tree
in ONE call and return a nested ``{name, file, line, children}`` structure.

This module is deliberately storage-agnostic: it takes an ``expand`` callback
that returns the *direct* neighbours of a node, so the same DFS works over the
SQL edge store, the in-memory CallGraph, or an in-memory test dict. The actual
edge lookups are reused from the existing single-hop call-graph machinery
(``ASTCache.query_callees`` / ``query_callers``, which themselves delegate to
``bfs_callees`` / ``bfs_callers`` over the unified ``edges`` table — B1).

Guards (so a large Java callee tree cannot blow the token budget):

* ``max_depth`` — capped traversal depth (default 3, hard cap 10).
* ``max_nodes`` — global node cap across the whole tree; once hit, expansion
  stops and ``truncated`` is flagged.
* per-path visited set — a node already on the current DFS path is returned as
  a leaf (cycle break), matching RFC-0020/0021.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Expand callback: (name, file) -> list of direct-neighbour dicts, each with at
# least ``name``; ``file``/``line`` optional.
Expander = Callable[[str, str | None], list[dict[str, Any]]]

DEFAULT_MAX_DEPTH = 3
MAX_DEPTH_CAP = 10
DEFAULT_MAX_NODES = 150


def _node_key(name: str, file: str | None) -> str:
    return f"{file or ''}:{name}"


def build_call_tree(
    root_name: str,
    root_file: str | None,
    expand: Expander,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    children_key: str = "children",
) -> dict[str, Any]:
    """Build a depth-limited nested call tree from ``root_name``.

    Args:
        root_name: Seed symbol name.
        root_file: Optional file to disambiguate the seed.
        expand: ``(name, file) -> [neighbour dict, ...]`` direct-neighbour fetch.
        max_depth: Maximum hops from the root (1 → direct neighbours only).
            Clamped to ``[0, MAX_DEPTH_CAP]``.
        max_nodes: Global cap on total nodes (excluding the root). Once reached,
            no further children are expanded and ``truncated`` is set.
        children_key: Key under which a node stores its descendants. ``children``
            for callee trees; callers reuse ``children`` too for a uniform shape.

    Returns:
        ``{"root": <node>, "node_count": int, "truncated": bool,
           "max_depth": int}`` where each ``<node>`` is
        ``{"name", "file", "line", children_key: [...]}``.
    """
    depth = max(0, min(int(max_depth), MAX_DEPTH_CAP))
    cap = max(1, int(max_nodes))

    # Mutable counter shared across the recursion (immutable-by-default style
    # would force threading a return tuple everywhere; a single-element list
    # keeps the DFS readable while still being local to this call).
    state = {"count": 0, "truncated": False}

    root_node: dict[str, Any] = {
        "name": root_name,
        "file": root_file or "",
        "line": 0,
        children_key: [],
    }

    def _dfs(
        node: dict[str, Any],
        name: str,
        file: str | None,
        remaining: int,
        path: set[str],
    ) -> None:
        if remaining <= 0:
            return
        if state["count"] >= cap:
            state["truncated"] = True
            return
        children: list[dict[str, Any]] = []
        for neighbour in expand(name, file):
            if state["count"] >= cap:
                state["truncated"] = True
                break
            n_name = str(neighbour.get("name", ""))
            if not n_name:
                continue
            n_file = neighbour.get("file") or ""
            n_line = int(neighbour.get("line", 0) or 0)
            key = _node_key(n_name, n_file)
            child: dict[str, Any] = {
                "name": n_name,
                "file": n_file,
                "line": n_line,
                children_key: [],
            }
            state["count"] += 1
            children.append(child)
            # Cycle guard: break on the resolved (file:name) key OR the bare
            # name. The bare-name fallback catches cycles where the same
            # symbol reappears with a different (or unresolved) file across
            # hops — without it, a -> b -> a with distinct files would recurse
            # forever. A node already on the current DFS path becomes a leaf
            # (RFC-0020/0021 semantics).
            if key in path or n_name in path:
                continue
            _dfs(child, n_name, n_file or None, remaining - 1, path | {key, n_name})
        node[children_key] = children

    root_key = _node_key(root_name, root_file)
    _dfs(root_node, root_name, root_file, depth, {root_key, root_name})

    return {
        "root": root_node,
        "node_count": state["count"],
        "truncated": state["truncated"],
        "max_depth": depth,
    }
