"""Tests for tree_sitter_analyzer.mcp.tools.tql_tool.

Covers: _cap_echo boundary values, TqlSchemaTool.execute(), TqlExecuteTool
  syntax-error path, empty selector path, _detect_index_state verdicts.
Target coverage: ~45-55% of tql_tool.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.unit.hyphae.test_evaluator import (
    FakeCache,
    FakeCacheWithConn,
    _seed_edge,
    _seed_sym,
)
from tree_sitter_analyzer.hyphae.evaluator import Evaluator
from tree_sitter_analyzer.hyphae.parser import HyphaeSyntaxError, parse
from tree_sitter_analyzer.mcp.tools.tql_tool import (
    TqlExecuteTool,
    TqlSchemaTool,
    _cap_echo,
)


@pytest.mark.parametrize(
    "selector,error",
    [
        (".function:hot", "TEMPORAL_INDEX_UNAVAILABLE"),
        (".function:reaches(#alpha){1,2}", "BFS_INDEX_UNAVAILABLE"),
        (".function:violates(rule)", "VIOLATION_INDEX_UNAVAILABLE"),
        (".function:branch(loop)", "BRANCH_INDEX_UNAVAILABLE"),
    ],
)
@pytest.mark.parametrize("storage", ["unsupported", "cannot_open"])
def test_sql_predicates_refuse_unavailable_adapter(tmp_path, selector, error, storage):
    """PR #1352：旧非 SQL 适配器及真实无法打开的数据库，不能给需要持久化证据的谓词伪造结果。"""
    import sqlite3

    cache = FakeCache([{"name": "alpha", "file": "a.py", "line": 1}], [], [])
    if storage == "cannot_open":
        cache.get_conn = lambda: sqlite3.connect(str(tmp_path))
    with pytest.raises(HyphaeSyntaxError, match=error):
        Evaluator(cache).eval(parse(selector))


@pytest.mark.parametrize(
    "table,pseudo,error",
    [
        ("edges", "reaches(#A){1,2}", "BFS_INDEX_UNAVAILABLE"),
        ("ast_constraint_violations", "violates(rule)", "VIOLATION_INDEX_UNAVAILABLE"),
    ],
)
def test_sql_predicate_missing_table_is_not_empty_graph(
    ast_cache_conn, table, pseudo, error
):
    """PR #1352：迁移后表被删除时，真实 SQL 必须报告无法验明图关系。"""
    _seed_sym(ast_cache_conn, "A")
    ast_cache_conn.execute(f"DROP TABLE {table}")
    cache = FakeCacheWithConn(
        [{"name": "A", "file": "f.py", "line": 1}], [], [], ast_cache_conn
    )
    with pytest.raises(HyphaeSyntaxError, match=error):
        Evaluator(cache).eval(parse(f".function:{pseudo}"))


def test_bfs_sql_interrupt_cleans_progress_handler(ast_cache_conn, monkeypatch):
    """PR #1352：真实递归 SQL 的时限中断必须失败且撤销 handler，后续数据库仍可使用。"""
    from types import SimpleNamespace

    import tree_sitter_analyzer.hyphae.evaluator as module

    ids = [_seed_sym(ast_cache_conn, f"n{i}") for i in range(60)]
    for i in range(59):
        _seed_edge(ast_cache_conn, f"n{i}", f"n{i + 1}", callee_symbol_id=ids[i + 1])
    ticks = iter([0.0])
    monkeypatch.setattr(
        module, "time", SimpleNamespace(monotonic=lambda: next(ticks, 2.0))
    )
    ev = Evaluator(FakeCacheWithConn([], [], [], ast_cache_conn))
    with pytest.raises(HyphaeSyntaxError, match="BFS_RESOURCE_LIMIT"):
        ev._eval_depth_bfs([ids[0]], "callee", 1, 50)
    assert (
        ast_cache_conn.execute(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) SELECT sum(x) FROM n"
        ).fetchone()[0]
        == 500500
    )


