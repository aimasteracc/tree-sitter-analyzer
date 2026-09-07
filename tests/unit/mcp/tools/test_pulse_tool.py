"""Tests for tree_sitter_analyzer.mcp.tools.pulse_tool.

Covers: PulseTool, PulseBatchTool, GetProjectSchemaTool execute() paths,
error handling, and batch truncation.
Target coverage: ~80-88% of pulse_tool.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.pulse_tool import (
    GetProjectSchemaTool,
    PulseBatchTool,
    PulseTool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_cache(conn):
    """Return a MagicMock that satisfies the cache.get_conn() contract."""
    fake = MagicMock()
    fake.get_conn.return_value = conn
    return fake


def _seed_symbol(
    conn, name: str, file_path: str = "a.py", language: str = "python"
) -> int:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, 1, 10),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# PulseTool
# ---------------------------------------------------------------------------


async def test_pulse_get_cache_raises_returns_error():
    """_get_cache() raises → execute() returns success=False with the error message."""
    tool = PulseTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("not set"))

    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "not set" in result["error"]


async def test_pulse_symbol_not_found(ast_cache_conn):
    """Empty DB → query_pulse returns None → success=False with descriptive message."""
    tool = PulseTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "fn" in result["error"]
    assert "a.py" in result["error"]


async def test_pulse_query_raises_returns_error(ast_cache_conn, monkeypatch):
    """query_pulse raises → execute() returns success=False with 'pulse query failed'."""
    tool = PulseTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    monkeypatch.setattr(
        "tree_sitter_analyzer.api.pulse.query_pulse",
        MagicMock(side_effect=RuntimeError("db error")),
    )
    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "pulse query failed" in result["error"]


# ---------------------------------------------------------------------------
# PulseBatchTool
# ---------------------------------------------------------------------------


async def test_pulse_batch_truncates_targets(ast_cache_conn):
    """超量目标保留截断警告，已尝试但不存在的目标仍须计为失败。"""
    tool = PulseBatchTool(project_root=None)
    fake_cache = _make_fake_cache(ast_cache_conn)
    tool._get_cache = MagicMock(return_value=fake_cache)

    targets = [{"file": f"f{i}.py", "symbol": f"fn{i}"} for i in range(5)]
    result = await tool.execute({"targets": targets, "max_symbols": 3})

    assert result["success"] is False
    assert result["count"] == 0
    assert result["error_count"] == 3
    assert result["truncated_count"] == 2
    warnings = [r for r in result["results"] if isinstance(r, dict) and "warning" in r]
    assert len(warnings) == 1
    assert "2 targets truncated" in warnings[0]["warning"]


async def test_pulse_batch_get_cache_raises():
    """_get_cache() raises → execute() returns success=False."""
    tool = PulseBatchTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("no root"))

    result = await tool.execute({"targets": [{"file": "a.py", "symbol": "fn"}]})
    assert result["success"] is False
    assert "no root" in result["error"]


# ---------------------------------------------------------------------------
# GetProjectSchemaTool
# ---------------------------------------------------------------------------


async def test_get_project_schema_get_cache_raises():
    """缓存访问失败应明确失败，而不是冒充正常的未索引状态。"""
    tool = GetProjectSchemaTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("no root"))

    result = await tool.execute({})
    assert result["success"] is False
    assert result["error"] == "no root"
    assert result["result"]["indexed"] is False


@pytest.fixture
def indexed_pulse_project(tmp_path):
    """真实单文件索引，不替换 SQL、预算或序列化实现。"""
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "a.py"
    source.write_text(
        'def greet(name):\n    """Say hello."""\n    # keep name\n    return name\n',
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    yield tmp_path, cache
    cache.close()


@pytest.mark.parametrize("format", ["skeletal", "compact", "verbose"])
async def test_nav_pulse_serializes_real_index(indexed_pulse_project, format):
    # PR #1352：真实 facade 必须返回可读的身份/文档/注释，而不是 mock success。
    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    root, _ = indexed_pulse_project
    response = await build_nav_facade(str(root)).execute(
        {"action": "pulse", "file": "a.py", "symbol": "greet", "format": format}
    )
    assert response["success"] is True
    payload = response["result"]
    if format == "skeletal":
        assert payload == {
            "n": "greet",
            "k": "function",
            "f": "a.py:1",
            "callers": 0,
            "callees": 0,
            "hot30": 0,
            "call_graph": True,
        }
    elif format == "compact":
        assert payload["sym"] == {
            "n": "greet",
            "k": "function",
            "f": "a.py",
            "l": 1,
            "el": 4,
            "lang": "python",
            "cls": None,
            "doc": "Say hello.",
        }
        assert payload["cmt"] == [{"l": 3, "t": "keep name", "k": "inline"}]
        assert payload["trunc"] == []
    else:
        assert payload["symbol"] == {
            "name": "greet",
            "kind": "function",
            "file": "a.py",
            "line": 1,
            "end_line": 4,
            "language": "python",
            "class_name": None,
            "docstring": "Say hello.",
        }
        assert payload["comments"] == [
            {"line": 3, "text": "keep name", "kind": "inline"}
        ]
        assert payload["truncated_fields"] == []


@pytest.mark.parametrize("limit", [-1, 1001])
async def test_pulse_rejects_out_of_range_limit(indexed_pulse_project, limit):
    # PR #1352：限制错误不能返回已截断/完整成功结果。
    root, _ = indexed_pulse_project
    response = await PulseTool(str(root)).execute(
        {"file": "a.py", "symbol": "greet", "max_callers": limit}
    )
    assert response["success"] is False
    assert "max_callers must be" in response["error"]
    assert "result" not in response


async def test_pulse_rejects_ambiguous_index_without_picking_a_definition(
    indexed_pulse_project,
):
    # PR #1352：通过真实工具错误边界验证同名歧义不能成为假成功。
    root, cache = indexed_pulse_project
    _seed_symbol(cache.get_conn(), "greet")
    response = await PulseTool(str(root)).execute({"file": "a.py", "symbol": "greet"})
    assert response["success"] is False
    assert "AMBIGUOUS_SYMBOL" in response["error"]
    assert "result" not in response


async def test_pulse_import_capacity_is_an_error(indexed_pulse_project):
    # PR #1352：超出反向导入资源上限不能伪装成空列表。
    root, cache = indexed_pulse_project
    conn = cache.get_conn()
    conn.executemany(
        "INSERT INTO ast_imports(file_path,language,module_path) VALUES ('a.py','python',?)",
        [(f"module_{i}",) for i in range(20001)],
    )
    conn.commit()
    response = await PulseTool(str(root)).execute({"file": "a.py", "symbol": "greet"})
    assert response["success"] is False
    assert "PULSE_IMPORT_RESOURCE_LIMIT" in response["error"]


async def test_pulse_batch_retains_per_target_error(indexed_pulse_project):
    # PR #1352：批量结果成功项可序列化，缺失项仍须带错误，不能被丢弃。
    root, _ = indexed_pulse_project
    response = await PulseBatchTool(str(root)).execute(
        {
            "targets": [
                {"file": "a.py", "symbol": "greet"},
                {"file": "a.py", "symbol": "missing"},
            ]
        }
    )
    assert response["results"][0]["sym"]["n"] == "greet"
    assert response["results"][1] == {
        "file": "a.py",
        "symbol": "missing",
        "error": "not found",
    }
    assert response["success"] is False
    assert response["count"] == 1
    assert response["error_count"] == 1


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"file": None}, "file"),
        ({"symbol": 4}, "symbol"),
        ({"symbol": "  "}, "symbol"),
        ({"format": "csv"}, "format"),
        ({"token_budget": 0}, "token_budget"),
        ({"token_budget": True}, "token_budget"),
        ({"max_callers": 1.5}, "max_callers"),
        ({"max_callees": "10"}, "max_callees"),
        ({"max_comments": False}, "max_comments"),
        ({"max_siblings": None}, "max_siblings"),
    ],
)
async def test_pulse_invalid_public_parameter_has_no_index_side_effect(changes, field):
    # PR #1352：无效参数必须在打开/迁移索引之前拒绝，不能隐式强制转换。
    tool = PulseTool(None)
    tool._get_cache = MagicMock(side_effect=AssertionError("must not open index"))
    args = {"file": "a.py", "symbol": "greet", **changes}
    response = await tool.execute(args)
    assert response["success"] is False
    assert response["error_code"] == "INVALID_ARGUMENT"
    assert field in response["error"]
    assert "result" not in response
    tool._get_cache.assert_not_called()


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"targets": None}, "targets"),
        ({"targets": [None]}, "targets[0]"),
        ({"targets": [{"file": "a.py"}]}, "targets[0].symbol"),
        ({"max_symbols": -1}, "max_symbols"),
        ({"max_symbols": True}, "max_symbols"),
        ({"token_budget_per_symbol": "400"}, "token_budget_per_symbol"),
        ({"format": "verbose"}, "format"),
    ],
)
async def test_pulse_batch_validates_public_request_before_index(changes, field):
    # PR #1352：嵌套 targets 和批量上限也必须校验，不能切片后才暴露错误。
    tool = PulseBatchTool(None)
    tool._get_cache = MagicMock(side_effect=AssertionError("must not open index"))
    response = await tool.execute(
        {"targets": [{"file": "a.py", "symbol": "greet"}], **changes}
    )
    assert response["success"] is False
    assert response["error_code"] == "INVALID_ARGUMENT"
    assert field in response["error"]
    tool._get_cache.assert_not_called()


async def test_project_schema_sql_failure_is_not_an_empty_index(indexed_pulse_project):
    # PR #1352：读取失败不是成功的空索引，不得掩盖数据库损坏。
    root, cache = indexed_pulse_project
    tool = GetProjectSchemaTool(str(root))
    tool._cache = cache
    cache.get_conn().execute("DROP TABLE edges")
    response = await tool.execute({})
    assert response["success"] is False
    assert response["error"] == "no such table: edges"
    assert response["result"]["indexed"] is False


async def test_project_schema_reports_real_counts(indexed_pulse_project):
    # PR #1352：schema 端点应从真实索引读取精确统计。
    root, _ = indexed_pulse_project
    response = await GetProjectSchemaTool(str(root)).execute({})
    assert response["success"] is True
    assert response["result"]["indexed"] is True
    assert response["result"]["languages"] == ["python"]
    assert response["result"]["total_symbols"] == 1
    assert response["result"]["total_edges"] == 0


async def test_pulse_batch_empty_request_does_not_create_index():
    # PR #1352：空批次可以成功，但不能创建索引或捏造已处理目标。
    tool = PulseBatchTool(None)
    tool._get_cache = MagicMock(side_effect=AssertionError("must not open index"))
    response = await tool.execute({"targets": []})
    assert response == {
        "success": True,
        "results": [],
        "count": 0,
        "error_count": 0,
        "truncated_count": 0,
    }
    tool._get_cache.assert_not_called()


async def test_pulse_accepts_integral_zero_limit_without_mutating_request(
    indexed_pulse_project,
):
    # PR #1352：max_comments=0.0 合法地省略注释，不能被当作默认值覆盖。
    root, _ = indexed_pulse_project
    arguments = {"file": "a.py", "symbol": "greet", "max_comments": 0.0}
    response = await PulseTool(str(root)).execute(arguments)
    assert response["success"] is True
    assert response["result"]["cmt"] == []
    assert type(arguments["max_comments"]) is float


async def test_get_project_schema_empty_db(ast_cache_conn):
    """Empty DB (0 symbols) → indexed=False."""
    tool = GetProjectSchemaTool(project_root=None)
    tool._get_cache = MagicMock(return_value=_make_fake_cache(ast_cache_conn))

    result = await tool.execute({})
    assert result["success"] is True
    assert result["result"]["indexed"] is False


async def test_nav_batch_success_isolated_across_project_rebind(tmp_path):
    # PR #1352：相同文件/符号/数据库 ID 不能让切换项目后的 batch 复用旧结果。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    roots = []
    for label in ("first", "second"):
        root = tmp_path / label
        root.mkdir()
        source = root / "a.py"
        source.write_text(
            f'def greet():\n    """{label} greet"""\n    return 1\n\ndef other():\n    """{label} other"""\n    return 2\n',
            encoding="utf-8",
        )
        cache = ASTCache(str(root))
        try:
            assert cache.index_file(str(source))["status"] == "indexed"
        finally:
            cache.close()
        roots.append(root)
    facade = build_nav_facade(str(roots[0]))
    request = {
        "action": "pulse_batch",
        "targets": [
            {"file": "a.py", "symbol": "greet"},
            {"file": "a.py", "symbol": "other"},
        ],
    }
    for root in (roots[0], roots[1], roots[0]):
        facade.set_project_path(str(root))
        result = await facade.execute(request)
        assert result["success"] is True
        assert (result["count"], result["error_count"], result["truncated_count"]) == (
            2,
            0,
            0,
        )
        assert [
            (r["sym"]["n"], r["sym"]["f"], r["sym"]["doc"]) for r in result["results"]
        ] == [
            ("greet", "a.py", f"{root.name} greet"),
            ("other", "a.py", f"{root.name} other"),
        ]
