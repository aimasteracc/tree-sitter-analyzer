"""#1546：test_pulse SQL 查询路径行为组；从 test_pulse.py 原样迁移，测试主体不变。"""

from __future__ import annotations

import json

import pytest

from tests.unit.api._pulse_helpers import _call, _seed_symbol
from tree_sitter_analyzer.api.pulse import (
    PulseResponse,
    SymbolInfo,
    query_pulse,
)


@pytest.mark.parametrize(
    "cached", ["missing_table", "bad_line", "missing_file", "text_line"]
)
def test_optional_lsp_damage_preserves_indexed_callsite(ast_cache_conn, cached):
    """PR #1352：可选 LSP 缓存缺失或损坏不得抹掉基础调用点，也不能伪造定义。"""
    from tree_sitter_analyzer.api.pulse import CalleeRef

    _seed_symbol(ast_cache_conn, "caller", "a.py")
    edge = ast_cache_conn.execute(
        "INSERT INTO edges(source_node_id,target_node_id,kind,file_path,caller_name,caller_line,callee_name,callee_line,callee_resolution) "
        "VALUES ('src','dst','calls','a.py','caller',1,'unknown',3,'unknown')"
    ).lastrowid
    if cached == "missing_table":
        ast_cache_conn.execute("DROP TABLE lsp_resolution_cache")
    else:
        file, line = {
            "bad_line": ("b.py", -1),
            "missing_file": (None, 0),
            "text_line": ("b.py", "invalid"),
        }[cached]
        ast_cache_conn.execute(
            "INSERT INTO lsp_resolution_cache(edge_id,resolved_file,resolved_line,lsp_server,cached_at) VALUES (?,?,?,'peer',0)",
            (edge, file, line),
        )
    result = query_pulse(ast_cache_conn, "a.py", "caller", max_comments=0)
    assert result is not None
    assert result.symbol.name == "caller"
    assert result.callees == (
        CalleeRef(name="unknown", file=None, line=None, resolution="unknown"),
    )


@pytest.mark.parametrize("row_style", ["tuple", "sqlite_row"])
def test_sql_json_empty_relations_and_null_heat_keep_public_shape(
    ast_cache_conn, row_style
):
    # PR #1352：真实 SQLite 的空数组和 NULL 在两种标准 row 形式下保持相同结果。
    import sqlite3

    _seed_symbol(ast_cache_conn, "only", "a.py")
    ast_cache_conn.execute(
        "INSERT INTO ast_index(file_path,content_hash,language,mtime_ns,file_size,indexed_at,symbols_json) "
        "VALUES ('a.py','hash','python',0,0,'',?)",
        (
            json.dumps(
                {
                    "symbols": [{"name": "only", "kind": "function", "line": 1}],
                    "comments": [],
                }
            ),
        ),
    )
    ast_cache_conn.row_factory = None if row_style == "tuple" else sqlite3.Row
    result = query_pulse(ast_cache_conn, "a.py", "only")
    assert result == PulseResponse(
        symbol=SymbolInfo(
            name="only",
            kind="function",
            file="a.py",
            line=1,
            end_line=10,
            language="python",
        )
    )