@pytest.mark.parametrize("stage", ["seed", "result"])
def test_bfs_sql_authorization_failure_is_not_empty_matches(ast_cache_conn, stage):
    """PR #1352：种子解析或结果身份读取受数据库拒绝时，错误不能降级为空匹配。"""
    import sqlite3

    _seed_sym(ast_cache_conn, "A")
    target = _seed_sym(ast_cache_conn, "B")
    _seed_edge(ast_cache_conn, "A", "B", callee_symbol_id=target)
    traversed = [False]

    def trace(sql):
        if sql.lstrip().startswith("WITH RECURSIVE"):
            traversed[0] = True

    def authorize(action, table, column, *_):
        if action == sqlite3.SQLITE_READ and table == "ast_symbol_rows":
            if (stage == "seed" and column == "id") or (
                stage == "result" and traversed[0]
            ):
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    cache = FakeCacheWithConn(
        [{"name": "A", "file": "f.py", "line": 1}], [], [], ast_cache_conn
    )
    ast_cache_conn.set_trace_callback(trace)
    ast_cache_conn.set_authorizer(authorize)
    try:
        with pytest.raises(HyphaeSyntaxError, match="BFS_INDEX_UNAVAILABLE"):
            Evaluator(cache).eval(parse(".function:reaches(#B){1,2}"))
    finally:
        ast_cache_conn.set_authorizer(None)
        ast_cache_conn.set_trace_callback(None)


def test_depth_without_selector_is_rejected(ast_cache_conn):
    """PR #1352：可解析但缺失目标的深度谓词必须明确拒绝，不能遍历全部图。"""
    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    with pytest.raises(
        HyphaeSyntaxError, match="depth pseudo-class requires a selector argument"
    ):
        Evaluator(cache).eval(parse(".function:reaches{1,2}"))


# ---------------------------------------------------------------------------
# _cap_echo
# ---------------------------------------------------------------------------


def test_cap_echo_short():
    """Selector at or below 200 chars passes through unchanged."""
    short = "x" * 200
    assert _cap_echo(short) == short


def test_cap_echo_long():
    """Selector above 200 chars is truncated with length suffix."""
    long_sel = "x" * 201
    result = _cap_echo(long_sel)
    assert result.startswith("x" * 200)
    assert "201" in result
    assert "chars total" in result


def test_cap_echo_exact_boundary():
    """Exactly 200 chars → returned unchanged."""
    exact = "a" * 200
    assert _cap_echo(exact) == exact


def test_cap_echo_one_over_boundary():
    """201 chars → truncated."""
    sel = "a" * 201
    result = _cap_echo(sel)
    assert result == "a" * 200 + "... (201 chars total)"
    assert result != sel


# ---------------------------------------------------------------------------
# TqlSchemaTool
# ---------------------------------------------------------------------------


async def test_tql_schema_execute_success():
    """TqlSchemaTool returns success=True with schema doc containing key terms."""
    tool = TqlSchemaTool()
    result = await tool.execute({})
    assert result["success"] is True
    assert ":hotspot" in result["schema"]
    assert "{n,m}" in result["schema"]


# ---------------------------------------------------------------------------
# TqlExecuteTool — validation paths
# ---------------------------------------------------------------------------


async def test_tql_execute_empty_selector():
    """Empty selector string → success=False with 'selector is required'."""
    tool = TqlExecuteTool(project_root=None)
    result = await tool.execute({"selector": ""})
    assert result["success"] is False
    assert "selector is required" in result["error"]


async def test_tql_execute_syntax_error():
    """Malformed selector → success=False before _get_cache is called."""
    tool = TqlExecuteTool(project_root=None)
    mock_cache = MagicMock()
    tool._get_cache = mock_cache

    result = await tool.execute({"selector": ":::"})
    assert result["success"] is False
    assert "TQL syntax error" in result["error"]
    # _get_cache must NOT have been called (parse fails before cache access)
    assert mock_cache.call_count == 0


# ---------------------------------------------------------------------------
# TqlExecuteTool._detect_index_state
# ---------------------------------------------------------------------------


def test_detect_index_state_empty():
    """Cache returns total_files=0 → state='empty', count=0."""
    tool = TqlExecuteTool(project_root=None)
    fake_cache = MagicMock()
    fake_cache.get_stats.return_value = {"total_files": 0}
    state, n = tool._detect_index_state(fake_cache)
    assert state == "empty"
    assert n == 0


def test_detect_index_state_missing():
    """Cache.get_stats() raises → state='missing', count=0."""
    tool = TqlExecuteTool(project_root=None)
    fake_cache = MagicMock()
    fake_cache.get_stats.side_effect = RuntimeError("no cache")
    state, n = tool._detect_index_state(fake_cache)
    assert state == "missing"
    assert n == 0


