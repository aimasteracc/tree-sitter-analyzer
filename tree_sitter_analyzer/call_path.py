#!/usr/bin/env python3
"""
Call Path Finder — BFS-based execution path discovery between two functions.

Finds all call chains from a source function to a target function using
the SQL-backed unified ``edges`` table (CALLS rows).  This is distinct from
callers (all X that call Y) and callees (all Y that X calls) — it
answers "how does execution reach from A to B?"

Two backends:
  - SQL-native: queries the ``edges`` table directly — O(k) per hop
  - In-memory: builds a :class:`CallGraph` and walks ``_callees`` / ``_callers`` maps
"""

from __future__ import annotations

import sqlite3
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .utils import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Unified edge-table SELECTs (B1.2)
#
# CALLS rows now live in the single ``edges`` table.  Real columns carry
# caller_name/callee_name/file_path; the remaining scalars (caller_line,
# callee_resolved_file) are read from the metadata JSON blob.  ``file_path`` is
# the caller's file (== legacy ``ast_call_edges.caller_file``), and ``line`` is
# the call-site line (== legacy ``callee_line``).  Aliases preserve the exact
# dict keys the BFS code downstream expects, so behaviour is unchanged.
# ---------------------------------------------------------------------------

_FORWARD_EDGE_SELECT = (
    "SELECT caller_name, file_path AS caller_file, callee_name, "
    "line AS callee_line, "
    "json_extract(metadata, '$.callee_resolved_file') AS callee_resolved_file, "
    "file_path "
    "FROM edges "
)

_BACKWARD_EDGE_SELECT = (
    "SELECT caller_name, file_path AS caller_file, "
    "json_extract(metadata, '$.caller_line') AS caller_line, "
    "callee_name, "
    "json_extract(metadata, '$.callee_resolved_file') AS callee_resolved_file, "
    "file_path "
    "FROM edges "
)

# ---------------------------------------------------------------------------
# Direction helpers — forward (callee) direction
# ---------------------------------------------------------------------------


def _fwd_state(row: dict[str, Any]) -> tuple[str, str | None]:
    """Extract the next (name, file) state from a forward-edge row."""
    callee_file = row.get("callee_resolved_file") or row.get("file_path", "")
    return (row["callee_name"], callee_file or None)


def _fwd_hop(
    current_name: str, current_file: str | None, row: dict[str, Any]
) -> dict[str, Any]:
    """Build a hop dict for a forward (callee direction) step."""
    callee_file = row.get("callee_resolved_file") or row.get("file_path", "")
    return {
        "caller": current_name,
        "caller_file": current_file or "",
        "callee": row["callee_name"],
        "callee_file": callee_file,
        "line": row.get("callee_line", 0),
    }


# ---------------------------------------------------------------------------
# Direction helpers — backward (caller) direction
# ---------------------------------------------------------------------------


def _bwd_state(row: dict[str, Any]) -> tuple[str, str | None]:
    """Extract the next (name, file) state from a backward-edge row."""
    return (row["caller_name"], row.get("caller_file") or None)


def _bwd_hop(
    current_name: str, current_file: str | None, row: dict[str, Any]
) -> dict[str, Any]:
    """Build a hop dict for a backward (caller direction) step."""
    return {
        "caller": row["caller_name"],
        "caller_file": row.get("caller_file", ""),
        "callee": current_name,
        "callee_file": current_file or "",
        "line": row.get("caller_line", 0),
    }


# ---------------------------------------------------------------------------
# Direction helpers — forward graph direction
# ---------------------------------------------------------------------------


def _graph_fwd_state(callee: dict[str, Any]) -> tuple[str, str | None]:
    return (callee.get("name", ""), callee.get("file", "") or None)


def _graph_fwd_hop(
    current_name: str, current_file: str | None, callee: dict[str, Any]
) -> dict[str, Any]:
    return {
        "caller": current_name,
        "caller_file": current_file or "",
        "callee": callee.get("name", ""),
        "callee_file": callee.get("file", ""),
        "line": callee.get("line", 0),
    }


