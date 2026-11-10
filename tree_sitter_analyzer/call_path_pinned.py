"""#1942: call paths between two *definitions*, not two names.

:mod:`.call_path` walks the ``edges`` table by ``(name, file)``. A qualified
endpoint such as ``Progress.start`` never equals a stored caller name
(``start``), so the walk found nothing; the name-keyed walk also joins every
same-named method of a file, so ``Progress.start`` was explored as
``Live.start``.

Here every node is one definition, ``(name, file, definition line)``:

* the outgoing calls of a node are the edges whose caller is that definition
  (``caller_name``, ``file_path`` and ``caller_line``);
* a call bound to a symbol (``callee_symbol_id``) leads to that definition;
* a call the index could not bind (an untyped receiver, ``self.console.x()``)
  is followed only onto the target, and that hop says ``name_only``. It is not
  expanded into every same-named definition: such a site is recorded as an open
  site, so ``NO_PATH`` can say whether the search was complete.

Every hop carries the call-site line (``call_site_line``, also ``line``) and
the definition lines of both ends.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from typing import Any

#: Open sites named in a ``NO_PATH`` answer.
OPEN_SITES_CAP = 20
#: Definitions examined per BFS before the search reports itself incomplete.
_NODES_MAX = 5000
RESOLVED = "resolved"
NAME_ONLY = "name_only"
#: Edge resolutions that name code outside the project.
_OUTSIDE = frozenset({"builtin", "stdlib", "external"})

_EDGE_COLUMNS = (
    "callee_name, callee_full, line, callee_resolution, callee_resolved_file, "
    "callee_symbol_id"
)


@dataclass(frozen=True)
class Definition:
    """One function or method definition in the index."""

    name: str
    file: str
    line: int
    end_line: int = 0
    owner: str | None = None

    @property
    def label(self) -> str:
        return f"{self.owner}.{self.name}" if self.owner else self.name

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.name, self.file, self.line)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.label, "file": self.file, "line": self.line}


@dataclass
class PinnedResult:
    paths: list[list[dict[str, Any]]] = field(default_factory=list)
    #: Calls on the explored frontier that could not be followed.
    open_sites: list[dict[str, Any]] = field(default_factory=list)
    depth_limited: bool = False

    @property
    def complete(self) -> bool:
        return not self.open_sites and not self.depth_limited


class SymbolBook:
    """Definitions read from the index on demand (owner classes included)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._files: dict[str, list[Definition]] = {}
        self._ids: dict[int, Definition | None] = {}
        self._declared: dict[str, bool] = {}

    def declared(self, name: str) -> bool:
        """Whether any project definition is named ``name`` (unreadable: True)."""
        if name not in self._declared:
            try:
                row = self._conn.execute(
                    "SELECT 1 FROM ast_symbol_rows WHERE name = ? "
                    "AND kind IN ('function', 'method') LIMIT 1",
                    (name,),
                ).fetchone()
                self._declared[name] = row is not None
            except sqlite3.OperationalError:
                self._declared[name] = True
        return self._declared[name]

    def in_file(self, file: str) -> list[Definition]:
        if file not in self._files:
            self._files[file] = _file_definitions(self._conn, file)
        return self._files[file]

    def named(self, name: str) -> list[Definition]:
        """Every definition of ``name`` in the project (ordered)."""
        try:
            rows = self._conn.execute(
                "SELECT DISTINCT file_path FROM ast_symbol_rows "
                "WHERE name = ? AND kind IN ('function', 'method') ORDER BY file_path",
                (name,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        found = [d for row in rows for d in self.in_file(str(row[0])) if d.name == name]
        return sorted(found, key=lambda d: (d.file, d.line))

    def by_id(self, symbol_id: int) -> Definition | None:
        if symbol_id not in self._ids:
            self._ids[symbol_id] = self._read_id(symbol_id)
        return self._ids[symbol_id]

    def at(self, name: str, file: str, line: int | None = None) -> list[Definition]:
        return [
            d
            for d in self.in_file(file)
            if d.name == name and (line is None or d.line == line)
        ]

    def symbol_id(self, definition: Definition) -> int | None:
        try:
            row = self._conn.execute(
                "SELECT id FROM ast_symbol_rows WHERE name = ? AND file_path = ? "
                "AND line = ? AND kind IN ('function', 'method')",
                definition.key,
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return None if row is None else int(row[0])

    def _read_id(self, symbol_id: int) -> Definition | None:
        try:
            row = self._conn.execute(
                "SELECT name, file_path, line FROM ast_symbol_rows WHERE id = ?",
                (symbol_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        found = self.at(str(row[0]), str(row[1]), int(row[2] or 0))
        if found:
            return found[0]
        return Definition(str(row[0]), str(row[1]), int(row[2] or 0))


def _file_definitions(conn: sqlite3.Connection, file: str) -> list[Definition]:
    try:
        row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?", (file,)
        ).fetchone()
        symbols = json.loads(row[0]).get("symbols", []) if row else []
    except (sqlite3.OperationalError, ValueError, TypeError):
        return []
    found = []
    for sym in symbols:
        if sym.get("kind") not in ("function", "method") or not sym.get("name"):
            continue
        found.append(
            Definition(
                str(sym["name"]),
                file,
                int(sym.get("line") or 0),
                int(sym.get("end_line") or 0),
                sym.get("class") or None,
            )
        )
    return found


def outgoing(conn: sqlite3.Connection, node: Definition) -> list[dict[str, Any]]:
    """The call edges whose caller is the definition ``node``."""
    queries = (
        f"SELECT {_EDGE_COLUMNS} FROM edges WHERE kind = 'calls' AND "  # nosec B608
        "caller_name = ? AND file_path = ? AND caller_line = ? ORDER BY line",
        f"SELECT {_EDGE_COLUMNS} FROM edges WHERE kind = 'calls' AND "  # nosec B608
        "caller_name = ? AND file_path = ? AND "
        "json_extract(metadata, '$.caller_line') = ? ORDER BY line",
    )
    for sql in queries:
        try:
            return [dict(r) for r in conn.execute(sql, node.key).fetchall()]
        except sqlite3.OperationalError:
            continue
    return []


def incoming(
    conn: sqlite3.Connection, book: SymbolBook, node: Definition
) -> list[dict[str, Any]]:
    """Call sites bound to ``node``, then unbound sites calling its name."""
    rows: list[dict[str, Any]] = []
    symbol_id = book.symbol_id(node)
    try:
        if symbol_id is not None:
            rows.extend(
                {**dict(r), "resolution": RESOLVED}
                for r in conn.execute(
                    "SELECT caller_name, file_path, caller_line, line FROM edges "
                    "WHERE kind = 'calls' AND callee_symbol_id = ? ORDER BY file_path, line",
                    (symbol_id,),
                ).fetchall()
            )
        rows.extend(
            {**dict(r), "resolution": NAME_ONLY}
            for r in conn.execute(
                "SELECT caller_name, file_path, caller_line, line FROM edges "
                "WHERE kind = 'calls' AND callee_name = ? AND callee_symbol_id IS NULL "
                "AND COALESCE(callee_resolved_file, '') = '' AND "
                "COALESCE(callee_resolution, '') NOT IN ('builtin', 'stdlib', 'external') "
                "ORDER BY file_path, line",
                (node.name,),
            ).fetchall()
        )
    except sqlite3.OperationalError:
        return rows
    return rows


def callee_of(book: SymbolBook, row: dict[str, Any]) -> Definition | None:
    """The definition an edge is bound to, or None for an unbound call."""
    symbol_id = row.get("callee_symbol_id")
    if symbol_id is not None:
        found = book.by_id(int(symbol_id))
        if found is not None:
            return found
    resolved_file = row.get("callee_resolved_file") or ""
    if resolved_file:
        same = book.at(str(row.get("callee_name") or ""), resolved_file)
        if len(same) == 1:
            return same[0]
    return None


def find_pinned_paths(
    conn: sqlite3.Connection,
    book: SymbolBook,
    source: Definition,
    target: Definition,
    max_depth: int,
    max_paths: int,
) -> PinnedResult:
    """Breadth-first from ``source`` to ``target`` over bound call edges."""
    result = PinnedResult()
    queue: deque[tuple[Definition, list[dict[str, Any]]]] = deque([(source, [])])
    visited = {source.key}
    while queue and len(result.paths) < max_paths:
        node, path = queue.popleft()
        if len(path) >= max_depth:
            result.depth_limited = True
            continue
        if len(visited) > _NODES_MAX:
            result.depth_limited = True
            break
        for row in outgoing(conn, node):
            if row.get("callee_resolution") in _OUTSIDE:
                continue  # a builtin / library call: nothing in the project
            callee = callee_of(book, row)
            if callee is None:
                if _may_be(row, target):
                    hop = _hop(node, target, row, NAME_ONLY)
                    result.paths.append([*path, hop])
                elif book.declared(str(row.get("callee_name") or "")):
                    _open_site(result, node, row)
                continue
            hop = _hop(node, callee, row, RESOLVED)
            if callee.key == target.key:
                result.paths.append([*path, hop])
            elif callee.key not in visited:
                visited.add(callee.key)
                queue.append((callee, [*path, hop]))
            if len(result.paths) >= max_paths:
                break
    result.paths.sort(key=lambda hops: (_name_only_hops(hops), len(hops)))
    return result


def _may_be(row: dict[str, Any], target: Definition) -> bool:
    """An unbound call that may reach ``target``: its name, and no other file."""
    if str(row.get("callee_name") or "") != target.name:
        return False
    resolved_file = row.get("callee_resolved_file") or ""
    return not resolved_file or resolved_file == target.file


def _name_only_hops(hops: list[dict[str, Any]]) -> int:
    return sum(1 for hop in hops if hop.get("callee_resolution") == NAME_ONLY)


def _hop(
    caller: Definition, callee: Definition, row: dict[str, Any], resolution: str
) -> dict[str, Any]:
    line = int(row.get("line") or 0)
    hop: dict[str, Any] = {
        "caller": caller.label,
        "caller_file": caller.file,
        "caller_line": caller.line,
        "callee": callee.label,
        "callee_file": callee.file,
        "callee_line": callee.line,
        "line": line,
        "call_site_line": line,
        "callee_resolution": resolution,
    }
    if resolution == NAME_ONLY:
        hop["callee_expression"] = str(row.get("callee_full") or "")
    return hop


def _open_site(result: PinnedResult, node: Definition, row: dict[str, Any]) -> None:
    """An unbound call to a name the project declares: it may lead on."""
    result.open_sites.append(
        {
            "file": node.file,
            "line": int(row.get("line") or 0),
            "caller": node.label,
            "callee": str(row.get("callee_full") or row.get("callee_name") or ""),
        }
    )


__all__ = [
    "NAME_ONLY",
    "OPEN_SITES_CAP",
    "RESOLVED",
    "Definition",
    "PinnedResult",
    "SymbolBook",
    "callee_of",
    "find_pinned_paths",
    "incoming",
    "outgoing",
]