def test_detect_index_state_ready():
    """Cache returns total_files=42 → state='ready', count=42."""
    tool = TqlExecuteTool(project_root=None)
    fake_cache = MagicMock()
    fake_cache.get_stats.return_value = {"total_files": 42}
    state, n = tool._detect_index_state(fake_cache)
    assert state == "ready"
    assert n == 42


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"selector": None}, "selector"),
        ({"selector": 7}, "selector"),
        ({"max_results": 0}, "max_results"),
        ({"max_results": -1}, "max_results"),
        ({"max_results": True}, "max_results"),
        ({"max_results": 1.5}, "max_results"),
        ({"max_results": "2"}, "max_results"),
        ({"max_results": None}, "max_results"),
        ({"max_results": 1001}, "max_results"),
    ],
)
async def test_tql_rejects_invalid_public_parameter_before_cache(changes, field):
    # PR #1352：不能通过隐式转换或夹取范围把错误请求改成另一条查询。
    tool = TqlExecuteTool(None)
    tool._get_cache = MagicMock(side_effect=AssertionError("must not open index"))
    response = await tool.execute({"selector": ".function", **changes})
    assert response["success"] is False
    assert response["error_code"] == "INVALID_ARGUMENT"
    assert field in response["error"]
    assert response["count"] == 0
    assert response["symbols"] == []
    tool._get_cache.assert_not_called()


@pytest.fixture
def indexed_tql(tmp_path):
    """真实索引和 evaluator，失败场景仅改变请求或数据库状态。"""
    source = tmp_path / "a.py"
    source.write_text(
        "def alpha():\n    pass\n\ndef beta():\n    pass\n\ndef gamma():\n    pass\n",
        encoding="utf-8",
    )
    tool = TqlExecuteTool(str(tmp_path))
    cache = tool._get_cache()
    cache.index_file(str(source))
    yield tool, cache
    cache.close()


@pytest.mark.parametrize(
    "pseudo,column",
    [
        ("hot", "last_modified_at"),
        ("stale", "last_modified_at"),
        ("hotspot", "mod_count_30d"),
    ],
)
def test_temporal_data_read_failure_after_lazy_state_check(indexed_tql, pseudo, column):
    """PR #1350/#1352：状态列可读不代表统计可读，SQLite 拒绝实际数据读取时仍必须显式失败。"""
    import sqlite3

    _, cache = indexed_tql
    db = cache.get_conn()
    denied = []

    def authorize(action, table, field, *_):
        if (
            action == sqlite3.SQLITE_READ
            and table == "ast_symbol_activation"
            and field == column
        ):
            denied.append(field)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    db.set_authorizer(authorize)
    try:
        with pytest.raises(HyphaeSyntaxError, match="TEMPORAL_INDEX_UNAVAILABLE"):
            Evaluator(cache).eval(parse(f".function:{pseudo}"))
        assert denied == [column]
    finally:
        db.set_authorizer(None)


@pytest.mark.parametrize(
    "selector", [".function:hot", ".function:stale", ".function:hotspot"]
)
async def test_temporal_filters_execute_against_real_activation(indexed_tql, selector):
    """PR #1352：公开时序谓词通过真实 activation 精确筛选，而非直接调用过滤私有函数。"""
    tool, cache = indexed_tql
    import time

    db = cache.get_conn()
    db.execute("DELETE FROM ast_symbol_activation")
    now = int(time.time())
    db.execute(
        "INSERT INTO ast_symbol_activation(symbol_id,file_path,last_modified_at,mod_count_30d,computed_at) "
        "SELECT id,file_path,CASE WHEN name='alpha' THEN ? ELSE 0 END,CASE WHEN name='alpha' THEN 9 ELSE 0 END,0 FROM ast_symbol_rows",
        (now,),
    )
    result = await tool.execute({"selector": selector})
    assert result["success"] is True
    expected = ["beta", "gamma"] if selector.endswith(":stale") else ["alpha"]
    assert [s["name"] for s in result["symbols"]] == expected
    assert result["count"] == len(expected)


@pytest.mark.parametrize("selector", [".function:hot(0)", ".function:hot(365001)"])
async def test_temporal_day_boundaries_are_errors(indexed_tql, selector):
    """PR #1352：超范围日期不得变成全部命中或空命中。"""
    tool, _ = indexed_tql
    result = await tool.execute({"selector": selector})
    assert result["success"] is False
    assert result["error"] == "TQL evaluation failed: hot days must be within 1..365000"
    assert result["symbols"] == []


@pytest.mark.parametrize("target", ["#seed", ".function[file=seeds.py]"])
async def test_bfs_seed_capacity_rejects_real_oversized_store(indexed_tql, target):
    """PR #1352：名字及复合选择器均不得绕过 512 种子限制，返回失败而不是截断图。"""
    tool, cache = indexed_tql
    import json

    symbols = [{"name": "seed", "kind": "function", "line": n + 1} for n in range(513)]
    cache.get_conn().execute(
        "INSERT INTO ast_index(file_path,content_hash,language,mtime_ns,file_size,indexed_at,symbols_json) VALUES ('seeds.py','x','python',0,0,'',?)",
        (json.dumps({"symbols": symbols}),),
    )
    cache.get_conn().executemany(
        "INSERT INTO ast_symbol_rows(name,kind,file_path,language,line) VALUES ('seed','function','seeds.py','python',?)",
        [(n + 1,) for n in range(513)],
    )
    result = await tool.execute({"selector": f".function:reaches({target}){{1,2}}"})
    assert result["success"] is False
    assert result["error"] == "TQL evaluation failed: BFS_RESOURCE_LIMIT: seed count"
    assert result["symbols"] == []