# ---------------------------------------------------------------------------
# Direction helpers — backward graph direction
# ---------------------------------------------------------------------------


def _graph_bwd_state(caller: dict[str, Any]) -> tuple[str, str | None]:
    return (caller.get("name", ""), caller.get("file", "") or None)


def _graph_bwd_hop(
    current_name: str, current_file: str | None, caller: dict[str, Any]
) -> dict[str, Any]:
    return {
        "caller": caller.get("name", ""),
        "caller_file": caller.get("file", ""),
        "callee": current_name,
        "callee_file": current_file or "",
        "line": caller.get("line", 0),
    }


# ---------------------------------------------------------------------------
# Shared target-matching predicate
# ---------------------------------------------------------------------------


def _target_match(
    name: str,
    file_: str | None,
    target: tuple[str, str | None],
) -> bool:
    """Return True when (name, file_) matches the target (name, file) pair."""
    target_name, target_file = target
    if name != target_name:
        return False
    if target_file and file_ and file_ != target_file:
        return False
    return True


def _lookup_in_visited(
    state: tuple[str, str | None],
    visited: dict[tuple[str, str | None], list[dict[str, Any]]],
) -> tuple[bool, list[dict[str, Any]]]:
    """Lookup *state* in *visited*, also accepting a name-only (file=None) wildcard.

    #797: bidirectional BFS stores visited nodes keyed by (name, file).  When
    the caller did not specify a target file the backward frontier is seeded
    with (target, None), but the forward frontier discovers the same node as
    (target, resolved_file).  An exact dict lookup then misses the intersection.
    This helper checks both the exact key and the name-only key so that a
    missing file acts as a wildcard (i.e. any file matches when the other side
    has no file constraint).

    Only the (name, None) wildcard is checked — a state with a concrete file
    never wildcards against another concrete file, so cross-file false matches
    cannot occur.
    """
    if state in visited:
        return True, visited[state]
    # Wildcard: if visited has an entry with no file constraint for this name,
    # treat it as a match regardless of our resolved file.
    if state[1] is not None:
        name_only = (state[0], None)
        if name_only in visited:
            return True, visited[name_only]
    return False, []


# ---------------------------------------------------------------------------
# Generic BFS engines
# ---------------------------------------------------------------------------


def _bfs_sql_core(
    conn: sqlite3.Connection,
    start_name: str,
    start_file: str | None,
    target_key: tuple[str, str | None],
    max_depth: int,
    max_paths: int,
    query_fn: Callable,
    state_fn: Callable,
    hop_fn: Callable,
    prepend: bool,
) -> list[Any]:
    """BFS over the unified ``edges`` table in one direction (forward/backward)."""
    queue: deque[tuple[str, str | None, list[dict[str, Any]]]] = deque(
        [(start_name, start_file, [])]
    )
    visited: set[tuple[str, str | None]] = {(start_name, start_file)}
    paths: list[Any] = []
    while queue and len(paths) < max_paths:
        current_name, current_file, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for row in query_fn(conn, current_name, current_file):
            hop = hop_fn(current_name, current_file, row)
            new_path = [hop] + path if prepend else path + [hop]
            state = state_fn(row)
            if _target_match(state[0], state[1], target_key):
                paths.append(_make_chain(new_path))
            elif state not in visited:
                visited.add(state)
                queue.append((*state, new_path))
    return paths


def _bfs_graph_core(
    get_neighbors: Callable,
    start_name: str,
    start_file: str | None,
    target_key: tuple[str, str | None],
    max_depth: int,
    max_paths: int,
    paths: list[Any],
    state_fn: Callable,
    hop_fn: Callable,
    prepend: bool,
) -> None:
    """BFS over an in-memory CallGraph in one direction."""
    queue: deque[tuple[str, str | None, list[dict[str, Any]]]] = deque(
        [(start_name, start_file, [])]
    )
    visited: set[tuple[str, str | None]] = {(start_name, start_file)}
    while queue and len(paths) < max_paths:
        current_name, current_file, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for neighbor in get_neighbors(current_name, current_file):
            hop = hop_fn(current_name, current_file, neighbor)
            new_path = [hop] + path if prepend else path + [hop]
            state = state_fn(neighbor)
            if _target_match(state[0], state[1], target_key):
                paths.append(_make_chain(new_path))
            elif state not in visited:
                visited.add(state)
                queue.append((*state, new_path))


