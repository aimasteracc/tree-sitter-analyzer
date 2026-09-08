"""Pulse 工具的参数、源码认证、批次隔离和错误语义测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.api.pulse import query_pulse
from tree_sitter_analyzer.mcp.tools.pulse_tool import (
    GetProjectSchemaTool,
    PulseBatchTool,
    PulseTool,
)


def _make_fake_cache(conn):
    """Return a MagicMock that satisfies the cache.get_conn() contract."""
    fake = MagicMock()
    fake.get_conn.return_value = conn
    return fake


@pytest.mark.parametrize("kind", ["single", "batch"])
async def test_warm_pulse_rejects_invalidated_index_with_unchanged_source(
    indexed_pulse_project, kind
):
    """源码未变不能替代索引认证；已预热的单次和批次查询都必须拒绝失效索引。"""
    root, cache = indexed_pulse_project
    source = root / "a.py"
    original = source.read_bytes()
    tool = PulseTool(str(root)) if kind == "single" else PulseBatchTool(str(root))
    target = {"file": "a.py", "symbol": "greet"}
    arguments = target if kind == "single" else {"targets": [target]}
    warm = await tool.execute(arguments)
    assert warm["success"] is True
    assert warm["source_evidence"]["freshness"] == "fresh"
    assert warm["source_evidence"]["snapshot_id"] is not None

    cache.invalidate(str(source))
    assert source.read_bytes() == original
    response = await tool.execute(arguments)
    assert response == {
        "success": False,
        "error_code": "SOURCE_EVIDENCE_UNAVAILABLE",
        "error": "Pulse source evidence unavailable: CALL_GRAPH_INCOMPLETE",
        "source_evidence": {
            "freshness": "unknown",
            "snapshot_id": None,
            "source_generation": None,
            "reason": "CALL_GRAPH_INCOMPLETE",
        },
    }


async def test_pulse_missing_relation_is_query_failure(indexed_pulse_project):
    """PR #1352：目标存在但关系表损坏时，不得谎报目标不存在。"""
    root, cache = indexed_pulse_project
    tool = PulseTool(str(root))
    cache.get_conn().execute("DROP TABLE ast_symbol_activation")
    cache.get_conn().commit()
    response = await tool.execute({"file": "a.py", "symbol": "greet"})
    assert response["success"] is False
    assert response["source_evidence"]["reason"] == "INCOMPATIBLE_SCHEMA"
    assert "result" not in response


async def test_batch_corrupt_index_rejects_all_uncertified_targets(
    indexed_pulse_project,
):
    """2026-09-08：损坏索引无法认证，整批拒绝，不能发布貌似健康的部分结果。"""
    root, cache = indexed_pulse_project
    source = root / "bad.py"
    source.write_text("def broken():\n    pass\n", encoding="utf-8")
    cache.index_file(str(source))
    cache.get_conn().execute(
        "UPDATE ast_index SET symbols_json='{' WHERE file_path='bad.py'"
    )
    cache.get_conn().commit()
    tool = PulseBatchTool(str(root))
    result = await tool.execute(
        {
            "targets": [
                {"file": "bad.py", "symbol": "broken"},
                {"file": "a.py", "symbol": "greet"},
            ],
            "max_symbols": 2.0,
            "token_budget_per_symbol": 400.0,
        }
    )
    assert result["success"] is False
    assert result["source_evidence"]["freshness"] == "unknown"
    assert "results" not in result


async def test_schema_invalid_timestamp_does_not_invent_index_age(
    indexed_pulse_project,
):
    """PR #1352：已有索引时间字段损坏时保留真实数量，年龄明确为未知。"""
    root, cache = indexed_pulse_project
    cache.get_conn().execute("UPDATE ast_index SET indexed_at='invalid timestamp'")
    tool = GetProjectSchemaTool(str(root))
    tool._cache = cache
    result = await tool.execute({})
    assert result["success"] is True
    assert result["result"]["index_age_seconds"] is None
    assert result["result"]["total_symbols"] == 1