async def test_bfs_missing_seed_is_legitimate_zero_matches(indexed_tql):
    """PR #1352：健康图中缺失种子是有效零匹配，不同于图读取失败。"""
    tool, _ = indexed_tql
    result = await tool.execute({"selector": ".function:reaches(#absent){1,2}"})
    assert result["success"] is True
    assert (result["count"], result["total_matches"], result["truncated"]) == (
        0,
        0,
        False,
    )


async def test_bfs_duplicate_definition_identity_is_not_arbitrarily_chosen(indexed_tql):
    """PR #1352：损坏索引中重复定义坐标不能任取一条进入调用链。"""
    tool, cache = indexed_tql
    cache.get_conn().execute(
        "INSERT INTO ast_symbol_rows(name,kind,file_path,language,line) VALUES ('alpha','function','a.py','python',1)"
    )
    result = await tool.execute(
        {"selector": ".function:reaches(#alpha[file=a.py]){1,2}"}
    )
    assert result["success"] is False
    assert result["error"] == "TQL evaluation failed: BFS_SYMBOL_IDENTITY_UNAVAILABLE"


async def test_tql_cap_returns_exact_total_and_truncation(indexed_tql):
    # PR #1352：公开返回的 count、total_matches 和 truncated 必须与真实输入一致。
    tool, _ = indexed_tql
    response = await tool.execute({"selector": ".function", "max_results": 2})
    assert response["success"] is True
    assert response["count"] == 2
    assert response["total_matches"] == 3
    assert response["truncated"] is True
    assert response["indexed_files"] == 1
    assert response["symbols"] == [
        {
            "name": "alpha",
            "file": "a.py",
            "line": 1,
            "language": "python",
            "class": None,
        },
        {
            "name": "beta",
            "file": "a.py",
            "line": 4,
            "language": "python",
            "class": None,
        },
    ]


async def test_tql_exact_limit_is_a_complete_result(indexed_tql):
    # PR #1352：恰好等于上限不等于被截断，公开计数和标记必须一致。
    tool, _ = indexed_tql
    response = await tool.execute({"selector": ".function", "max_results": 3})
    assert response["success"] is True
    assert response["count"] == response["total_matches"] == 3
    assert response["truncated"] is False
    assert [item["name"] for item in response["symbols"]] == ["alpha", "beta", "gamma"]
    assert response["agent_summary"]["verdict"] == "INFO"


async def test_tql_ready_zero_matches_is_not_index_failure(indexed_tql):
    # PR #1352：零匹配与查询失败必须可区分。
    tool, _ = indexed_tql
    response = await tool.execute({"selector": "#absent"})
    assert response["success"] is True
    assert response["count"] == response["total_matches"] == 0
    assert response["symbols"] == []
    assert response["truncated"] is False
    assert response["index_state"] == "ready"
    assert response["agent_summary"]["verdict"] == "NOT_FOUND"


async def test_tql_empty_index_does_not_claim_query_success(tmp_path):
    # PR #1352：尚未索引时不能把零结果解释成完整查询成功。
    tool = TqlExecuteTool(str(tmp_path))
    try:
        response = await tool.execute({"selector": ".function"})
        assert response["success"] is False
        assert response["error"] == "TQL_INDEX_EMPTY"
        assert response["index_state"] == "empty"
        assert response["symbols"] == []
    finally:
        if tool._cache is not None:
            tool._cache.close()


async def test_tql_broken_edge_store_is_not_zero_matches(indexed_tql):
    # PR #1352：底层 query_edges 会降级为空列表，公开入口必须先识别损坏索引。
    tool, cache = indexed_tql
    cache.get_conn().execute("DROP TABLE edges")
    response = await tool.execute({"selector": ".function:calls(#alpha)"})
    assert response["success"] is False
    assert response["error"] == "TQL_INDEX_UNAVAILABLE: no such table: edges"
    assert response["symbols"] == []