@dataclass
class CallChain:
    """A single call chain from source to target."""

    hops: list[dict[str, Any]] = field(default_factory=list)
    total_hops: int = 0
    files_crossed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hops": self.hops,
            "total_hops": self.total_hops,
            "files_crossed": self.files_crossed,
        }


@dataclass
class CallPathResult:
    """Result of a call path search."""

    source: str
    target: str
    paths: list[CallChain] = field(default_factory=list)
    data_source: str = "unknown"
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "path_count": len(self.paths),
            "truncated": self.truncated,
            "data_source": self.data_source,
            "paths": [p.to_dict() for p in self.paths],
        }


def _files_in_chain(hops: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    for hop in hops:
        f = hop.get("file", "")
        if f:
            seen.add(f)
    return len(seen)


def _make_chain(path: list[dict[str, Any]]) -> CallChain:
    """Construct a CallChain from a hop list."""
    return CallChain(
        hops=path, total_hops=len(path), files_crossed=_files_in_chain(path)
    )


class CallPathFinder:
    """Find execution paths between two functions via BFS on call edges.

    Parameters
    ----------
    project_root : str
        Root directory of the project to analyse.
    cache : ASTCache | None
        Optional pre-built cache.  When *None* the finder will attempt
        to open one on first query; if that also fails it falls back
        to an in-memory :class:`CallGraph`.
    """

    def __init__(self, project_root: str, cache: Any | None = None) -> None:
        self._project_root = project_root
        self._cache = cache
        self._data_source = "unknown"

    def _try_get_cache(self) -> Any:
        if self._cache is not None:
            return self._cache
        try:
            from .ast_cache import ASTCache

            cache = ASTCache(self._project_root)
            if cache.has_call_edges() or cache.get_stats().get("total_files", 0) > 0:
                self._cache = cache
                return cache
            cache.close()
        except Exception:
            pass
        return None

    def find_path(
        self,
        source_function: str,
        target_function: str,
        source_file: str | None = None,
        target_file: str | None = None,
        max_depth: int = 10,
        max_paths: int = 5,
        direction: str = "forward",
    ) -> CallPathResult:
        """Find call paths from *source_function* to *target_function*.

        Parameters
        ----------
        source_function : str
            Name of the starting function.
        target_function : str
            Name of the destination function.
        source_file : str | None
            Optional file to disambiguate the source function.
        target_file : str | None
            Optional file to disambiguate the target function.
        max_depth : int
            Maximum BFS depth (default 10).
        max_paths : int
            Maximum number of paths to return (default 5).
        direction : str
            ``"forward"`` (follow callees from source),
            ``"backward"`` (follow callers from target),
            or ``"bidirectional"`` (BFS from both ends, meet in middle).
        """
        cache = self._try_get_cache()
        if cache is not None and cache.has_call_edges():
            if direction == "bidirectional":
                result = self._bidirectional_sql(
                    cache,
                    source_function,
                    target_function,
                    source_file,
                    target_file,
                    max_depth,
                    max_paths,
                )
            elif direction == "backward":
                result = self._bfs_sql_backward(
                    cache,
                    source_function,
                    target_function,
                    source_file,
                    target_file,
                    max_depth,
                    max_paths,
                )
            else:
                result = self._bfs_sql_forward(
                    cache,
                    source_function,
                    target_function,
                    source_file,
                    target_file,
                    max_depth,
                    max_paths,
                )
            result.data_source = "sql"
            return result

        return self._fallback_graph(
            source_function,
            target_function,
            source_file,
            target_file,
            max_depth,
            max_paths,
            direction,
        )

    def _bfs_sql_forward(
        self,
        cache: Any,
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        max_depth: int,
        max_paths: int,
    ) -> CallPathResult:
        paths = _bfs_sql_core(
            cache.get_conn(),
            source_function,
            source_file,
            (target_function, target_file),
            max_depth,
            max_paths,
            self._query_forward_edges,
            _fwd_state,
            _fwd_hop,
            prepend=False,
        )
        return CallPathResult(
            source=source_function,
            target=target_function,
            paths=paths,
            truncated=len(paths) >= max_paths,
        )

    def _bfs_sql_backward(
        self,
        cache: Any,
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        max_depth: int,
        max_paths: int,
    ) -> CallPathResult:
        paths = _bfs_sql_core(
            cache.get_conn(),
            target_function,
            target_file,
            (source_function, source_file),
            max_depth,
            max_paths,
            self._query_backward_edges,
            _bwd_state,
            _bwd_hop,
            prepend=True,
        )
        return CallPathResult(
            source=source_function,
            target=target_function,
            paths=paths,
            truncated=len(paths) >= max_paths,
        )

    def _bidirectional_sql(
        self,
        cache: Any,
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        max_depth: int,
        max_paths: int,
    ) -> CallPathResult:
        conn = cache.get_conn()
        forward_visited: dict[tuple[str, str | None], list[dict[str, Any]]] = {
            (source_function, source_file): [],
        }
        backward_visited: dict[tuple[str, str | None], list[dict[str, Any]]] = {
            (target_function, target_file): [],
        }
        forward_queue: deque[tuple[str, str | None]] = deque(
            [(source_function, source_file)]
        )
        backward_queue: deque[tuple[str, str | None]] = deque(
            [(target_function, target_file)]
        )
        paths: list[CallChain] = []
        depth = 0
        half_depth = max(1, max_depth // 2)
        while forward_queue or backward_queue:
            if depth >= half_depth or len(paths) >= max_paths:
                break
            next_forward: deque[tuple[str, str | None]] = deque()
            while forward_queue:
                current_name, current_file = forward_queue.popleft()
                rows = self._query_forward_edges(conn, current_name, current_file)
                for row in rows:
                    callee_name = row["callee_name"]
                    callee_file = row.get("callee_resolved_file") or row.get(
                        "file_path", ""
                    )
                    state = (callee_name, callee_file or None)
                    hop = {
                        "caller": current_name,
                        "caller_file": current_file or "",
                        "callee": callee_name,
                        "callee_file": callee_file,
                        "line": row.get("callee_line", 0),
                    }
                    parent_path = forward_visited.get((current_name, current_file), [])
                    forward_visited[state] = parent_path + [hop]
                    # #797: only check for a meeting in backward_visited to stop
                    # further exploration of this callee.  Paths are recorded
                    # exclusively by the backward pass to prevent duplicates when
                    # both passes discover the same meeting node in the same round.
                    if _lookup_in_visited(state, backward_visited)[0]:
                        # Terminal node reached: stop exploring its callees.
                        continue
                    next_forward.append(state)
            forward_queue = next_forward
            next_backward: deque[tuple[str, str | None]] = deque()
            while backward_queue:
                current_name, current_file = backward_queue.popleft()
                rows = self._query_backward_edges(conn, current_name, current_file)
                for row in rows:
                    caller_name = row["caller_name"]
                    caller_file = row["caller_file"]
                    state = (caller_name, caller_file or None)
                    hop = {
                        "caller": caller_name,
                        "caller_file": caller_file,
                        "callee": current_name,
                        "callee_file": current_file or "",
                        "line": row.get("caller_line", 0),
                    }
                    parent_path = backward_visited.get((current_name, current_file), [])
                    backward_visited[state] = [hop] + list(parent_path)
                    found, fwd_path = _lookup_in_visited(state, forward_visited)
                    if found:
                        full_path = fwd_path + list(reversed(backward_visited[state]))
                        paths.append(_make_chain(full_path))
                        continue
                    next_backward.append(state)
            backward_queue = next_backward
            depth += 1
        return CallPathResult(
            source=source_function,
            target=target_function,
            paths=paths[:max_paths],
            truncated=len(paths) >= max_paths,
        )

    @staticmethod
    def _query_forward_edges(
        conn: sqlite3.Connection,
        caller_name: str,
        caller_file: str | None,
    ) -> list[dict[str, Any]]:
        try:
            if caller_file:
                rows = conn.execute(
                    _FORWARD_EDGE_SELECT
                    + "WHERE kind = 'calls' AND caller_name = ? AND file_path = ?",
                    (caller_name, caller_file),
                ).fetchall()
                # #734: intermediate nodes use callee_resolved_file || file_path
                # as their "file" — file_path is the *caller-side* file, but the
                # node's outgoing edges are stored under its *definition* file.
                # When the file-filtered query returns nothing, retry without the
                # filter so cross-file chains are not silently dead-ended.
                if not rows:
                    rows = conn.execute(
                        _FORWARD_EDGE_SELECT
                        + "WHERE kind = 'calls' AND caller_name = ?",
                        (caller_name,),
                    ).fetchall()
            else:
                rows = conn.execute(
                    _FORWARD_EDGE_SELECT + "WHERE kind = 'calls' AND caller_name = ?",
                    (caller_name,),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _query_backward_edges(
        conn: sqlite3.Connection,
        callee_name: str,
        callee_file: str | None,
    ) -> list[dict[str, Any]]:
        try:
            if callee_file:
                rows = conn.execute(
                    _BACKWARD_EDGE_SELECT + "WHERE kind = 'calls' AND callee_name = ? "
                    "AND json_extract(metadata, '$.callee_resolved_file') = ?",
                    (callee_name, callee_file),
                ).fetchall()
                if not rows:
                    rows = conn.execute(
                        _BACKWARD_EDGE_SELECT
                        + "WHERE kind = 'calls' AND callee_name = ? "
                        "AND file_path = ?",
                        (callee_name, callee_file),
                    ).fetchall()
            else:
                rows = conn.execute(
                    _BACKWARD_EDGE_SELECT + "WHERE kind = 'calls' AND callee_name = ?",
                    (callee_name,),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def _fallback_graph(
        self,
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        max_depth: int,
        max_paths: int,
        direction: str,
    ) -> CallPathResult:
        try:
            from .call_graph import CallGraph

            graph = CallGraph(self._project_root)
            graph.build()
            self._data_source = "parse"
        except Exception as exc:
            logger.debug("fallback CallGraph build failed: %s", exc)
            return CallPathResult(
                source=source_function,
                target=target_function,
                data_source="error",
            )

        paths: list[CallChain] = []
        if direction in ("forward", "bidirectional"):
            self._bfs_graph_forward(
                graph,
                source_function,
                target_function,
                source_file,
                target_file,
                max_depth,
                max_paths,
                paths,
            )
        # #797: bidirectional fallback must also try backward when forward found
        # nothing (mirrors the SQL bidirectional that tries both frontiers).
        if direction in ("backward", "bidirectional") and len(paths) < max_paths:
            self._bfs_graph_backward(
                graph,
                source_function,
                target_function,
                source_file,
                target_file,
                max_depth,
                max_paths,
                paths,
            )
        return CallPathResult(
            source=source_function,
            target=target_function,
            paths=paths[:max_paths],
            data_source="parse",
            truncated=len(paths) >= max_paths,
        )

    @staticmethod
    def _bfs_graph_forward(
        graph: Any,
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        max_depth: int,
        max_paths: int,
        paths: list[CallChain],
    ) -> None:
        _bfs_graph_core(
            graph.callees_of,
            source_function,
            source_file,
            (target_function, target_file),
            max_depth,
            max_paths,
            paths,
            _graph_fwd_state,
            _graph_fwd_hop,
            prepend=False,
        )

    @staticmethod
    def _bfs_graph_backward(
        graph: Any,
        source_function: str,
        target_function: str,
        source_file: str | None,
        target_file: str | None,
        max_depth: int,
        max_paths: int,
        paths: list[CallChain],
    ) -> None:
        _bfs_graph_core(
            graph.callers_of,
            target_function,
            target_file,
            (source_function, source_file),
            max_depth,
            max_paths,
            paths,
            _graph_bwd_state,
            _graph_bwd_hop,
            prepend=True,
        )