@pytest.mark.parametrize(
    "kind", ["pulse", "batch", "schema", "semantic", "tql", "tql_schema"]
)
async def test_factory_schema_and_missing_root_contract(tmp_path, kind):
    """PR #1352：公开工厂产生匹配的输入 schema，无项目时执行不能创建隐式索引。"""
    from tree_sitter_analyzer.mcp.tools import pulse_tool, semantic_tool, tql_tool

    factory, arguments = {
        "pulse": (pulse_tool.build_pulse_tool, {"file": "a.py", "symbol": "greet"}),
        "batch": (
            pulse_tool.build_pulse_batch_tool,
            {"targets": [{"file": "a.py", "symbol": "greet"}]},
        ),
        "schema": (pulse_tool.build_project_schema_tool, {}),
        "semantic": (semantic_tool.build_semantic_neighbors_tool, {"query": "greet"}),
        "tql": (tql_tool.build_tql_execute_tool, {"selector": ".function"}),
        "tql_schema": (tql_tool.build_tql_schema_tool, {}),
    }[kind]
    tool = factory(str(tmp_path))
    tool.project_root = None
    assert (
        tool.get_tool_schema()
        == tool.get_tool_definition()["inputSchema"]["properties"]
    )
    assert tool.validate_arguments(dict(arguments)) is True
    result = await tool.execute(arguments)
    if kind == "tql_schema":
        assert result["success"] is True
        assert ":hot(N)" in result["schema"]
    else:
        assert result["success"] is False
        if kind in {"pulse", "batch"}:
            assert result["source_evidence"]["reason"] == "MISSING_PROJECT_ROOT"
        else:
            assert (
                result["error"] == "Project root not set. Call set_project_path first."
            )
    assert not (tmp_path / ".ast-cache").exists()


@pytest.mark.parametrize("field,value", [("token_budget", 0), ("token_budget", False)])
async def test_pulse_invalid_budget_is_not_silently_reinterpreted(field, value):
    """PR #1352：零和布尔预算违反公开整数约束，不能执行另一条查询。"""
    result = await PulseTool().execute(
        {"file": "a.py", "symbol": "greet", field: value}
    )
    assert result == {
        "success": False,
        "error_code": "INVALID_ARGUMENT",
        "error": "token_budget must be a positive integer",
    }


async def test_batch_rejects_excessive_capacity():
    """PR #1352：批量上限超过服务边界时必须拒绝，不允许突破资源限制。"""
    result = await PulseBatchTool().execute({"targets": [], "max_symbols": 1001})
    assert result == {
        "success": False,
        "error_code": "INVALID_ARGUMENT",
        "error": "max_symbols must not exceed 1000",
    }


async def test_explicit_positive_budget_preserves_requested_definition(
    indexed_pulse_project,
):
    """PR #1352：显式合法的 JSON 整值预算保持目标身份，不改写调用者的参数。"""
    root, cache = indexed_pulse_project
    tool = PulseTool(str(root))
    arguments = {"file": "a.py", "symbol": "greet", "token_budget": 600.0}
    result = await tool.execute(arguments)
    assert result["success"] is True
    assert result["result"]["sym"]["n"] == "greet"
    assert type(arguments["token_budget"]) is float


async def test_reverse_import_does_not_attach_unrelated_module(indexed_pulse_project):
    """PR #1352：真实解析无关模块的 import 不能误归属当前定义文件。"""
    root, cache = indexed_pulse_project
    for filename, text in [
        ("other.py", "def other():\n    pass\n"),
        ("consumer.py", "import other\n"),
    ]:
        path = root / filename
        path.write_text(text, encoding="utf-8")
        cache.index_file(str(path))
    await _certify_project(root)
    tool = PulseTool(str(root))
    response = await tool.execute(
        {"file": "a.py", "symbol": "greet", "format": "verbose"}
    )
    assert response["success"] is True
    assert response["result"]["imported_by"] == []


