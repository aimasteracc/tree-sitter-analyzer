"""Tests for tree_sitter_analyzer.api.pulse.

Covers: apply_budget (immutability, truncation order, large budget),
query_pulse (empty table, no-call-graph languages).
Target coverage: ~55-65% of api/pulse.py.
"""

from __future__ import annotations

import json

import pytest

from tree_sitter_analyzer.api.pulse import (
    CallerRef,
    CommentRef,
    PulseResponse,
    SymbolInfo,
    apply_budget,
    query_pulse,
)

# ---------------------------------------------------------------------------
# Minimal symbol for constructing PulseResponse in tests
# ---------------------------------------------------------------------------

_MINIMAL_SYM = SymbolInfo(
    name="fn",
    kind="function",
    file="a.py",
    line=1,
    end_line=5,
    language="python",
)

_MINIMAL_PR = PulseResponse(symbol=_MINIMAL_SYM)


@pytest.mark.parametrize(
    "name,args",
    [
        ("SymbolInfo", ("fn", "function", "a.py", 1, 5, "python")),
        ("CallerRef", ("caller", "a.py", 1, 0)),
        ("CalleeRef", ("callee",)),
        ("ImportRef", ("module",)),
        ("GitHeat", ()),
        ("SiblingRef", ("sibling", "function", 2)),
        ("CommentRef", (3, "note", "inline")),
        ("BranchContext", ("loop",)),
        ("PulseResponse", (_MINIMAL_SYM,)),
    ],
)
def test_split_dtos_preserve_public_identity_and_pickle(name, args):
    """PR #1352：机械迁移 DTO 后仍为单一类型，公开路径、冻结行为和 pickle 往返不变。"""
    import dataclasses
    import pickle

    from tree_sitter_analyzer.api import _pulse_models, pulse

    cls = getattr(pulse, name)
    assert cls is getattr(_pulse_models, name)
    assert cls.__module__ == "tree_sitter_analyzer.api.pulse"
    value = cls(*args)
    restored = pickle.loads(pickle.dumps(value))
    assert type(restored) is cls
    assert restored == value
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, dataclasses.fields(value)[0].name, None)


@pytest.mark.parametrize(
    "first", ["_pulse_models", "_pulse_sql", "serialization", "pulse"]
)
def test_pulse_leaf_import_order_is_acyclic(first):
    """PR #1352：干净解释器中不同导入顺序均可用，DTO 与序列化不会提前加载查询实现。"""
    import subprocess
    import sys

    script = """
import importlib, sys, typing
first = sys.argv[1]
importlib.import_module('tree_sitter_analyzer.api.' + first)
if first != 'pulse':
    assert 'tree_sitter_analyzer.api.pulse' not in sys.modules
from tree_sitter_analyzer.api import pulse, serialization
assert serialization.PulseResponse is pulse.PulseResponse
assert typing.get_type_hints(pulse.PulseResponse)['symbol'] is pulse.SymbolInfo
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, first],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    )
    assert result.stdout == "ok\n"


def test_pulse_sql_moved_without_changing_query_bytes():
    """PR #1352：固定 SQL 的原始字节必须保持拆分前指纹，避免夹带查询语义修改。"""
    import hashlib

    from tree_sitter_analyzer.api import _pulse_sql, pulse

    assert pulse._PULSE_SQL is _pulse_sql._PULSE_SQL
    # 使用原始摘要字节表达公开校验和，不添加秘密扫描豁免。
    assert hashlib.sha256(pulse._PULSE_SQL.encode("utf-8")).digest() == (
        b"\x17\x6b\x4f\xbb\x0e\xce\x93\x9d\x87\xf5\xdd\xc7\x17\x45\x78\xc5"
        b"\xbb\xcb\xd5\x27\xf6\x79\xb1\x1c\xb6\x90\x2e\x03\xc3\xf0\xe1\x01"
    )


