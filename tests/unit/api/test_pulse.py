"""Tests for tree_sitter_analyzer.api.pulse.

Covers: apply_budget (immutability, truncation order, large budget),
query_pulse (empty table, no-call-graph languages).
Target coverage: ~55-65% of api/pulse.py.
"""

from __future__ import annotations

import pytest

from tests.unit.api._pulse_helpers import _MINIMAL_SYM, _seed_symbol
from tree_sitter_analyzer.api.pulse import query_pulse


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


def test_pulse_sql_preserves_reviewed_snapshot_and_activation_guards():
    """PR #1350/#1352：固定 SQL 包含已审阅的快照与 lazy-state 守卫，指纹随此次收敛更新。

    审计 P3-2：imported_by 的 LIMIT 20 改为绑定 :imported_by_probe（21 行）以证明触顶。
    """
    import hashlib

    from tree_sitter_analyzer.api import _pulse_sql, pulse

    assert pulse._PULSE_SQL is _pulse_sql._PULSE_SQL
    # 使用原始摘要字节表达公开校验和，不添加秘密扫描豁免。
    assert hashlib.sha256(pulse._PULSE_SQL.encode("utf-8")).digest() == (
        b"\x8e\xc02z\xab\xda\xe9\xf4\x01\x86\xa4\x91\x1aA\x03B"
        b"\xc8\x87\xa9\x12\xe8\x96\xac\xd9\xe5|\xf5i\x0c\xdev\x94"
    )


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


def test_query_pulse_imports_graph_availability_by_language(ast_cache_conn):
    """issue #1444：无 import 边语言显式声明 iga=False，imported_by 是「声明过的空」。"""
    _seed_symbol(ast_cache_conn, "my_query", "report.sql", language="sql")
    result = query_pulse(ast_cache_conn, "report.sql", "my_query")
    assert result.imports_graph_available is False
    assert result.imported_by == ()

    _seed_symbol(ast_cache_conn, "greet", "a.py")
    py = query_pulse(ast_cache_conn, "a.py", "greet")
    assert py.imports_graph_available is True


def test_query_pulse_returns_none_for_missing_symbol(ast_cache_conn):
    """Symbol that does not exist in ast_symbol_rows → None."""
    result = query_pulse(ast_cache_conn, "nonexistent.py", "ghost_fn")
    assert result is None


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


# Python 反向导入缓存测试已拆至 test_pulse_import_cache.py（800 行治理阈值）。


# 序列化视图契约测试已拆至 test_pulse_serialization.py（issue #1444/#1445
# 测试增长使本文件越过 800 行治理阈值，断言原样迁移）。


# 预算与截断、SQL 查询路径、只读一致性与认证读取测试已按 #1546 拆至
# test_pulse_budget_truncation.py、test_pulse_sql_paths.py、
# test_pulse_read_consistency.py（500 行模块上限），断言原样迁移。