async def test_pulse_missing_project_returns_source_error():
    """缺失项目必须与符号不存在分开，不打开隐式索引。"""
    result = await PulseTool(None).execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert result["source_evidence"]["reason"] == "MISSING_PROJECT_ROOT"


async def test_pulse_symbol_not_found(indexed_pulse_project):
    """当前认证快照内不存在的目标，才可以明确报告不存在。"""
    root, _ = indexed_pulse_project
    tool = PulseTool(str(root))

    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "fn" in result["error"]
    assert "a.py" in result["error"]


async def test_pulse_query_raises_returns_error(indexed_pulse_project, monkeypatch):
    """认证连接上的查询失败仍明确失败。"""
    root, _ = indexed_pulse_project
    tool = PulseTool(str(root))

    monkeypatch.setattr(
        "tree_sitter_analyzer.api.pulse.query_pulse",
        MagicMock(side_effect=RuntimeError("db error")),
    )
    result = await tool.execute({"file": "a.py", "symbol": "fn"})
    assert result["success"] is False
    assert "pulse query failed" in result["error"]


async def test_pulse_batch_truncates_targets(indexed_pulse_project):
    """超量目标保留截断警告，已尝试但不存在的目标仍须计为失败。"""
    root, _ = indexed_pulse_project
    tool = PulseBatchTool(str(root))

    targets = [{"file": f"f{i}.py", "symbol": f"fn{i}"} for i in range(5)]
    result = await tool.execute({"targets": targets, "max_symbols": 3})

    assert result["success"] is False
    assert result["count"] == 0
    assert result["error_count"] == 3
    assert result["truncated_count"] == 2
    warnings = [r for r in result["results"] if isinstance(r, dict) and "warning" in r]
    assert len(warnings) == 1
    assert "2 targets truncated" in warnings[0]["warning"]


async def test_pulse_batch_missing_project_returns_source_error():
    """缺失项目时整批失败，无目标级假不存在。"""
    result = await PulseBatchTool(None).execute(
        {"targets": [{"file": "a.py", "symbol": "fn"}]}
    )
    assert result["success"] is False
    assert result["source_evidence"]["reason"] == "MISSING_PROJECT_ROOT"
    assert "results" not in result


async def test_get_project_schema_get_cache_raises():
    """缓存访问失败应明确失败，而不是冒充正常的未索引状态。"""
    tool = GetProjectSchemaTool(project_root=None)
    tool._get_cache = MagicMock(side_effect=ValueError("no root"))

    result = await tool.execute({})
    assert result["success"] is False
    assert result["error"] == "no root"
    assert result["result"]["indexed"] is False


async def _certify_project(root):
    """通过生产完整索引入口生成认证，不能用 mock 声称源码当前。"""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute({"mode": "full"})
    assert result["scope_complete"] is True


@pytest.fixture
async def indexed_pulse_project(tmp_path):
    """真实单文件索引，不替换 SQL、预算或序列化实现。"""
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "a.py"
    source.write_text(
        'def greet(name):\n    """Say hello."""\n    # keep name\n    return name\n',
        encoding="utf-8",
    )
    await _certify_project(tmp_path)
    cache = ASTCache(str(tmp_path))
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
    (root / "a.py").write_text(
        "def greet():\n    return 1\ndef greet():\n    return 2\n", encoding="utf-8"
    )
    await _certify_project(root)
    response = await PulseTool(str(root)).execute({"file": "a.py", "symbol": "greet"})
    assert response["success"] is False
    assert "AMBIGUOUS_SYMBOL" in response["error"]
    assert "result" not in response