@pytest.mark.parametrize("boundary", ["identity", "imports"])
@pytest.mark.parametrize("outer_transaction", [False, True])
def test_pulse_wal_reindex_keeps_one_read_version(
    tmp_path, boundary, outer_transaction
):
    """PR #1352 P2：另一真实 WAL 连接重索引换 ID 后，整次只读 Pulse 必须保持同一版本。"""
    import sqlite3

    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    importer = tmp_path / "consumer.py"
    source.write_text(
        'def target():\n    """old doc"""\n    # old comment\n    old_helper()\n\ndef old_helper():\n    pass\n',
        encoding="utf-8",
    )
    importer.write_text(
        "import sample\n" if boundary == "identity" else "import elsewhere\n",
        encoding="utf-8",
    )
    writer = ASTCache(str(tmp_path))
    writer.index_file(str(source))
    writer.index_file(str(importer))
    db = writer.get_conn()
    old_id = db.execute(
        "SELECT id FROM ast_symbol_rows WHERE name='target'"
    ).fetchone()[0]
    reader = sqlite3.connect(
        f"file:{writer.db_path}?mode=ro", uri=True, isolation_level=None
    )
    assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    reader.execute("PRAGMA query_only=ON")
    if outer_transaction:
        reader.execute("BEGIN")
    switched = []
    failures = []

    def reindex_between_reads(sql):
        marker = (
            "SELECT json_type(symbols_json"
            if boundary == "identity"
            else "SELECT file_path FROM ast_index WHERE language='python'"
        )
        if switched or not sql.lstrip().startswith(marker):
            return
        switched.append(True)
        try:
            source.write_text(
                'def target():\n    """new doc"""\n    # new comment\n    new_helper()\n\ndef new_helper():\n    pass\n',
                encoding="utf-8",
            )
            importer.write_text(
                "import elsewhere\n" if boundary == "identity" else "import sample\n",
                encoding="utf-8",
            )
            writer.index_file(str(source))
            writer.index_file(str(importer))
        except Exception as exc:
            failures.append(exc)

    reader.set_trace_callback(reindex_between_reads)
    try:
        result = query_pulse(reader, "sample.py", "target")
        assert switched == [True]
        assert failures == []
        assert (
            db.execute("SELECT id FROM ast_symbol_rows WHERE name='target'").fetchone()[
                0
            ]
            != old_id
        )
        assert result is not None
        assert result.symbol.docstring == "old doc"
        assert [c.name for c in result.callees] == ["old_helper"]
        assert [c.text for c in result.comments] == ["old comment"]
        assert result.imported_by == (
            ("consumer.py",) if boundary == "identity" else ()
        )
        assert reader.in_transaction is outer_transaction
        assert reader.total_changes == 0
        current = query_pulse(db, "sample.py", "target")
        assert current.symbol.docstring == "new doc"
        assert current.imported_by == (
            () if boundary == "identity" else ("consumer.py",)
        )
    finally:
        reader.close()
        writer.close()


@pytest.mark.parametrize("failure", [False, True])
def test_pulse_does_not_commit_or_rollback_caller_write_transaction(
    ast_cache_conn, failure
):
    """PR #1352 P2：Pulse 成功或报错均不得提交/回滚调用者已有写事务。"""
    _seed_symbol(ast_cache_conn, "target", "a.py")
    ast_cache_conn.execute("CREATE TABLE caller_state(value TEXT)")
    ast_cache_conn.commit()
    ast_cache_conn.execute("BEGIN")
    ast_cache_conn.execute("INSERT INTO caller_state VALUES ('pending')")
    if failure:
        ast_cache_conn.execute("DROP TABLE ast_symbol_activation")
        import sqlite3

        with pytest.raises(sqlite3.OperationalError, match="ast_symbol_activation"):
            query_pulse(ast_cache_conn, "a.py", "target", max_comments=0)
    else:
        assert (
            query_pulse(ast_cache_conn, "a.py", "target", max_comments=0).symbol.name
            == "target"
        )
    assert ast_cache_conn.in_transaction is True
    assert (
        ast_cache_conn.execute("SELECT value FROM caller_state").fetchone()[0]
        == "pending"
    )
    ast_cache_conn.rollback()
    assert ast_cache_conn.execute("SELECT * FROM caller_state").fetchall() == []


def _make_pr_with_comments(n: int = 10) -> PulseResponse:
    comments = tuple(
        CommentRef(line=i, text=f"comment {i}", kind="inline") for i in range(n)
    )
    return PulseResponse(symbol=_MINIMAL_SYM, comments=comments)


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


def test_target_removed_between_identity_and_context_returns_missing(ast_cache_conn):
    """PR #1352：连接上并发删除已识别目标后，不能从其他同名目标拼出上下文。"""
    _seed_symbol(ast_cache_conn, "vanish", "a.py")

    def delete_before_context(sql):
        if sql.lstrip().startswith("WITH"):
            ast_cache_conn.execute("DELETE FROM ast_symbol_rows WHERE name='vanish'")

    ast_cache_conn.set_trace_callback(delete_before_context)
    try:
        assert query_pulse(ast_cache_conn, "a.py", "vanish", max_comments=0) is None
    finally:
        ast_cache_conn.set_trace_callback(None)