async def test_raw_symbols_json_corruption_remains_an_error(tmp_path):
    # PR #1352：简化内置 JSON 解码不能让真正的索引 JSON 损坏成为成功响应。
    import sqlite3

    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "a.py"
    source.write_text("def only():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        cache.get_conn().execute("UPDATE ast_index SET symbols_json='{broken'")
        with pytest.raises(sqlite3.OperationalError, match="malformed JSON"):
            query_pulse(cache.get_conn(), "a.py", "only")
    finally:
        cache.close()


def test_pulse_callee_uses_definition_not_callsite(ast_cache_conn):
    # PR #1352：被调定义在 1 行，调用点在 8 行。
    _seed_symbol(ast_cache_conn, "run", "a.py")
    target = _seed_symbol(ast_cache_conn, "work", "b.py")
    _call(
        ast_cache_conn, "run", "work", call_line=8, target_id=target, target_file="b.py"
    )
    result = query_pulse(ast_cache_conn, "a.py", "run")
    assert [(c.file, c.line) for c in result.callees] == [("b.py", 1)]


def test_pulse_unknown_definition_has_no_callsite_coordinate(ast_cache_conn):
    # PR #1352：缺少定义证据时不能捏造定义行。
    _seed_symbol(ast_cache_conn, "run", "a.py")
    _call(ast_cache_conn, "run", "work", call_line=8)
    result = query_pulse(ast_cache_conn, "a.py", "run")
    assert [(c.file, c.line) for c in result.callees] == [(None, None)]


def test_pulse_unresolved_same_name_is_not_a_caller(ast_cache_conn):
    # PR #1352：同文件未解析名字也不是唯一目标证据。
    _seed_symbol(ast_cache_conn, "work", "a.py")
    _call(ast_cache_conn, "run", "work")
    assert query_pulse(ast_cache_conn, "a.py", "work").callers == ()


def test_pulse_callers_do_not_duplicate_same_named_methods(ast_cache_conn):
    # PR #1352：热度连接使用调用者定义行，不扩展到同名方法。
    target = _seed_symbol(ast_cache_conn, "work", "b.py")
    _seed_symbol(ast_cache_conn, "run", "a.py")
    other = _seed_symbol(ast_cache_conn, "run", "a.py")
    ast_cache_conn.execute("UPDATE ast_symbol_rows SET line=20 WHERE id=?", (other,))
    _call(ast_cache_conn, "run", "work", target_id=target, target_file="b.py")
    result = query_pulse(ast_cache_conn, "b.py", "work")
    assert [(c.name, c.line) for c in result.callers] == [("run", 1)]


def test_pulse_lsp_cache_is_bound_to_edge_and_converts_zero(ast_cache_conn):
    # PR #1352：同名两次调用有不同目标，LSP 第 0 行必须转换为 TSA 第 1 行。
    from tree_sitter_analyzer.lsp.client import cache_lsp_resolution

    _seed_symbol(ast_cache_conn, "run", "a.py")
    for line, target, definition in [(5, "b.py", 0), (8, "c.py", 19)]:
        edge = _call(ast_cache_conn, "run", "work", call_line=line)
        cache_lsp_resolution(
            ast_cache_conn,
            edge_id=edge,
            symbol_id=None,
            resolved_file=target,
            resolved_line=definition,
            resolved_type=None,
            lsp_server="fake",
        )
    result = query_pulse(ast_cache_conn, "a.py", "run")
    assert [(c.file, c.line, c.resolution) for c in result.callees] == [
        ("b.py", 1, "resolved"),
        ("c.py", 20, "resolved"),
    ]


def test_pulse_reads_complete_symbols_json(ast_cache_conn):
    # PR #1352：JSON 超过 500 字符仍须先解析，再截短目标 docstring。
    _seed_symbol(ast_cache_conn, "run", "a.py")
    symbols = {
        "comments": [],
        "symbols": [
            {"name": "padding", "docstring": "x" * 600},
            {
                "name": "run",
                "kind": "function",
                "line": 1,
                "docstring": "target documentation",
            },
        ],
    }
    ast_cache_conn.execute(
        "INSERT INTO ast_index (file_path, content_hash, language, symbols_json, mtime_ns, file_size, indexed_at) "
        "VALUES ('a.py', 'hash', 'python', ?, 0, 0, '')",
        (json.dumps(symbols),),
    )
    assert (
        query_pulse(ast_cache_conn, "a.py", "run").symbol.docstring
        == "target documentation"
    )


def test_pulse_imported_by_matches_target_module(ast_cache_conn):
    # PR #1352：反向 import 不能返回目标自己的出边或只因符号同名而匹配。
    _seed_symbol(ast_cache_conn, "run", "pkg/mod.py")
    for source, module in [
        ("consumer.py", "pkg.mod"),
        ("pkg/mod.py", "unrelated"),
        ("wrong.py", "run"),
    ]:
        ast_cache_conn.execute(
            "INSERT INTO edges (source_node_id, target_node_id, kind, file_path, callee_name) "
            "VALUES (?, ?, 'imports', ?, ?)",
            (f"file:{source}", f"module:{module}", source, module),
        )
    assert query_pulse(ast_cache_conn, "pkg/mod.py", "run").imported_by == (
        "consumer.py",
    )


@pytest.mark.parametrize(
    "statement", ["from .mod import run", "from . import mod as alias"]
)
def test_pulse_relative_import_uses_existing_module_resolver(tmp_path, statement):
    # PR #1352：真实 import 索引覆盖相对模块和子模块别名。
    from tree_sitter_analyzer.ast_cache import ASTCache

    package = tmp_path / "pkg"
    package.mkdir()
    (package / "mod.py").write_text("def run():\n    pass\n", encoding="utf-8")
    (package / "consumer.py").write_text(statement + "\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        for name in ("mod.py", "consumer.py"):
            cache.index_file(str(package / name))
        result = query_pulse(cache.get_conn(), "pkg/mod.py", "run")
        assert result.imported_by == ("pkg/consumer.py",)
    finally:
        cache.close()


def test_pulse_reports_missing_legacy_commit_message(ast_cache_conn, caplog):
    # PR #1352：存量 activation 缺少消息时，保留 NULL 并发出 missing 诊断。
    caplog.set_level("WARNING", logger="tree_sitter_analyzer.api.pulse")
    sid = _seed_symbol(ast_cache_conn, "run", "a.py")
    ast_cache_conn.execute(
        "INSERT INTO ast_symbol_activation (symbol_id,file_path,last_modified_commit,computed_at) "
        "VALUES (?, 'a.py', ?, 0)",
        (sid, "a" * 40),
    )
    result = query_pulse(ast_cache_conn, "a.py", "run")
    assert result.git_heat.commit_msg is None
    assert "COMMIT_MESSAGE_MISSING" in caplog.text
    assert (
        "tree_sitter_analyzer.api.pulse",
        30,
        "COMMIT_MESSAGE_MISSING: a.py:run",
    ) in caplog.record_tuples


def test_pulse_legacy_comments_are_not_reported_as_empty_success(tmp_path):
    # PR #1352：旧提取数据没有注释证据时，默认查询必须明确拒绝。
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "a.py"
    source.write_text("def run():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute(
            "UPDATE ast_index SET symbols_json=json_remove(symbols_json, '$.comments')"
        )
        with pytest.raises(ValueError, match="COMMENTS_NOT_INDEXED"):
            query_pulse(conn, "a.py", "run")
        assert query_pulse(conn, "a.py", "run", max_comments=0).symbol.name == "run"
    finally:
        cache.close()