async def test_pulse_rejects_unrecorded_import_projection(indexed_pulse_project):
    # 2026-09-08：未重新认证的导入表改动不能借用旧清单返回成功。
    root, cache = indexed_pulse_project
    conn = cache.get_conn()
    conn.executemany(
        "INSERT INTO ast_imports(file_path,language,module_path) VALUES ('a.py','python',?)",
        [(f"module_{i}",) for i in range(20001)],
    )
    conn.commit()
    response = await PulseTool(str(root)).execute({"file": "a.py", "symbol": "greet"})
    assert response["success"] is False
    assert response["source_evidence"]["freshness"] == "unknown"
    assert response["source_evidence"]["reason"] == "NO_EXACT_FULL_INDEX_MANIFEST"


@pytest.mark.parametrize(
    "symbol,error",
    [("missing", "not found"), ("repeated", "AMBIGUOUS_SYMBOL: a.py:repeated")],
)
async def test_pulse_batch_retains_per_target_error(
    indexed_pulse_project, symbol, error
):
    # PR #1352：批量结果成功项可序列化，缺失项仍须带错误，不能被丢弃。
    root, _ = indexed_pulse_project
    source = root / "a.py"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\ndef repeated():\n    pass\ndef repeated():\n    pass\n",
        encoding="utf-8",
    )
    await _certify_project(root)
    response = await PulseBatchTool(str(root)).execute(
        {
            "targets": [
                {"file": "a.py", "symbol": "greet"},
                {"file": "a.py", "symbol": symbol},
            ]
        }
    )
    assert response["results"][0]["sym"]["n"] == "greet"
    assert response["results"][1] == {
        "file": "a.py",
        "symbol": symbol,
        "error": error,
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
async def test_pulse_invalid_public_parameter_has_no_index_side_effect(
    changes, field, monkeypatch
):
    # PR #1352：无效参数必须在打开/迁移索引之前拒绝，不能隐式强制转换。
    tool = PulseTool(None)
    source_access = MagicMock(side_effect=AssertionError("must not open index"))
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.pulse_tool.certified_pulse_connection",
        source_access,
    )
    args = {"file": "a.py", "symbol": "greet", **changes}
    response = await tool.execute(args)
    assert response["success"] is False
    assert response["error_code"] == "INVALID_ARGUMENT"
    assert field in response["error"]
    assert "result" not in response
    source_access.assert_not_called()


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
async def test_pulse_batch_validates_public_request_before_index(
    changes, field, monkeypatch
):
    # PR #1352：嵌套 targets 和批量上限也必须校验，不能切片后才暴露错误。
    tool = PulseBatchTool(None)
    source_access = MagicMock(side_effect=AssertionError("must not open index"))
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.pulse_tool.certified_pulse_connection",
        source_access,
    )
    response = await tool.execute(
        {"targets": [{"file": "a.py", "symbol": "greet"}], **changes}
    )
    assert response["success"] is False
    assert response["error_code"] == "INVALID_ARGUMENT"
    assert field in response["error"]
    source_access.assert_not_called()


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


async def test_pulse_batch_empty_request_does_not_create_index(monkeypatch):
    # PR #1352：空批次可以成功，但不能创建索引或捏造已处理目标。
    tool = PulseBatchTool(None)
    source_access = MagicMock(side_effect=AssertionError("must not open index"))
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.pulse_tool.certified_pulse_connection",
        source_access,
    )
    response = await tool.execute({"targets": []})
    assert response == {
        "success": True,
        "results": [],
        "count": 0,
        "error_count": 0,
        "truncated_count": 0,
    }
    source_access.assert_not_called()


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
        await _certify_project(root)
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


