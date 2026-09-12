"""Pure ASTCache write helpers with explicit parameters."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from ..index_symbol_projection import (
    delete_fts_rows as _delete_fts_rows,
)
from ..index_symbol_projection import (
    upsert_symbol_projection_state,
)

logger = logging.getLogger(__name__)
_COMMIT_MSG_CACHE: OrderedDict[tuple[str, str], tuple[float, str | None]] = (
    OrderedDict()
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _delete_symbol_comments(conn: sqlite3.Connection, rel_path: str) -> None:
    """显式清除旧定义的注释；不能依赖所有 SQLite 调用方都启用外键级联。"""
    if _table_exists(conn, "ast_symbol_comments"):
        conn.execute(
            "DELETE FROM ast_symbol_comments WHERE symbol_id IN "
            "(SELECT id FROM ast_symbol_rows WHERE file_path=?) "
            "OR NOT EXISTS (SELECT 1 FROM ast_symbol_rows s WHERE s.id=ast_symbol_comments.symbol_id)",
            (rel_path,),
        )


def _delete_file_rows_if_table_present(
    conn: sqlite3.Connection,
    table: str,
    rel_path: str,
) -> None:
    if _table_exists(conn, table):
        conn.execute(
            f"DELETE FROM {table} WHERE file_path = ?",  # nosec B608
            (rel_path,),
        )


def _reset_incoming_edge_resolutions(
    conn: sqlite3.Connection,
    rel_path: str,
) -> None:
    """Unresolve calls and drop hierarchy edges targeting a removed generation."""
    rows = conn.execute(
        "SELECT id, metadata FROM edges "
        "WHERE kind = 'calls' AND callee_resolved_file = ?",
        (rel_path,),
    ).fetchall()
    for row in rows:
        metadata = json.loads(row["metadata"] or "{}")
        metadata.update(
            {
                "callee_resolution": "unknown",
                "callee_resolved_file": "",
                "callee_symbol_id": None,
            }
        )
        conn.execute(
            "UPDATE edges SET callee_resolution = 'unknown', "
            "callee_resolved_file = '', callee_symbol_id = NULL, metadata = ? "
            "WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), row["id"]),
        )
    target_prefix = f"{rel_path}:"
    conn.execute(
        "DELETE FROM edges WHERE kind IN ('extends', 'implements') "
        "AND target_node_id >= ? AND target_node_id < ?",
        (target_prefix, target_prefix + "\U0010ffff"),
    )


def discard_file_rows(
    conn: sqlite3.Connection,
    rel_path: str,
    fts5_available: bool | None,
) -> bool:
    """Remove one file generation without committing the current transaction."""
    # Resolver contexts retain symbol-row IDs and project targets independently
    # of SQLite transactions.  Clear them before the first mutation so the
    # ensuing pipeline cannot resurrect a deleted/replaced generation.
    _clear_symbol_resolver_context()
    if fts5_available:
        _delete_fts_rows(conn, rel_path)
    _delete_symbol_comments(conn, rel_path)
    _delete_file_rows_if_table_present(conn, "ast_symbol_rows", rel_path)
    _delete_file_rows_if_table_present(conn, "ast_symbol_projection_state", rel_path)
    for table in ("ast_imports", "ast_symbol_activation"):
        _delete_file_rows_if_table_present(conn, table, rel_path)
    if _table_exists(conn, "edges"):
        from ..graph.edge_store import EdgeStore

        EdgeStore(conn, ensure_schema=False).replace_edges_for_file(rel_path, [])
        _reset_incoming_edge_resolutions(conn, rel_path)
    cursor = conn.execute(
        "DELETE FROM ast_index WHERE file_path = ?",
        (rel_path,),
    )
    return cursor.rowcount > 0


def invalidate_file_rows(
    conn: sqlite3.Connection,
    rel_path: str,
    fts5_available: bool | None,
) -> bool:
    """Remove one file's primary and derived cache rows."""
    changes_before = conn.total_changes
    try:
        removed = discard_file_rows(conn, rel_path, fts5_available)
        if conn.total_changes > changes_before:
            from .callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return removed


