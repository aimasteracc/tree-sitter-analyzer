"""Write helper functions for ASTCache indexing pipeline.

Pure functions extracted from ASTCache._write_* methods to reduce
ast_cache.py line count. Each takes explicit parameters instead of self.

ASTCache keeps thin wrapper methods that delegate here.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def write_fts5_symbols(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbols: dict[str, Any],
) -> list[dict[str, Any]]:
    """Replace FTS5 symbol rows for ``rel_path``. Returns inserted row list."""
    conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel_path,))
    conn.execute("DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel_path,))
    sym_list = symbols.get("symbols", [])
    if not sym_list:
        return []
    sym_params = [
        (
            sym.get("name") or sym.get("text", ""),
            sym.get("kind", "unknown"),
            rel_path,
            language,
            sym.get("line", 0),
            sym.get("end_line", 0),
        )
        for sym in sym_list
    ]
    conn.executemany(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        sym_params,
    )
    start_id = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE file_path = ? ORDER BY id ASC LIMIT 1",
        (rel_path,),
    ).fetchone()
    base_id = start_id[0] if start_id else 0
    # #614: docstring tokens enter the FTS docstring column (low bm25 weight).
    fts_params = [
        (base_id + i, p[0], p[1], rel_path, language, sym.get("docstring", ""))
        for i, (p, sym) in enumerate(zip(sym_params, sym_list, strict=True))
    ]
    conn.executemany(
        "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language, docstring) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        fts_params,
    )
    return [
        {"id": base_id + i, "line": p[4], "end_line": p[5]}
        for i, p in enumerate(sym_params)
    ]


def write_fts5_symbols_from_tuples(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbol_rows: list[tuple[str, str, int, int, str]],
) -> list[dict[str, Any]]:
    """Insert FTS5 symbols from worker-serialised tuples
    (name, kind, line, end_line, docstring) — docstring added by #614."""
    conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel_path,))
    conn.execute("DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel_path,))
    if not symbol_rows:
        return []
    inserted: list[dict[str, Any]] = []
    sym_params = [
        (n, k, rel_path, language, ln, el) for n, k, ln, el, _d in symbol_rows
    ]
    conn.executemany(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        sym_params,
    )
    start_id = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE file_path = ? ORDER BY id ASC LIMIT 1",
        (rel_path,),
    ).fetchone()
    base_id = start_id[0] if start_id else 0
    fts_params = [
        (base_id + i, n, k, rel_path, language, d)
        for i, (n, k, _ln, _el, d) in enumerate(symbol_rows)
    ]
    conn.executemany(
        "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language, docstring) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        fts_params,
    )
    for i, (_n, _k, ln, el, _d) in enumerate(symbol_rows):
        inserted.append(
            {
                "id": base_id + i,
                "line": ln,
                "end_line": el,
            }
        )
    return inserted


def _parse_import_raw(raw: Any) -> tuple[str, int]:
    """Extract (text, line) from a raw import entry (str or dict)."""
    if isinstance(raw, dict):
        text = raw.get("text") or raw.get("statement") or ""
        line = int(raw.get("line", 0) or 0)
    else:
        text = str(raw)
        line = 0
    return text, line


def _insert_import_entry(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    entry: Any,
) -> bool:
    """Insert one parsed import entry into ast_imports.

    Returns True on success, False when a fatal OperationalError fires.
    """
    try:
        conn.execute(
            """INSERT INTO ast_imports
               (file_path, language, module_path, local_name,
                is_relative, is_star, alias_of)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                rel_path,
                language,
                entry.module_path,
                entry.local_name,
                1 if entry.is_relative else 0,
                1 if entry.is_star else 0,
                entry.alias_of,
            ),
        )
        return True
    except sqlite3.OperationalError as exc:
        logger.debug("ast_imports write failed for %s: %s", rel_path, exc)
        return False


def write_activation_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    inserted_symbol_rows: list[dict[str, Any]],
    project_root: str,
) -> None:
    """Refresh ast_symbol_activation rows for a single file."""
    if not inserted_symbol_rows:
        try:
            conn.execute(
                "DELETE FROM ast_symbol_activation WHERE file_path = ?",
                (rel_path,),
            )
        except sqlite3.OperationalError:
            pass
        return
    try:
        from . import git_activation
    except Exception as exc:  # pragma: no cover
        logger.debug("git_activation import failed: %s", exc)
        return
    if git_activation._activation_disabled():  # noqa: SLF001
        return
    try:
        rows = git_activation.compute_symbol_activation(
            file_path=os.path.join(project_root, rel_path),
            symbols=inserted_symbol_rows,
            repo_root=project_root,
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("compute_symbol_activation failed for %s: %s", rel_path, exc)
        return
    try:
        conn.execute(
            "DELETE FROM ast_symbol_activation WHERE file_path = ?",
            (rel_path,),
        )
        for r in rows:
            conn.execute(
                """INSERT OR REPLACE INTO ast_symbol_activation (
                    symbol_id, file_path,
                    last_modified_commit, last_modified_at,
                    mod_count_30d, mod_count_90d, mod_count_all,
                    computed_at, git_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(r.symbol_id),
                    rel_path,
                    r.last_modified_commit,
                    r.last_modified_at,
                    int(r.mod_count_30d),
                    int(r.mod_count_90d),
                    int(r.mod_count_all),
                    int(r.computed_at),
                    r.git_state,
                ),
            )
    except sqlite3.OperationalError as exc:
        logger.debug("activation write failed for %s: %s", rel_path, exc)