def test_budget_uses_optional_tokenizer_without_network(monkeypatch):
    """PR #1352：已安装 tokenizer 的编码结果决定裁剪，保留 Unicode 和原输入。"""
    import sys
    from types import SimpleNamespace

    calls = []

    def encoding(name):
        assert name == "cl100k_base"

        def encode(text):
            calls.append(json.loads(text))
            return list(text.encode("utf-8"))

        return SimpleNamespace(encode=encode)

    monkeypatch.setitem(sys.modules, "tiktoken", SimpleNamespace(get_encoding=encoding))
    original = PulseResponse(
        symbol=_MINIMAL_SYM, comments=(CommentRef(1, "注释", "inline"),)
    )
    result = apply_budget(original, token_budget=1)
    assert result.comments == ()
    assert result.truncated_fields == ("comments",)
    assert original.comments[0].text == "注释"
    assert any("注释" in json.dumps(value, ensure_ascii=False) for value in calls)


# ---------------------------------------------------------------------------
# apply_budget — immutability
# ---------------------------------------------------------------------------


def test_apply_budget_does_not_mutate_input():
    """apply_budget must not mutate the input PulseResponse (frozen dataclass)."""
    pr = _make_pr_with_comments(10)
    original_comments = pr.comments
    apply_budget(pr, token_budget=1)
    # Frozen dataclass: mutation would raise FrozenInstanceError;
    # verify the reference is unchanged (just sanity).
    assert pr.comments is original_comments


def test_apply_budget_returns_new_object():
    """apply_budget always returns a new PulseResponse object."""
    pr = _MINIMAL_PR
    result = apply_budget(pr, token_budget=999999)
    assert result is not pr


def test_apply_budget_drops_comments_first():
    """With a very tight budget, 'comments' field is among the truncated fields."""
    pr = _make_pr_with_comments(10)
    result = apply_budget(pr, token_budget=1)
    # comments is lowest priority — should be dropped
    assert "comments" in result.truncated_fields


def test_apply_budget_large_budget_no_truncation():
    """With a very large budget, no fields are truncated."""
    pr = _make_pr_with_comments(5)
    result = apply_budget(pr, token_budget=100_000)
    assert result.truncated_fields == ()


def test_apply_budget_large_budget_preserves_comments():
    """apply_budget with generous budget keeps all comments."""
    pr = _make_pr_with_comments(3)
    result = apply_budget(pr, token_budget=100_000)
    assert len(result.comments) == 3


# ---------------------------------------------------------------------------
# Helpers for seeding data in the in-memory DB
# ---------------------------------------------------------------------------


def _seed_symbol(conn, name: str, file_path: str, language: str = "python") -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, 1, 10),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# query_pulse — empty table
# ---------------------------------------------------------------------------


def test_query_pulse_empty_table(ast_cache_conn):
    """No matching symbol in empty DB → query_pulse returns None."""
    # The ast_cache_conn fixture includes ast_index (SCHEMA_V1), so the CTE
    # can run without OperationalError. An empty DB returns target_json=NULL.
    result = query_pulse(ast_cache_conn, "a.py", "fn")
    assert result is None


def test_query_pulse_no_call_graph_language(ast_cache_conn):
    """Symbol with language='sql' → call_graph_available=False, callers=(), callees=()."""
    _seed_symbol(ast_cache_conn, "my_query", "report.sql", language="sql")

    result = query_pulse(ast_cache_conn, "report.sql", "my_query")
    assert result is not None, (
        "query_pulse must return a result when the symbol exists in ast_symbol_rows"
    )
    assert result.call_graph_available is False
    assert result.callers == ()
    assert result.callees == ()


def test_query_pulse_returns_none_for_missing_symbol(ast_cache_conn):
    """Symbol that does not exist in ast_symbol_rows → None."""
    result = query_pulse(ast_cache_conn, "nonexistent.py", "ghost_fn")
    assert result is None


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
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.tools.pulse_tool import PulseTool

    source = tmp_path / "a.py"
    source.write_text("def only():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        cache.get_conn().execute("UPDATE ast_index SET symbols_json='{broken'")
        tool = PulseTool(str(tmp_path))
        tool._cache = cache
        result = await tool.execute({"file": "a.py", "symbol": "only"})
        assert result["success"] is False
        assert result["error"] == "pulse query failed: malformed JSON"
    finally:
        cache.close()


def _call(
    conn,
    caller,
    callee,
    *,
    caller_line=1,
    call_line=5,
    target_id=None,
    target_file="",
    file="a.py",
):
    return conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, line, "
        "file_path, caller_name, caller_line, callee_name, callee_line, "
        "callee_symbol_id, callee_resolved_file, callee_resolution) "
        "VALUES (?, ?, 'calls', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{file}:{caller}:{caller_line}",
            f"{target_file}:{callee}:{call_line}",
            call_line,
            file,
            caller,
            caller_line,
            callee,
            call_line,
            target_id,
            target_file,
            "project" if target_file else "unknown",
        ),
    ).lastrowid