def _clear_symbol_resolver_context() -> None:
    """Invalidate resolver snapshots containing replaced symbol-row IDs."""
    from ..synapse_resolver._context import clear_resolver_context_cache

    clear_resolver_context_cache()


def write_fts5_symbols(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbols: dict[str, Any],
    fts5_available: bool = True,
) -> list[dict[str, Any]]:
    """Replace ordinary symbol rows and, when available, their FTS projection."""
    _clear_symbol_resolver_context()
    if _table_exists(conn, "edges"):
        _reset_incoming_edge_resolutions(conn, rel_path)
    if fts5_available:
        _delete_fts_rows(conn, rel_path)
    _delete_symbol_comments(conn, rel_path)
    conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel_path,))
    sym_list = symbols.get("symbols", [])
    if not sym_list:
        upsert_symbol_projection_state(conn, rel_path)
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
    fts_params = [
        (base_id + i, p[0], p[1], rel_path, language) for i, p in enumerate(sym_params)
    ]
    if fts5_available:
        conn.executemany(
            "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language) "
            "VALUES (?, ?, ?, ?, ?)",
            fts_params,
        )
    upsert_symbol_projection_state(conn, rel_path)
    return [
        {"id": base_id + i, "line": p[4], "end_line": p[5]}
        for i, p in enumerate(sym_params)
    ]


def write_fts5_symbols_from_tuples(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbol_rows: list[tuple[str, str, int, int]],
    fts5_available: bool = True,
) -> list[dict[str, Any]]:
    """Insert ordinary worker symbol rows and optional FTS projection."""
    _clear_symbol_resolver_context()
    if _table_exists(conn, "edges"):
        _reset_incoming_edge_resolutions(conn, rel_path)
    if fts5_available:
        _delete_fts_rows(conn, rel_path)
    _delete_symbol_comments(conn, rel_path)
    conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel_path,))
    if not symbol_rows:
        upsert_symbol_projection_state(conn, rel_path)
        return []
    inserted: list[dict[str, Any]] = []
    sym_params = [(n, k, rel_path, language, ln, el) for n, k, ln, el in symbol_rows]
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
        (base_id + i, n, k, rel_path, language)
        for i, (n, k, _ln, _el) in enumerate(symbol_rows)
    ]
    if fts5_available:
        conn.executemany(
            "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language) "
            "VALUES (?, ?, ?, ?, ?)",
            fts_params,
        )
    upsert_symbol_projection_state(conn, rel_path)
    for i, (_n, _k, ln, el) in enumerate(symbol_rows):
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
                is_relative, is_star, alias_of, line)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel_path,
                language,
                entry.module_path,
                entry.local_name,
                1 if entry.is_relative else 0,
                1 if entry.is_star else 0,
                entry.alias_of,
                entry.line,
            ),
        )
        return True
    except sqlite3.OperationalError as exc:
        logger.debug("ast_imports write failed for %s: %s", rel_path, exc)
        return False


