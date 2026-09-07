"""Tests for tree_sitter_analyzer.mcp.tools.tql_tool.

Covers: _cap_echo boundary values, TqlSchemaTool.execute(), TqlExecuteTool
  syntax-error path, empty selector path, _detect_index_state verdicts.
Target coverage: ~45-55% of tql_tool.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.tql_tool import (
    TqlExecuteTool,
    TqlSchemaTool,
    _cap_echo,
)

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