def test_pulse_rejects_ambiguous_target(ast_cache_conn):
    # PR #1352：同文件同名不能任意选取首行。
    _seed_symbol(ast_cache_conn, "run", "a.py")
    _seed_symbol(ast_cache_conn, "run", "a.py")
    with pytest.raises(ValueError, match="AMBIGUOUS_SYMBOL"):
        query_pulse(ast_cache_conn, "a.py", "run")


@pytest.mark.parametrize(
    "limit",
    ["max_callers", "max_callees", "max_siblings", "max_imports", "max_comments"],
)
def test_pulse_rejects_negative_limits_before_sql(ast_cache_conn, limit):
    # PR #1352：SQLite LIMIT -1 表示无限，必须在执行前拒绝。
    statements = []
    ast_cache_conn.set_trace_callback(statements.append)
    with pytest.raises(ValueError, match=limit):
        query_pulse(ast_cache_conn, "a.py", "run", **{limit: -1})
    assert statements == []


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


def test_budget_drops_low_priority_fields_before_callers(monkeypatch):
    # PR #1352：即使 callers 单独超限，也不能保留低优先 comments 而先丢 callers。
    import importlib

    pulse_module = importlib.import_module("tree_sitter_analyzer.api.pulse")
    monkeypatch.setattr(
        pulse_module,
        "_estimate_tokens",
        lambda v: len(v) if isinstance(v, tuple) else 0,
    )
    pulse = PulseResponse(
        symbol=_MINIMAL_SYM,
        callers=tuple(CallerRef("run", "a.py", 1, 0) for _ in range(5)),
        comments=(CommentRef(1, "comment", "inline"),),
    )
    result = apply_budget(pulse, 3)
    assert result.truncated_fields == ("comments", "callers")
    assert result.callers == ()
    assert result.comments == ()


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


@pytest.mark.parametrize("format", ["compact", "verbose"])
def test_serialization_preserves_relationship_payloads(format):
    # PR #1352：发布格式不能丢失关系身份、解析状态或 Git 消息。
    from tree_sitter_analyzer.api.pulse import CalleeRef, GitHeat, ImportRef, SiblingRef
    from tree_sitter_analyzer.api.serialization import serialize

    pulse = PulseResponse(
        symbol=_MINIMAL_SYM,
        callers=(CallerRef("caller", "caller.py", 7, 3),),
        callees=(CalleeRef("callee", "callee.py", 11, "resolved"),),
        git_heat=GitHeat(
            commit="sha", commit_msg="message", at=123, mod_30d=2, mod_90d=4, mod_all=5
        ),
        imports=(ImportRef("pkg", "pkg.py"),),
        imported_by=("consumer.py",),
        siblings=(SiblingRef("other", "function", 20),),
        comments=(CommentRef(2, "note", "inline"),),
    )
    result = serialize(pulse, format)
    if format == "compact":
        assert result["cr"] == [{"n": "caller", "f": "caller.py", "l": 7, "h": 3}]
        assert result["ce"] == [
            {"n": "callee", "f": "callee.py", "l": 11, "r": "resolved"}
        ]
        assert result["gh"] == {
            "sha": "sha",
            "m": "message",
            "at": 123,
            "m30": 2,
            "m90": 4,
            "mall": 5,
            "s": "tracked",
        }
        assert result["im"] == [{"m": "pkg", "f": "pkg.py"}]
        assert result["ib"] == ["consumer.py"]
        assert result["sib"] == [{"n": "other", "k": "function", "l": 20}]
        assert result["cmt"] == [{"l": 2, "t": "note", "k": "inline"}]
    else:
        assert result["callers"] == [
            {"name": "caller", "file": "caller.py", "line": 7, "hot30": 3}
        ]
        assert result["callees"] == [
            {
                "name": "callee",
                "file": "callee.py",
                "line": 11,
                "resolution": "resolved",
            }
        ]
        assert result["git_heat"] == {
            "commit": "sha",
            "commit_msg": "message",
            "at": 123,
            "mod_30d": 2,
            "mod_90d": 4,
            "mod_all": 5,
            "state": "tracked",
        }
        assert result["imports"] == [{"module": "pkg", "file": "pkg.py"}]
        assert result["imported_by"] == ["consumer.py"]
        assert result["siblings"] == [{"name": "other", "kind": "function", "line": 20}]
        assert result["comments"] == [{"line": 2, "text": "note", "kind": "inline"}]