def _fetch_commit_msgs(shas: list[str], repo_root: str) -> dict[str, str]:
    """有界批量读取不可变 SHA 的消息，跨文件缓存；缺失值不伪造为空串。"""
    from ..git_readonly import run_git_readonly
    from ..source_oracle import SourceOracleError

    root = os.path.realpath(repo_root)
    requested = list(
        dict.fromkeys(s for s in shas if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", s))
    )
    now = time.monotonic()
    pending = [
        s
        for s in requested
        if (root, s) not in _COMMIT_MSG_CACHE or _COMMIT_MSG_CACHE[(root, s)][0] < now
    ]
    deadline = now + 5.0
    for offset in range(0, min(len(pending), 4096), 256):
        batch = pending[offset : offset + 256]
        found: dict[str, str] = {}
        try:
            raw = run_git_readonly(
                root,
                ["log", "--no-walk", "--stdin", "--format=%H%x00%s%x00"],
                deadline=deadline,
                limit=1024 * 1024,
                input_=("\n".join(batch) + "\n").encode("ascii"),
            )
            fields = raw.decode("utf-8", errors="replace").split("\0")
            for i in range(0, len(fields) - 1, 2):
                sha = fields[i].strip()
                if sha in batch:
                    found[sha] = fields[i + 1][:120]
        except (SourceOracleError, OSError) as exc:
            logger.warning("COMMIT_MESSAGE_MISSING: %s", exc)
        for sha in batch:
            message = found.get(sha)
            _COMMIT_MSG_CACHE[(root, sha)] = (
                float("inf") if message is not None else now + 60,
                message,
            )
            _COMMIT_MSG_CACHE.move_to_end((root, sha))
        while len(_COMMIT_MSG_CACHE) > 4096:
            _COMMIT_MSG_CACHE.popitem(last=False)
        if time.monotonic() >= deadline:
            break
    result: dict[str, str] = {}
    for sha in requested:
        cached = _COMMIT_MSG_CACHE.get((root, sha))
        if cached is not None and cached[1] is not None:
            result[sha] = cached[1]
    if len(result) != len(requested):
        logger.warning(
            "COMMIT_MESSAGE_MISSING: %d SHA(s)", len(requested) - len(result)
        )
    return result


def write_activation_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    inserted_symbol_rows: list[dict[str, Any]],
    project_root: str,
) -> None:
    """只写 pending/disabled 占位行，Git 与提交消息统一延迟到 flush。"""
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
        from .. import git_activation
    except Exception as exc:  # pragma: no cover
        logger.debug("git_activation import failed: %s", exc)
        return
    # disabled 也保留显式占位，不能把缺行误当成完成计算。
    state = "disabled" if git_activation._activation_disabled() else "pending"  # noqa: SLF001
    try:
        conn.execute(
            "DELETE FROM ast_symbol_activation WHERE file_path = ?",
            (rel_path,),
        )
        for r in inserted_symbol_rows:
            conn.execute(
                """INSERT OR REPLACE INTO ast_symbol_activation (
                    symbol_id, file_path,
                    last_modified_commit, last_modified_at,
                    mod_count_30d, mod_count_90d, mod_count_all,
                    computed_at, git_state, activation_state, last_commit_msg
                ) VALUES (?, ?, NULL, NULL, 0, 0, 0, 0, NULL, ?, NULL)""",
                (int(r["id"]), rel_path, state),
            )
    except sqlite3.OperationalError as exc:
        logger.debug("activation write failed for %s: %s", rel_path, exc)


