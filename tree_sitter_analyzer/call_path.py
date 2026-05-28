#!/usr/bin/env python3
"""
Call Path Finder — BFS-based execution path discovery between two functions.

Finds all call chains from a source function to a target function using
the SQL-backed ``ast_call_edges`` table.  This is distinct from
callers (all X that call Y) and callees (all Y that X calls) — it
answers "how does execution reach from A to B?"

Two backends:
  - SQL-native: queries ``ast_call_edges`` directly — O(k) per hop
  - In-memory: builds a :class:`CallGraph` and walks ``_callees`` / ``_callers`` maps
"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .utils import setup_logger

logger = setup_logger(__name__)


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
        conn = cache.get_conn()
        start_key = (source_function, source_file)
        target_key = (target_function, target_file)
        queue: deque[tuple[str, str | None, list[dict[str, Any]]]] = deque()
        queue.append((source_function, source_file, []))
        visited: set[tuple[str, str | None]] = {start_key}
        paths: list[CallChain] = []
        while queue and len(paths) < max_paths:
            current_name, current_file, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            rows = self._query_forward_edges(conn, current_name, current_file)
            for row in rows:
                callee_name = row["callee_name"]
                callee_file = row.get("callee_resolved_file") or row.get(
                    "file_path", ""
                )
                hop = {
                    "caller": current_name,
                    "caller_file": current_file or "",
                    "callee": callee_name,
                    "callee_file": callee_file,
                    "line": row.get("callee_line", 0),
                }
                new_path = path + [hop]
                if self._matches_target(callee_name, callee_file, target_key):
                    paths.append(_make_chain(new_path))
                    continue
                state = (callee_name, callee_file or None)
                if state not in visited:
                    visited.add(state)
                    queue.append((callee_name, callee_file or None, new_path))
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
        conn = cache.get_conn()
        target_key = (target_function, target_file)
        start_key = (source_function, source_file)
        queue: deque[tuple[str, str | None, list[dict[str, Any]]]] = deque()
        queue.append((target_function, target_file, []))
        visited: set[tuple[str, str | None]] = {target_key}
        paths: list[CallChain] = []
        while queue and len(paths) < max_paths:
            current_name, current_file, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            rows = self._query_backward_edges(conn, current_name, current_file)
            for row in rows:
                caller_name = row["caller_name"]
                caller_file = row["caller_file"]
                hop = {
                    "caller": caller_name,
                    "caller_file": caller_file,
                    "callee": current_name,
                    "callee_file": current_file or "",
                    "line": row.get("caller_line", 0),
                }
                new_path = [hop] + path
                if self._matches_target(caller_name, caller_file, start_key):
                    paths.append(_make_chain(new_path))
                    continue
                state = (caller_name, caller_file or None)
                if state not in visited:
                    visited.add(state)
                    queue.append((caller_name, caller_file or None, new_path))
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
                    if state in backward_visited:
                        full_path = forward_visited[state] + list(
                            reversed(backward_visited[state])
                        )
                        paths.append(_make_chain(full_path))
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
                    if state in forward_visited:
                        full_path = forward_visited[state] + list(
                            reversed(backward_visited[state])
                        )
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
                    "SELECT caller_name, caller_file, callee_name, "
                    "callee_line, callee_resolved_file, file_path "
                    "FROM ast_call_edges "
                    "WHERE caller_name = ? AND caller_file = ?",
                    (caller_name, caller_file),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, callee_name, "
                    "callee_line, callee_resolved_file, file_path "
                    "FROM ast_call_edges WHERE caller_name = ?",
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
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_resolved_file, file_path "
                    "FROM ast_call_edges "
                    "WHERE callee_name = ? AND callee_resolved_file = ?",
                    (callee_name, callee_file),
                ).fetchall()
                if not rows:
                    rows = conn.execute(
                        "SELECT caller_name, caller_file, caller_line, "
                        "callee_name, callee_resolved_file, file_path "
                        "FROM ast_call_edges "
                        "WHERE callee_name = ? AND file_path = ?",
                        (callee_name, callee_file),
                    ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_resolved_file, file_path "
                    "FROM ast_call_edges WHERE callee_name = ?",
                    (callee_name,),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _matches_target(
        name: str,
        file: str | None,
        target: tuple[str, str | None],
    ) -> bool:
        target_name, target_file = target
        if name != target_name:
            return False
        if target_file and file and file != target_file:
            return False
        return True

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
        if direction == "backward" and len(paths) < max_paths:
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
        start_key = (source_function, source_file)
        queue: deque[tuple[str, str | None, list[dict[str, Any]]]] = deque()
        queue.append((source_function, source_file, []))
        visited: set[tuple[str, str | None]] = {start_key}
        while queue and len(paths) < max_paths:
            current_name, current_file, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            callees = graph.callees_of(current_name, current_file)
            for callee in callees:
                callee_name = callee.get("name", "")
                callee_file = callee.get("file", "")
                hop = {
                    "caller": current_name,
                    "caller_file": current_file or "",
                    "callee": callee_name,
                    "callee_file": callee_file,
                    "line": callee.get("line", 0),
                }
                new_path = path + [hop]
                state = (callee_name, callee_file or None)
                if CallPathFinder._matches_target(
                    callee_name, callee_file, (target_function, target_file)
                ):
                    paths.append(_make_chain(new_path))
                elif state not in visited:
                    visited.add(state)
                    queue.append((callee_name, callee_file or None, new_path))

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
        queue: deque[tuple[str, str | None, list[dict[str, Any]]]] = deque()
        queue.append((target_function, target_file, []))
        visited: set[tuple[str, str | None]] = {(target_function, target_file)}
        while queue and len(paths) < max_paths:
            current_name, current_file, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            callers = graph.callers_of(current_name, current_file)
            for caller in callers:
                caller_name = caller.get("name", "")
                caller_file = caller.get("file", "")
                hop = {
                    "caller": caller_name,
                    "caller_file": caller_file,
                    "callee": current_name,
                    "callee_file": current_file or "",
                    "line": caller.get("line", 0),
                }
                new_path = [hop] + path
                state = (caller_name, caller_file or None)
                if CallPathFinder._matches_target(
                    caller_name, caller_file, (source_function, source_file)
                ):
                    paths.append(_make_chain(new_path))
                elif state not in visited:
                    visited.add(state)
                    queue.append((caller_name, caller_file or None, new_path))