@pytest.mark.parametrize(
    "kind,symbol", [("single", "greet"), ("single", "renamed"), ("batch", "greet")]
)
async def test_pulse_saved_source_is_stale_not_missing(
    indexed_pulse_project, kind, symbol
):
    # 2026-09-08：旧名和新名都必须指出索引过期，不能返回旧结果或假不存在。
    root, _ = indexed_pulse_project
    (root / "a.py").write_text("def renamed():\n    return 2\n", encoding="utf-8")
    if kind == "single":
        result = await PulseTool(str(root)).execute({"file": "a.py", "symbol": symbol})
    else:
        result = await PulseBatchTool(str(root)).execute(
            {"targets": [{"file": "a.py", "symbol": symbol}]}
        )
    assert result == {
        "success": False,
        "error_code": "SOURCE_EVIDENCE_UNAVAILABLE",
        "error": "Pulse source evidence unavailable: SOURCE_INDEX_MISMATCH",
        "source_evidence": {
            "freshness": "stale",
            "snapshot_id": None,
            "source_generation": None,
            "reason": "SOURCE_INDEX_MISMATCH",
        },
    }


async def test_pulse_batch_save_between_targets_discards_entire_result(
    indexed_pulse_project, monkeypatch
):
    # 2026-09-08：第二个目标期间保存，不能保留第一个目标的成功结果。
    from tree_sitter_analyzer.api import pulse

    root, _ = indexed_pulse_project
    original = pulse.query_pulse
    calls = []

    def changing_query(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(kwargs["symbol_name"])
        if len(calls) == 2:
            (root / "a.py").write_text(
                "def renamed():\n    return 2\n", encoding="utf-8"
            )
        return result

    monkeypatch.setattr(pulse, "query_pulse", changing_query)
    response = await PulseBatchTool(str(root)).execute(
        {
            "targets": [
                {"file": "a.py", "symbol": "greet"},
                {"file": "a.py", "symbol": "absent"},
            ]
        }
    )
    assert calls == ["greet", "absent"]
    assert response["success"] is False
    assert response["source_evidence"]["reason"] == "SOURCE_GENERATION_MISMATCH"
    assert "results" not in response


@pytest.mark.parametrize("format", ["skeletal", "compact", "verbose"])
async def test_pulse_tiny_budget_preserves_source_evidence(
    indexed_pulse_project, format
):
    """源码证据留在外层，最小内容预算与精简展示不能裁掉它。"""
    root, _ = indexed_pulse_project
    result = await PulseTool(str(root)).execute(
        {"file": "a.py", "symbol": "greet", "token_budget": 1, "format": format}
    )
    assert result["success"] is True
    assert result["source_evidence"]["freshness"] == "fresh"
    assert result["source_evidence"]["reason"] is None


@pytest.fixture
async def certified_pulse_project(tmp_path):
    """建立真实完整索引，认证范围包含定义及跨文件调用者。"""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "leaf.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        "from leaf import leaf\ndef caller():\n    return leaf()\n", encoding="utf-8"
    )
    result = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 100}
    )
    assert result["scope_complete"] is True
    return tmp_path


@pytest.mark.parametrize(
    "change", ["definition", "caller", "delete_caller", "new_caller"]
)
async def test_certified_pulse_rejects_changed_source_scope(
    certified_pulse_project, change
):
    # 2026-09-08：目标未变也不能掩盖调用者的新增、删除或修改。
    from tree_sitter_analyzer.api.pulse_evidence import (
        PulseSourceError,
        certified_pulse_connection,
    )

    root = certified_pulse_project
    if change == "definition":
        (root / "leaf.py").write_text(
            "def renamed():\n    return 2\n", encoding="utf-8"
        )
    elif change == "caller":
        (root / "caller.py").write_text(
            "def caller():\n    return 2\n", encoding="utf-8"
        )
    elif change == "delete_caller":
        (root / "caller.py").unlink()
    else:
        (root / "new.py").write_text(
            "from leaf import leaf\ndef other():\n    return leaf()\n", encoding="utf-8"
        )
    with pytest.raises(PulseSourceError) as error:
        with certified_pulse_connection(str(root)):
            pytest.fail("源码范围过期不能发布读取连接")
    assert (error.value.reason, error.value.freshness) == (
        "SOURCE_INDEX_MISMATCH",
        "stale",
    )