def _flush_pending_activations(
    conn: sqlite3.Connection,
    project_root: str,
    batch_size: int = 50,
) -> dict[str, int]:
    """有界刷新 pending：DB 故障回滚重试，消息缺失保留 pending，disabled 不动。

    Git 计算异常保留 canonical 的 computed/零值降级，但不伪造有效 git_state。
    提交消息通过共享 SHA 批次及负缓存读取；返回 flushed/errors 数量。
    """
    from .. import git_activation

    if git_activation._activation_disabled():
        # 暂停计算不等于完成；旧 pending 留给显式重新启用后的刷新。
        return {"flushed": 0, "errors": 0}

    try:
        pending_paths = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT file_path FROM ast_symbol_activation"
                " WHERE activation_state = 'pending'"
                " LIMIT ?",
                (batch_size,),
            ).fetchall()
        ]
    except sqlite3.DatabaseError:
        # 查询失败代表队列不可用，不等于没有工作；已初始化的 schema 必须包含该列。
        return {"flushed": 0, "errors": 1}

    flushed = 0
    errors = 0
    for rel_path in pending_paths:
        try:
            # 同一快照内读身份并发布，另一连接重索引时由 SQLite 拒绝旧快照写回。
            conn.execute("SAVEPOINT tsa_activation_flush")
            sym_rows = conn.execute(
                "SELECT s.id, s.line, s.end_line FROM ast_symbol_rows s "
                "JOIN ast_symbol_activation a ON a.symbol_id=s.id "
                "WHERE s.file_path=? AND a.activation_state='pending'",
                (rel_path,),
            ).fetchall()
            symbols = [{"id": r[0], "line": r[1], "end_line": r[2]} for r in sym_rows]
            try:
                activation_rows = git_activation.compute_symbol_activation(
                    os.path.join(project_root, rel_path),
                    symbols,
                    repo_root=project_root,
                )
            except Exception as exc:
                # 仅 Git 计算失败使用既有零值降级；数据库失败必须保留 pending。
                logger.debug(
                    "git activation computation failed for %s: %s", rel_path, exc
                )
                conn.execute(
                    "UPDATE ast_symbol_activation SET activation_state='computed', "
                    "last_modified_commit=NULL,last_modified_at=NULL,last_commit_msg=NULL, "
                    "mod_count_30d=0,mod_count_90d=0,mod_count_all=0,computed_at=0,git_state=NULL "
                    "WHERE file_path=? AND activation_state='pending'",
                    (rel_path,),
                )
                conn.commit()
                errors += 1
                continue
            shas = [
                r.last_modified_commit
                for r in activation_rows
                if r.last_modified_commit
            ]
            commit_msgs = _fetch_commit_msgs(shas, project_root)
            if any(sha not in commit_msgs for sha in shas):
                conn.execute("RELEASE SAVEPOINT tsa_activation_flush")
                errors += 1
                continue
            # 消息与统计共同写入；不能先宣称 computed 再补消息。
            for r in activation_rows:
                conn.execute(
                    """UPDATE ast_symbol_activation
                       SET last_modified_commit = ?,
                           last_modified_at = ?,
                           mod_count_30d = ?,
                           mod_count_90d = ?,
                           mod_count_all = ?,
                           computed_at = ?,
                            git_state = ?,
                            last_commit_msg = ?,
                            activation_state = 'computed'
                       WHERE file_path = ? AND symbol_id = ? AND activation_state='pending'""",
                    (
                        r.last_modified_commit,
                        r.last_modified_at,
                        int(r.mod_count_30d),
                        int(r.mod_count_90d),
                        int(r.mod_count_all),
                        int(r.computed_at),
                        r.git_state,
                        commit_msgs.get(r.last_modified_commit or ""),
                        rel_path,
                        int(r.symbol_id),
                    ),
                )
            # 没有 Git 记录的占位行仍按 canonical 语义完成，不改 disabled。
            conn.execute(
                """UPDATE ast_symbol_activation
                   SET activation_state = 'computed'
                   WHERE file_path = ? AND activation_state = 'pending'""",
                (rel_path,),
            )
            conn.commit()
            flushed += 1
        except sqlite3.DatabaseError as exc:
            logger.debug("_flush_pending_activations failed for %s: %s", rel_path, exc)
            conn.rollback()
            errors += 1
        except BaseException:
            conn.rollback()
            raise

    return {"flushed": flushed, "errors": errors}


def write_imports_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    imports: list[str] | list[dict[str, Any]],
) -> None:
    """Refresh ast_imports rows for rel_path."""
    try:
        from ..synapse_resolver import parse_imports
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


#: Languages whose import specifiers are importer-relative, so the resolved
#: file must be computed at index time rather than derived from the target.
_RELATIVE_SPECIFIER_LANGUAGES = ("typescript", "javascript")