def write_imports_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    imports: list[str] | list[dict[str, Any]],
) -> None:
    """Refresh ast_imports rows for rel_path."""
    try:
        from .synapse_resolver import parse_imports
    except Exception as exc:  # pragma: no cover
        logger.debug("synapse_resolver import failed: %s", exc)
        return
    try:
        conn.execute("DELETE FROM ast_imports WHERE file_path = ?", (rel_path,))
    except sqlite3.OperationalError:
        return
    for raw in imports or []:
        text, line = _parse_import_raw(raw)
        if not text:
            continue
        for entry in parse_imports(text, language, rel_path, line):
            if not _insert_import_entry(conn, rel_path, language, entry):
                return


def write_graph_edges_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbols: dict[str, Any],
    imports: list[str] | list[dict[str, Any]],
    call_edges: list[dict[str, Any]],
    *,
    preserve_calls: bool = False,
) -> None:
    """Refresh unified EdgeStore rows derived from one indexed file.

    ``preserve_calls=True`` rebuilds only the structural edges (EXTENDS /
    CONTAINS / IMPORTS) and leaves existing CALLS rows — with their second-pass
    resolution columns — untouched. Used by ``_refresh_graph_edges_from_cache``,
    which (post-B1.3) has no extracted call-edge source to rebuild calls from.
    """
    try:
        from .graph.edge_store import (
            Edge,
            EdgeKind,
            EdgeStore,
            class_node,
            file_node,
            module_node,
            symbol_node,
        )
        from .synapse_resolver import parse_imports
    except Exception as exc:  # pragma: no cover
        logger.debug("edge store import failed for %s: %s", rel_path, exc)
        return

    symbol_items = symbols.get("symbols", [])
    class_nodes = {
        sym.get("name", ""): symbol_node(rel_path, sym.get("name", ""), sym.get("line"))
        for sym in symbol_items
        if sym.get("kind") == "class" and sym.get("name")
    }
    edges: list[Edge] = []

    for edge in call_edges:
        caller_name = edge.get("caller_name", "")
        source = (
            symbol_node(rel_path, caller_name, edge.get("caller_line"))
            if caller_name
            else file_node(rel_path)
        )
        callee_name = edge.get("callee_name", "")
        resolved_file = str(edge.get("callee_resolved_file") or "")
        target_file = resolved_file or rel_path
        target = symbol_node(target_file, callee_name, edge.get("callee_line"))
        edges.append(
            Edge(
                source,
                target,
                EdgeKind.CALLS,
                edge.get("callee_line"),
                metadata={
                    "language": language,
                    "caller_name": caller_name,
                    "caller_line": edge.get("caller_line", 0),
                    "callee_name": callee_name,
                    "callee_full": edge.get("callee_full", ""),
                    "callee_resolution": edge.get("callee_resolution", "unknown"),
                    "callee_resolved_file": resolved_file,
                },
            )
        )

    for raw in imports or []:
        text, line = _parse_import_raw(raw)
        if not text:
            continue
        for entry in parse_imports(text, language, rel_path, line):
            target = module_node(entry.module_path)
            edges.append(
                Edge(
                    file_node(rel_path),
                    target,
                    EdgeKind.IMPORTS,
                    line or entry.line,
                    metadata={
                        "language": language,
                        "local_name": entry.local_name,
                        "is_relative": entry.is_relative,
                        "is_star": entry.is_star,
                        "alias_of": entry.alias_of,
                    },
                )
            )

    for sym in symbol_items:
        if sym.get("kind") in ("function", "method") and sym.get("class"):
            cls_name = sym["class"]
            edges.append(
                Edge(
                    class_nodes.get(cls_name, class_node(cls_name)),
                    symbol_node(rel_path, sym.get("name", ""), sym.get("line")),
                    EdgeKind.CONTAINS,
                    sym.get("line"),
                    metadata={"language": language},
                )
            )
        elif sym.get("kind") == "class" and sym.get("parents"):
            source = class_nodes.get(
                sym.get("name", ""),
                symbol_node(rel_path, sym.get("name", ""), sym.get("line")),
            )
            for parent in sym.get("parents", []):
                base_parent = str(parent).rsplit(".", 1)[-1]
                parent_target = class_nodes.get(str(parent)) or class_nodes.get(
                    base_parent
                )
                edges.append(
                    Edge(
                        source,
                        parent_target or class_node(str(parent)),
                        EdgeKind.EXTENDS,
                        sym.get("line"),
                        metadata={"language": language, "parent": str(parent)},
                    )
                )

    try:
        EdgeStore(conn, ensure_schema=False).replace_edges_for_file(
            rel_path, edges, preserve_calls=preserve_calls
        )
    except sqlite3.OperationalError as exc:
        logger.debug("edge store write failed for %s: %s", rel_path, exc)
