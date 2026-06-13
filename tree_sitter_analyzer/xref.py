#!/usr/bin/env python3
"""
Cross-Reference Engine — AST-cache-backed instant symbol cross-referencing.

Combines all AST cache dimensions (FTS5 symbols, call edges, import graph,
file dependencies) into a single unified cross-reference query. No re-parsing.

Dimensions returned for a symbol query:
  - Definition location (file, line, signature)
  - Direct callers (who calls this function/class)
  - Direct callees (what does this function call)
  - Import dependents (which files import the containing module)
  - File-level blast radius (transitive dependents)

All data comes from the pre-indexed SQLite cache — queries are O(1) after
initial indexing. Falls back to empty results when cache is empty.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .codegraph_query_backend import CodeGraphQueryBackend

logger = logging.getLogger(__name__)

# SQLite's default SQLITE_MAX_VARIABLE_NUMBER is 999. Each inbound xref query
# binds the file's symbol-name list plus 2 file_path params, so chunk the names
# well under that ceiling (mirrors the portability chunking in _route_cache.py).
_XREF_NAME_CHUNK = 900


@dataclass
class XRefResult:
    symbol: str
    file_path: str | None
    definitions: list[dict[str, Any]] = field(default_factory=list)
    callers: list[dict[str, Any]] = field(default_factory=list)
    callees: list[dict[str, Any]] = field(default_factory=list)
    import_dependents: list[dict[str, Any]] = field(default_factory=list)
    file_dependents: list[dict[str, Any]] = field(default_factory=list)
    data_source: str = "cache"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "symbol": self.symbol,
            "definition_count": len(self.definitions),
            "caller_count": len(self.callers),
            "callee_count": len(self.callees),
            "import_dependent_count": len(self.import_dependents),
            "file_dependent_count": len(self.file_dependents),
            "data_source": self.data_source,
        }
        if self.file_path:
            d["file_path"] = self.file_path
        if self.definitions:
            d["definitions"] = self.definitions
        if self.callers:
            d["callers"] = self.callers
        if self.callees:
            d["callees"] = self.callees
        if self.import_dependents:
            d["import_dependents"] = self.import_dependents
        if self.file_dependents:
            d["file_dependents"] = self.file_dependents
        return d


class XRefEngine:
    """AST-cache-backed cross-reference engine.

    Queries the pre-indexed AST cache (SQLite) for instant symbol cross-
    references without any re-parsing. Combines symbols, call edges, and
    import data into a unified view.
    """

    def __init__(
        self,
        cache: Any,
        backend: Any | None = None,
    ) -> None:
        self._cache = cache
        self._backend = backend or CodeGraphQueryBackend(cache)

    def xref(
        self,
        symbol: str,
        file_path: str | None = None,
        *,
        include_callers: bool = True,
        include_callees: bool = True,
        include_imports: bool = True,
        include_file_deps: bool = True,
    ) -> XRefResult:
        conn = self._cache.get_conn()

        definitions = self._find_definitions(conn, symbol, file_path)
        primary_file = file_path
        if not primary_file and definitions:
            primary_file = definitions[0].get("file")

        callers: list[dict[str, Any]] = []
        if include_callers:
            callers = self._find_callers(conn, symbol, primary_file)

        callees: list[dict[str, Any]] = []
        if include_callees:
            callees = self._find_callees(conn, symbol, primary_file)

        import_dependents: list[dict[str, Any]] = []
        if include_imports and primary_file:
            import_dependents = self._find_import_dependents(conn, primary_file)

        file_dependents: list[dict[str, Any]] = []
        if include_file_deps and primary_file:
            file_dependents = self._find_file_dependents(conn, primary_file)

        return XRefResult(
            symbol=symbol,
            file_path=primary_file,
            definitions=definitions,
            callers=callers,
            callees=callees,
            import_dependents=import_dependents,
            file_dependents=file_dependents,
            data_source="cache",
        )

    def file_xref(self, file_path: str) -> dict[str, Any]:
        conn = self._cache.get_conn()

        symbols = self._file_symbols(conn, file_path)
        callers = self._file_callers(conn, file_path)
        callees = self._file_callees(conn, file_path)
        import_deps = self._find_import_dependents(conn, file_path)
        file_deps = self._find_file_dependents(conn, file_path)

        return {
            "file": file_path,
            "symbol_count": len(symbols),
            "caller_count": len(callers),
            "callee_count": len(callees),
            "import_dependent_count": len(import_deps),
            "file_dependent_count": len(file_deps),
            "symbols": symbols[:50],
            "callers": callers[:50],
            "callees": callees[:50],
            "import_dependents": import_deps,
            "file_dependents": file_deps,
            "data_source": "cache",
        }

    def _find_definitions(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        file_path: str | None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for definition in self._backend.resolve_definitions(symbol):
            if file_path and definition.get("file") != file_path:
                continue
            entry = dict(definition)
            sig = self._get_signature(
                conn,
                str(entry.get("file", "")),
                str(entry.get("name", "")),
                int(entry.get("line", 0) or 0),
            )
            if sig:
                entry["signature"] = sig
            results.append(entry)
            if len(results) >= 20:
                break
        return results

    def _get_signature(
        self,
        conn: sqlite3.Connection,
        file_path: str,
        name: str,
        line: int,
    ) -> str:
        row = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return ""
        syms = json.loads(row["symbols_json"])
        for sym in syms.get("symbols", []):
            if sym.get("name") == name and sym.get("line") == line:
                params = sym.get("params", "")
                return params if isinstance(params, str) else ""
        return ""

    def _find_callers(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        file_path: str | None,
    ) -> list[dict[str, Any]]:
        callers_sql = (
            "SELECT caller_name, file_path AS caller_file, "
            "json_extract(metadata, '$.caller_line') AS caller_line, "
            "callee_name, "
            "json_extract(metadata, '$.callee_full') AS callee_full "
            "FROM edges "
            "WHERE kind = 'calls' "
            "AND (callee_name = ? "
            "OR json_extract(metadata, '$.callee_full') LIKE ?) "
            "ORDER BY caller_file, caller_line LIMIT 50"
        )
        if file_path:
            rows = conn.execute(callers_sql, (symbol, f"%{symbol}%")).fetchall()
        else:
            rows = conn.execute(callers_sql, (symbol, f"%{symbol}%")).fetchall()

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for row in rows:
            key = f"{row['caller_file']}:{row['caller_name']}:{row['caller_line']}"
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "name": row["caller_name"],
                    "file": row["caller_file"],
                    "line": row["caller_line"],
                    "calls_via": row["callee_full"],
                }
            )
        return results

    def _find_callees(
        self,
        conn: sqlite3.Connection,
        symbol: str,
        file_path: str | None,
    ) -> list[dict[str, Any]]:
        callee_cols = (
            "SELECT callee_name, "
            "json_extract(metadata, '$.callee_full') AS callee_full, "
            "line AS callee_line, file_path, "
            "json_extract(metadata, '$.language') AS language "
            "FROM edges "
        )
        if file_path:
            rows = conn.execute(
                callee_cols
                + "WHERE kind = 'calls' AND caller_name = ? AND file_path = ? "
                "ORDER BY callee_line LIMIT 50",
                (symbol, file_path),
            ).fetchall()
        else:
            rows = conn.execute(
                callee_cols + "WHERE kind = 'calls' AND caller_name = ? "
                "ORDER BY file_path, callee_line LIMIT 50",
                (symbol,),
            ).fetchall()

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for row in rows:
            callee = row["callee_name"] or row["callee_full"]
            key = f"{row['file_path']}:{callee}:{row['callee_line']}"
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "name": callee,
                    "full_name": row["callee_full"],
                    "called_at_line": row["callee_line"],
                    "from_file": row["file_path"],
                    "language": row["language"],
                }
            )
        return results

    def _find_import_dependents(
        self,
        conn: sqlite3.Connection,
        file_path: str,
    ) -> list[dict[str, Any]]:
        module_name = self._file_to_module(file_path)
        if not module_name:
            return []

        rows = conn.execute("SELECT file_path, imports_json FROM ast_index").fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            if row["file_path"] == file_path:
                continue
            imports = json.loads(row["imports_json"])
            for imp in imports:
                if (
                    module_name in imp
                    or file_path.rstrip(".py").replace("/", ".") in imp
                ):
                    results.append(
                        {
                            "file": row["file_path"],
                            "imports_via": imp,
                        }
                    )
                    break
        return results

    def _file_defined_names(
        self,
        conn: sqlite3.Connection,
        file_path: str,
    ) -> list[str]:
        """Callable symbol names defined in ``file_path`` (function/method/class).

        Inbound xref (callers / file-dependents) resolves by these names — the
        same name-based precision symbol-mode ``_find_callers`` uses.
        """
        return [s["name"] for s in self._file_symbols(conn, file_path) if s.get("name")]

    def _inbound_edge_rows(
        self,
        conn: sqlite3.Connection,
        names: list[str],
        file_path: str,
        prefix: str,
        suffix: str,
    ) -> list[sqlite3.Row]:
        """Run a chunked inbound-edge query and concatenate the rows.

        ``names`` is chunked under SQLite's 999 bound-variable cap so a file
        with ~1000+ symbols doesn't raise ``too many SQL variables``. Each chunk
        binds ``(*chunk, file_path, file_path)``. ``prefix``/``suffix`` are
        constant SQL fragments (B608: no user data in the string); callers
        dedup + order + cap across chunks.
        """
        rows: list[sqlite3.Row] = []
        for start in range(0, len(names), _XREF_NAME_CHUNK):
            chunk = names[start : start + _XREF_NAME_CHUNK]
            placeholders = ",".join("?" * len(chunk))
            rows.extend(
                conn.execute(
                    prefix + placeholders + suffix,
                    (*chunk, file_path, file_path),
                ).fetchall()
            )
        return rows

    def _find_file_dependents(
        self,
        conn: sqlite3.Connection,
        file_path: str,
    ) -> list[dict[str, Any]]:
        # Inbound: distinct OTHER files whose call edges target a symbol defined
        # in this file. (The prior query selected edges where this file is the
        # CALLER, then discarded every row as same-file — always empty.)
        names = self._file_defined_names(conn, file_path)
        if not names:
            return []
        # Bind a ``?``-only placeholders variable between named prefix/suffix
        # constants (no user data in the SQL string) so the security scanner
        # doesn't flag the SELECT — same B608 convention as _route_cache.py.
        _fd_prefix = (
            "SELECT DISTINCT file_path AS caller_file FROM edges "
            "WHERE kind = 'calls' AND callee_name IN ("
        )
        # callee_resolved_file gate (Codex P2): count ONLY edges the resolver
        # tied to THIS file. No unresolved ('') fallback — an unresolved
        # `'x'.format()` call would otherwise inflate any file defining `format`
        # (resolved inbound only; under-count beats over-count for blast radius).
        _fd_suffix = (
            ") AND file_path != ? AND callee_resolved_file = ? ORDER BY caller_file"
        )
        rows = self._inbound_edge_rows(conn, names, file_path, _fd_prefix, _fd_suffix)
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for caller_file in sorted(row["caller_file"] for row in rows):
            if caller_file in seen:
                continue
            seen.add(caller_file)
            out.append({"file": caller_file})
            if len(out) >= 50:
                break
        return out

    def _file_symbols(
        self,
        conn: sqlite3.Connection,
        file_path: str,
    ) -> list[dict[str, Any]]:
        row = conn.execute(
            "SELECT symbols_json, language FROM ast_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return []
        syms = json.loads(row["symbols_json"])
        results: list[dict[str, Any]] = []
        for sym in syms.get("symbols", []):
            # "method" is the in-class callable kind (added with method
            # classification). Without it, codegraph_xref file mode would omit
            # every method and undercount files that contain only methods.
            if sym.get("kind") in ("function", "method", "class"):
                results.append(
                    {
                        "name": sym.get("name", ""),
                        "kind": sym["kind"],
                        "line": sym.get("line", 0),
                    }
                )
        return results

    def _file_callers(
        self,
        conn: sqlite3.Connection,
        file_path: str,
    ) -> list[dict[str, Any]]:
        # Inbound call sites in OTHER files whose callee resolves to a symbol
        # defined in this file. (The prior `file_path = ? AND file_path != ?`
        # predicate bound both to the same value — structurally always empty.)
        names = self._file_defined_names(conn, file_path)
        if not names:
            return []
        # ``?``-only placeholders between named prefix/suffix — B608 convention.
        _fc_prefix = (
            "SELECT DISTINCT caller_name, file_path AS caller_file, "
            "json_extract(metadata, '$.caller_line') AS caller_line, callee_name "
            "FROM edges WHERE kind = 'calls' AND callee_name IN ("
        )
        # callee_resolved_file gate (Codex P2): resolved-to-this-file rows ONLY,
        # no unresolved ('') fallback (an unresolved str.format() call would
        # otherwise be credited to any file defining `format`).
        _fc_suffix = (
            ") AND file_path != ? AND callee_resolved_file = ? "
            "ORDER BY caller_file, caller_line"
        )
        rows = self._inbound_edge_rows(conn, names, file_path, _fc_prefix, _fc_suffix)
        seen: set[tuple[str, str, Any]] = set()
        out: list[dict[str, Any]] = []
        for row in sorted(
            rows, key=lambda r: (r["caller_file"], r["caller_line"] or 0)
        ):
            key = (row["caller_file"], row["caller_name"], row["caller_line"])
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(row))
            if len(out) >= 50:
                break
        return out

    def _file_callees(
        self,
        conn: sqlite3.Connection,
        file_path: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT DISTINCT callee_name, "
            "json_extract(metadata, '$.callee_full') AS callee_full, "
            "line AS callee_line "
            "FROM edges "
            "WHERE kind = 'calls' AND file_path = ? "
            "LIMIT 50",
            (file_path,),
        ).fetchall()
        return [
            {
                "name": row["callee_name"] or row["callee_full"],
                "full_name": row["callee_full"],
                "line": row["callee_line"],
            }
            for row in rows
        ]

    @staticmethod
    def _file_to_module(file_path: str) -> str:
        p = file_path
        if p.endswith("/__init__.py"):
            return p[: -len("/__init__.py")].replace("/", ".")
        if p.endswith(".py"):
            return p[:-3].replace("/", ".")
        return p.replace("/", ".")
