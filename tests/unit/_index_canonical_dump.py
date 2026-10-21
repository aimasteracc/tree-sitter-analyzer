"""索引内容的规范化转储：增量刷新与全新重建的逐表比较（#1671 / #1673 等价门）。

查询可见表逐行转储为有序列表，只排除与内容无关的列。排除项（精确清单）：

时间戳
  * ``ast_index.indexed_at``、``ast_index.certified_at``（保留“是否已认证”）
  * ``ast_symbol_activation.computed_at``
  * ``ast_constraint_violations.detected_at``
  * ``lsp_resolution_cache.cached_at``
  * ``ast_schema_version.applied_at``
  * ``ast_call_graph_state.built_at``、``ast_build_state.started_at`` 与 ``pid``；
    ``ast_build_state`` 中 ``building = 0`` 的行与无行同义（强制重建结束后留下
    该行，增量首建不写），不参与比较
  * ``ast_resolve_state.fingerprint``（值为 ``<行数>:<max(indexed_at)>``，由时间戳派生）
  * ``ast_index_snapshot_manifest.index_fingerprint``（覆盖上面各时间戳列的摘要）

版本 / 写入身份
  * ``ast_writer_state``（缓存 UUID 与写入修订号，RFC-0032）
  * ``ast_certification_leaves``（RFC-0039 认证树的叶：由含时间戳的行派生）
  * ``ast_certification_state``（RFC-0039 校验计划：增量盖章次数与时间）
  * ``sqlite_sequence``（AUTOINCREMENT 计数器）

代理键（不丢弃，而是映射为自然键后比较）
  * ``ast_symbol_rows.id`` → ``(file_path, name, kind, line, end_line, language)``，
    ``edges.callee_symbol_id``、``ast_symbol_comments.symbol_id``、
    ``ast_symbol_activation.symbol_id``、``lsp_resolution_cache.symbol_id`` 与
    FTS 文档 rowid 都按此映射
  * ``edges.id`` → ``(source_node_id, target_node_id, kind, line)``；
    ``ast_imports.id``、``ast_symbol_comments.id`` 直接省略（无外部引用）
  * ``edges.metadata`` JSON 内的 ``callee_symbol_id`` / ``resolved_symbol_id`` /
    ``symbol_id`` 同样映射为符号自然键（JSON 按键排序重排，其余字段不变）
  * ``ast_symbol_projection_state.projection_digest`` 是按 ``id`` 顺序对该文件
    符号行（含 ``id``）的摘要，随代理键变化；改为在同一库内用
    ``symbol_rows_digest`` 重新计算，只比较“与实际行一致”这一布尔值

FTS5 影子表（``ast_symbols_fts_*``）的 B 树布局取决于写入历史，不可比较；改为用
``fts5vocab(instance)`` 转储完整倒排索引（词项、文档、列、偏移），文档按上面的
符号自然键映射。其余列（含 ``mtime_ns``、``file_size``、内容摘要、全部 JSON）全部比较。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

EXCLUDED_TABLES = frozenset(
    {
        "ast_writer_state",
        "sqlite_sequence",
        "ast_certification_leaves",
        "ast_certification_state",
    }
)
EXCLUDED_COLUMNS = {
    "ast_index": {"indexed_at", "certified_at"},
    "ast_symbol_activation": {"computed_at"},
    "ast_constraint_violations": {"detected_at"},
    "lsp_resolution_cache": {"cached_at"},
    "ast_schema_version": {"applied_at"},
    "ast_call_graph_state": {"built_at"},
    "ast_build_state": {"started_at", "pid"},
    "ast_resolve_state": {"fingerprint"},
    "ast_index_snapshot_manifest": {"index_fingerprint"},
    "ast_imports": {"id"},
    "ast_symbol_comments": {"id"},
}
_SYMBOL_ID_COLUMNS = {
    "edges": "callee_symbol_id",
    "ast_symbol_comments": "symbol_id",
    "ast_symbol_activation": "symbol_id",
    "lsp_resolution_cache": "symbol_id",
}


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _sorted(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return sorted(rows, key=repr)


def canonical_dump(
    database: Path | str, *, project_root: str | None = None
) -> dict[str, list[tuple[Any, ...]]]:
    """返回 ``{表名: 有序行}``；只读打开，不修改数据库。

    给出 ``project_root`` 时，``ast_index`` 的 ``(mtime_ns, file_size)`` 取合并
    ``cache.stat_evidence`` 之后的值（#1707：只有 mtime 变化的零变化刷新不发布，
    新戳记记在 stat 证据里；读者按同一规则合并，见 ``stat_evidence.effective_stamp``）。
    """
    conn = sqlite3.connect(Path(database).as_uri() + "?mode=ro", uri=True)
    try:
        dump = _dump(conn)
        if project_root is not None and "ast_index" in dump:
            columns = [
                c
                for c in _columns(conn, "ast_index")
                if c not in EXCLUDED_COLUMNS["ast_index"]
            ]
            dump["ast_index"] = _sorted(
                [_effective(project_root, columns, row) for row in dump["ast_index"]]
            )
        return dump
    finally:
        conn.close()


def _effective(
    project_root: str, columns: list[str], row: tuple[Any, ...]
) -> tuple[Any, ...]:
    import os

    from tree_sitter_analyzer.cache import stat_evidence

    values = dict(zip(columns, row[: len(columns)], strict=True))
    try:
        info = os.stat(os.path.join(project_root, str(values["file_path"])))
        live: tuple[int, int] | None = (info.st_mtime_ns, info.st_size)
    except OSError:
        live = None
    mtime_ns, size = stat_evidence.effective_stamp(
        stat_evidence.load(project_root),
        str(values["file_path"]),
        (values["mtime_ns"], values["file_size"], str(values["content_hash"])),
        live,
    )
    values["mtime_ns"], values["file_size"] = mtime_ns, size
    return (*(values[c] for c in columns), *row[len(columns) :])


def _dump(conn: sqlite3.Connection) -> dict[str, list[tuple[Any, ...]]]:
    tables = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    symbols: dict[int, tuple[Any, ...]] = {
        int(row[0]): tuple(row[1:])
        for row in conn.execute(
            "SELECT id, file_path, name, kind, line, end_line, language "
            "FROM ast_symbol_rows"
        )
    }
    edge_keys: dict[int, tuple[Any, ...]] = {}
    if "edges" in tables:
        edge_keys = {
            int(row[0]): tuple(row[1:])
            for row in conn.execute(
                "SELECT id, source_node_id, target_node_id, kind, line FROM edges"
            )
        }
    dump: dict[str, list[tuple[Any, ...]]] = {}
    for table in tables:
        if table in EXCLUDED_TABLES or table.startswith("ast_symbols_fts"):
            continue
        columns = _columns(conn, table)
        keep = [c for c in columns if c not in EXCLUDED_COLUMNS.get(table, set())]
        if table == "ast_symbol_rows":
            keep = [c for c in keep if c != "id"]
        if table == "edges":
            keep = [c for c in keep if c != "id"]
        quoted = ", ".join(f'"{c}"' for c in keep)
        rows = []
        for row in conn.execute(f'SELECT {quoted} FROM "{table}"'):
            values = dict(zip(keep, row, strict=True))
            symbol_column = _SYMBOL_ID_COLUMNS.get(table)
            if symbol_column in values and values[symbol_column] is not None:
                values[symbol_column] = symbols.get(int(values[symbol_column]), "?")
            if table == "lsp_resolution_cache" and values.get("edge_id") is not None:
                values["edge_id"] = edge_keys.get(int(values["edge_id"]), "?")
            if table == "edges" and isinstance(values.get("metadata"), str):
                values["metadata"] = _canonical_metadata(values["metadata"], symbols)
            if table == "ast_build_state" and values.get("building") == 0:
                continue  # “未在构建”与无行同义（见模块文档）
            rows.append(tuple(values[c] for c in keep))
        if table == "ast_symbol_projection_state" and "projection_digest" in keep:
            rows = _projection_rows(conn, keep, rows)
        if table == "ast_index":
            # ``certified_at`` 的值是时间戳，只比较“是否已认证”。
            certified = dict(
                conn.execute(
                    "SELECT file_path, certified_at IS NOT NULL FROM ast_index"
                ).fetchall()
            )
            rows = [(*row, certified[row[0]]) for row in rows]
        dump[table] = _sorted(rows)
    dump["fts5vocab(instance)"] = _fts_dump(conn, symbols)
    return dump


_METADATA_SYMBOL_KEYS = ("callee_symbol_id", "resolved_symbol_id", "symbol_id")


def _canonical_metadata(raw: str, symbols: dict[int, tuple[Any, ...]]) -> str:
    """边元数据 JSON 中的符号代理键映射为自然键；其余字段原样保留。"""
    import json

    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(data, dict):
        return raw
    for key in _METADATA_SYMBOL_KEYS:
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            data[key] = list(symbols.get(value, ("?",)))
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _projection_rows(
    conn: sqlite3.Connection, keep: list[str], rows: list[tuple[Any, ...]]
) -> list[tuple[Any, ...]]:
    """把依赖代理键的摘要换成“与该文件实际符号行一致”的布尔值。"""
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    path_at = keep.index("file_path")
    digest_at = keep.index("projection_digest")
    converted = []
    for row in rows:
        actual = symbol_rows_digest(
            conn.execute(
                "SELECT id, name, kind, file_path, language, line, end_line "
                "FROM ast_symbol_rows WHERE file_path = ? ORDER BY id",
                (row[path_at],),
            ).fetchall()
        )
        values = list(row)
        values[digest_at] = actual == row[digest_at]
        converted.append(tuple(values))
    return converted


def _fts_dump(
    conn: sqlite3.Connection, symbols: dict[int, tuple[Any, ...]]
) -> list[tuple[Any, ...]]:
    present = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='ast_symbols_fts'"
    ).fetchone()
    if present is None:
        return []
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS temp.tsa_fts_vocab "
        "USING fts5vocab(main, ast_symbols_fts, instance)"
    )
    try:
        return _sorted(
            [
                (term, symbols.get(int(doc), "?"), column, offset)
                for term, doc, column, offset in conn.execute(
                    "SELECT term, doc, col, offset FROM temp.tsa_fts_vocab"
                )
            ]
        )
    finally:
        conn.execute("DROP TABLE temp.tsa_fts_vocab")


def dump_differences(
    left: dict[str, list[tuple[Any, ...]]],
    right: dict[str, list[tuple[Any, ...]]],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """逐表差异（各方独有的行，最多 ``limit`` 条）；相同返回空字典。"""
    from collections import Counter

    differences: dict[str, Any] = {}
    for table in sorted(set(left) | set(right)):
        a = Counter(left.get(table, []))
        b = Counter(right.get(table, []))
        if a == b:
            continue
        only_left = list((a - b).elements())
        only_right = list((b - a).elements())
        differences[table] = {
            "only_left": len(only_left),
            "only_right": len(only_right),
            "left_sample": only_left[:limit],
            "right_sample": only_right[:limit],
        }
    return differences