@pytest.mark.parametrize(
    "selector,error",
    [
        (".function:unsupported", "unknown pseudo-class ':unsupported'"),
        (".function:reaches(#alpha){2,1}", "depth must be within 1..50"),
    ],
)
async def test_tql_evaluation_error_is_an_error_response(indexed_tql, selector, error):
    # PR #1352：语法解析后的 evaluator 错误也要返回失败，不能裸抛或伪造统计。
    tool, _ = indexed_tql
    response = await tool.execute({"selector": selector})
    assert response["success"] is False
    assert response["error"] == "TQL evaluation failed: " + error
    assert response["count"] == 0
    assert response["symbols"] == []
    assert "total_matches" not in response


async def test_tql_corrupt_branch_metadata_cannot_match_all_symbols(indexed_tql):
    # PR #1352：schema 完整但 JSON 损坏时，也不能吞错后返回全部候选。
    tool, cache = indexed_tql
    cache.get_conn().execute(
        "INSERT INTO edges(source_node_id,target_node_id,kind,metadata) VALUES ('a','b','calls','not-json')"
    )
    response = await tool.execute({"selector": ".function:branch(loop)"})
    assert response["success"] is False
    assert (
        response["error"]
        == "TQL evaluation failed: BRANCH_INDEX_UNAVAILABLE: malformed JSON"
    )
    assert response["count"] == 0
    assert response["symbols"] == []


async def test_tql_accepts_integral_json_number_without_mutating_request(indexed_tql):
    # PR #1352：保留仓库已支持的整值浮点输入，且不修改调用者字典。
    tool, _ = indexed_tql
    arguments = {"selector": ".function", "max_results": 2.0}
    response = await tool.execute(arguments)
    assert response["count"] == 2
    assert response["total_matches"] == 3
    assert type(arguments["max_results"]) is float


@pytest.fixture
async def indexed_tql_relationships(tmp_path):
    """构建真实解析/解析后调用边，再由真实约束工具持久化违规记录。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    (tmp_path / "db.py").write_text("def persist():\n    return 1\n", encoding="utf-8")
    (tmp_path / "service.py").write_text(
        "from db import persist\n\nclass Writer:\n    def run(self):\n        return persist()\n"
        "    def forward(self):\n        return self.run()\n\nclass Reader:\n    def run(self):\n"
        "        return 0\n    def forward(self):\n        return self.run()\n",
        encoding="utf-8",
    )
    (tmp_path / "architectural-constraints.yml").write_text(
        "version: 1\nconstraints:\n  - id: no-db\n    severity: error\n    rule: forbid\n"
        "    from: service.py\n    to: db.py\n    reason: keep the service boundary\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        assert (
            cache.index_project(max_files=4, workers=0, include_activation=False)[
                "errors"
            ]
            == 0
        )
        rows = (
            cache.get_conn()
            .execute(
                "SELECT e.caller_name,e.caller_line,e.callee_name,s.file_path,s.line "
                "FROM edges e LEFT JOIN ast_symbol_rows s ON s.id=e.callee_symbol_id "
                "WHERE e.kind='calls' ORDER BY e.caller_line"
            )
            .fetchall()
        )
        assert [tuple(r) for r in rows] == [
            ("run", 4, "persist", "db.py", 1),
            ("forward", 6, "run", "service.py", 4),
            ("forward", 12, "run", "service.py", 10),
        ]
        checked = await ConstraintCheckTool(str(tmp_path)).execute(
            {"persist": True, "output_format": "json"}
        )
        assert checked["success"] is True
        assert [
            (v["caller_file"], v["caller_name"], v["caller_line"])
            for v in checked["violations"]
        ] == [("service.py", "run", 4)]
        yield build_search_facade(str(tmp_path))
    finally:
        cache.close()


@pytest.mark.parametrize(
    "selector,expected",
    [
        (".method:calls(#persist)", [("run", "Writer", 4)]),
        (
            ".method:reaches(#persist){1,2}",
            [("run", "Writer", 4), ("forward", "Writer", 6)],
        ),
        (".method:violates(no-db)", [("run", "Writer", 4)]),
        (".method:calls(.method[class=Writer])", [("forward", "Writer", 6)]),
    ],
)
async def test_search_tql_real_relationships_do_not_cross_same_named_methods(
    indexed_tql_relationships, selector, expected
):
    # PR #1352：公开 search 结果必须保持类、文件和定义行，不能只按方法名过筛。
    result = await indexed_tql_relationships.execute(
        {"action": "tql_execute", "selector": selector}
    )
    assert result["success"] is True
    assert result["count"] == result["total_matches"] == len(expected)
    assert result["truncated"] is False
    assert [(s["name"], s["class"], s["line"]) for s in result["symbols"]] == expected
    assert {s["file"] for s in result["symbols"]} == {"service.py"}