async def test_certified_pulse_reads_one_current_snapshot(certified_pulse_project):
    """退出认证上下文后，结果和版本证据绑定同一个读取连接。"""
    from tree_sitter_analyzer.api.pulse_evidence import certified_pulse_connection

    with certified_pulse_connection(str(certified_pulse_project)) as (conn, evidence):
        result = query_pulse(conn, "leaf.py", "leaf")
        assert evidence["freshness"] == "unknown"
    assert result.symbol.name == "leaf"
    assert [(c.name, c.file) for c in result.callers] == [("caller", "caller.py")]
    assert evidence["freshness"] == "fresh"
    assert evidence["reason"] is None
    assert isinstance(evidence["snapshot_id"], str)
    assert isinstance(evidence["source_generation"], str)


async def test_certified_pulse_rejects_save_during_read(certified_pulse_project):
    # 2026-09-08：读取完成前再次保存时，不得发布读取前的 fresh 证据。
    from tree_sitter_analyzer.api.pulse_evidence import (
        PulseSourceError,
        certified_pulse_connection,
    )

    with pytest.raises(PulseSourceError) as error:
        with certified_pulse_connection(str(certified_pulse_project)) as (
            conn,
            evidence,
        ):
            query_pulse(conn, "leaf.py", "leaf")
            (certified_pulse_project / "caller.py").unlink()
    assert (error.value.reason, error.value.freshness) == (
        "SOURCE_GENERATION_MISMATCH",
        "stale",
    )
    assert evidence["freshness"] == "unknown"


@pytest.mark.parametrize("failure", ["query", "save"])
async def test_certified_pulse_releases_readers_after_failure(
    certified_pulse_project, failure
):
    """失败后释放读取与租约 pin，不能阻塞后续索引或耗尽快照容量。"""
    from tree_sitter_analyzer import index_snapshot
    from tree_sitter_analyzer.api.pulse_evidence import (
        PulseSourceError,
        certified_pulse_connection,
    )

    expected = RuntimeError if failure == "query" else PulseSourceError
    with pytest.raises(expected):
        with certified_pulse_connection(str(certified_pulse_project)) as (_, evidence):
            if failure == "query":
                raise RuntimeError("query failed")
            (certified_pulse_project / "leaf.py").unlink()
    entry = index_snapshot.REGISTRY._entries[evidence["snapshot_id"]]
    assert entry.readers == 0
    assert evidence["freshness"] == "unknown"


@pytest.mark.parametrize("kind", ["single", "batch"])
@pytest.mark.parametrize(
    "stage",
    [
        "lease_existing_snapshot",
        "acquire_index_snapshot",
        "verify_snapshot_source_current",
    ],
)
async def test_pulse_source_access_failure_discards_targets(
    certified_pulse_project, monkeypatch, kind, stage
):
    """认证任一阶段的权限错误均返回稳定 unknown，不能发布部分结果。"""

    def denied(*args, **kwargs):
        raise PermissionError("source access denied")

    monkeypatch.setattr(
        f"tree_sitter_analyzer.api.pulse_evidence.index_snapshot.{stage}", denied
    )
    target = {"file": "leaf.py", "symbol": "leaf"}
    tool = PulseTool if kind == "single" else PulseBatchTool
    result = await tool(str(certified_pulse_project)).execute(
        target if kind == "single" else {"targets": [target]}
    )
    assert result == {
        "success": False,
        "error_code": "SOURCE_EVIDENCE_UNAVAILABLE",
        "error": "Pulse source evidence unavailable: INDEX_SNAPSHOT_UNKNOWN",
        "source_evidence": {
            "freshness": "unknown",
            "snapshot_id": None,
            "source_generation": None,
            "reason": "INDEX_SNAPSHOT_UNKNOWN",
        },
    }