def _import_specifier_resolver(
    conn: sqlite3.Connection, language: str
) -> Callable[[str, str], str]:
    """Return a ``(specifier, importer) -> resolved_file`` callable.

    Languages without importer-relative specifiers get a no-op resolver, so
    Python keeps matching through its module-name branch unchanged.
    """
    if language not in _RELATIVE_SPECIFIER_LANGUAGES:
        return lambda specifier, importer: ""
    try:
        from ..synapse_resolver._typescript_imports import (
            resolve_typescript_specifier,
        )

        indexed = {
            str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")
        }
    except Exception as exc:  # pragma: no cover - resolution is best-effort
        logger.debug("import specifier resolver unavailable: %s", exc)
        return lambda specifier, importer: ""

    def resolve(specifier: str, importer: str) -> str:
        return resolve_typescript_specifier(specifier, importer, indexed)

    return resolve


def write_graph_edges_for_file(
    conn: sqlite3.Connection,
    rel_path: str,
    language: str,
    symbols: dict[str, Any],
    imports: list[str] | list[dict[str, Any]],
    call_edges: list[dict[str, Any]],
    *,
    preserve_calls: bool = False,
) -> bool:
    """Refresh unified EdgeStore rows derived from one indexed file.

    ``preserve_calls=True`` rebuilds only the structural edges (EXTENDS /
    CONTAINS / IMPORTS) and leaves existing CALLS rows — with their second-pass
    resolution columns — untouched. Used by ``_refresh_graph_edges_from_cache``,
    which (post-B1.3) has no extracted call-edge source to rebuild calls from.
    """
    try:
        from ..graph.edge_store import (
            Edge,
            EdgeKind,
            EdgeStore,
            class_node,
            file_node,
            module_node,
            symbol_node,
        )
        from ..synapse_resolver import parse_imports
    except Exception as exc:  # pragma: no cover
        logger.debug("edge store import failed for %s: %s", rel_path, exc)
        return False

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
        edge_metadata: dict[str, Any] = {
            "language": language,
            "caller_name": caller_name,
            "caller_line": edge.get("caller_line", 0),
            "callee_name": callee_name,
            "callee_full": edge.get("callee_full", ""),
            "callee_resolution": edge.get("callee_resolution", "unknown"),
            "callee_resolved_file": resolved_file,
        }
        branch_ctx = edge.get("branch")
        if branch_ctx is not None:
            edge_metadata["branch"] = branch_ctx
        edges.append(
            Edge(
                source,
                target,
                EdgeKind.CALLS,
                edge.get("callee_line"),
                metadata=edge_metadata,
            )
        )

    resolve_specifier = _import_specifier_resolver(conn, language)
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
                        # Importer-relative specifiers cannot be derived from
                        # the target, so resolve here and let the query match
                        # on the language-neutral resolved-file column.
                        "callee_resolved_file": resolve_specifier(
                            entry.module_path, rel_path
                        ),
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
        if "comments" in symbols and _table_exists(conn, "ast_symbol_comments"):
            _delete_symbol_comments(conn, rel_path)
            owners = conn.execute(
                "SELECT id, line, end_line FROM ast_symbol_rows WHERE file_path=? "
                "AND kind IN ('function','method','class') ORDER BY end_line-line, line DESC, id",
                (rel_path,),
            ).fetchall()
            for comment in symbols["comments"]:
                matches = [s for s in owners if s[1] <= comment["line"] <= s[2]]
                if matches:
                    conn.execute(
                        "INSERT INTO ast_symbol_comments(symbol_id,line,text,kind) VALUES (?,?,?,?)",
                        (
                            matches[0][0],
                            comment["line"],
                            comment["text"],
                            comment["kind"],
                        ),
                    )
        EdgeStore(conn, ensure_schema=False).replace_edges_for_file(
            rel_path, edges, preserve_calls=preserve_calls
        )
    except sqlite3.OperationalError as exc:
        logger.debug("edge store write failed for %s: %s", rel_path, exc)
        return False
    return True
