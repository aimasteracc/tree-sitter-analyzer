"""#1546：test_pulse 预算与截断行为组；从 test_pulse.py 原样迁移，测试主体不变。"""

from __future__ import annotations

import json

import pytest

from tests.unit.api._pulse_helpers import _MINIMAL_SYM, _call, _seed_symbol
from tree_sitter_analyzer.api.pulse import (
    CallerRef,
    CommentRef,
    FieldTruncation,
    PulseResponse,
    apply_budget,
    query_pulse,
)

_MINIMAL_PR = PulseResponse(symbol=_MINIMAL_SYM)


def _make_pr_with_comments(n: int = 10) -> PulseResponse:
    comments = tuple(
        CommentRef(line=i, text=f"comment {i}", kind="inline") for i in range(n)
    )
    return PulseResponse(symbol=_MINIMAL_SYM, comments=comments)


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


def test_budget_falls_back_when_tokenizer_breaks(monkeypatch):
    """审计 P2-1：tiktoken 已安装但初始化失败（如离线冷缓存）时回退字符估算，不崩。"""
    import sys
    from types import SimpleNamespace

    def broken(name):
        raise RuntimeError("network unavailable")

    monkeypatch.setitem(sys.modules, "tiktoken", SimpleNamespace(get_encoding=broken))
    result = apply_budget(_make_pr_with_comments(10), token_budget=1)
    assert result.comments == ()
    assert result.truncated_fields == ("comments",)


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


def test_query_pulse_import_capacity_degrades_instead_of_failing(ast_cache_conn):
    """issue #1445：超资源上限时降级而非整体报错。

    保留 #1352 的见证意图（超限不能静默返回空列表）：SQL 侧结果保留，
    且 truncated_fields 必须声明 imported_by 被截断，其余字段不受影响。
    """
    _seed_symbol(ast_cache_conn, "greet", "a.py")
    ast_cache_conn.executemany(
        "INSERT INTO ast_imports(file_path,language,module_path) VALUES ('a.py','python',?)",
        [(f"module_{i}",) for i in range(20001)],
    )
    result = query_pulse(ast_cache_conn, "a.py", "greet", max_comments=0)
    assert result is not None
    assert result.symbol.name == "greet"
    assert "imported_by" in result.truncated_fields
    # 降级只影响 imported_by 富化，其余上下文照常返回。
    assert result.callers == ()
    assert result.call_graph_available is True


def test_apply_budget_preserves_query_side_truncated_fields():
    """issue #1445：预算裁剪不得覆盖 query_pulse 已声明的截断（合并去重保序）。"""
    import dataclasses

    pr = dataclasses.replace(
        _make_pr_with_comments(10), truncated_fields=("imported_by",)
    )
    result = apply_budget(pr, token_budget=1)
    assert result.truncated_fields == ("imported_by", "comments")


@pytest.mark.parametrize(
    "count,prior,expected",
    [
        # 审计 P3-2：top-N 把 12 个导入者裁到 5 个必须可见；源未触顶时总数精确。
        (12, (), (FieldTruncation("imported_by", 5, 12, 12),)),
        # 审计 P3-2：未裁剪的字段不得出现字段内截断声明。
        (2, (), ()),
        # 审计 P3-2：源已触顶再做 top-N 时保留「总数未知」，不得改报 total=20。
        (
            20,
            (FieldTruncation("imported_by", 20, None, 21),),
            (FieldTruncation("imported_by", 5, None, 21),),
        ),
    ],
    ids=["trimmed-exact-total", "untrimmed", "capped-source-unknown-total"],
)
def test_apply_budget_field_truncation(count, prior, expected):
    files = tuple(f"m{i:02}.py" for i in range(count))
    pr = PulseResponse(_MINIMAL_SYM, imported_by=files, field_truncation=prior)
    assert apply_budget(pr, 100_000).field_truncation == expected


@pytest.mark.parametrize("count,expected", [(20, ()), (25, ((20, None, 21),))])
def test_query_pulse_imported_by_sql_cap_reports_unknown_total(
    ast_cache_conn, count, expected
):
    # 审计 P3-2：SQL 上限 20 触顶时真实总数未知，只声明下界，不捏造精确计数。
    _seed_symbol(ast_cache_conn, "run", "pkg/mod.py")
    ast_cache_conn.executemany(
        "INSERT INTO edges (source_node_id, target_node_id, kind, file_path, callee_name) "
        "VALUES (?, 'module:pkg.mod', 'imports', ?, 'pkg.mod')",
        [(f"file:c{i:02}.py", f"c{i:02}.py") for i in range(count)],
    )
    result = query_pulse(ast_cache_conn, "pkg/mod.py", "run", max_comments=0)
    assert result.imported_by == tuple(f"c{i:02}.py" for i in range(20))
    assert result.field_truncation == tuple(
        FieldTruncation("imported_by", *e) for e in expected
    )


def test_query_pulse_requested_limit_cap_reports_unknown_total(ast_cache_conn):
    # 审计 P3-2：max_callers 触顶同样只能声明下界。
    target = _seed_symbol(ast_cache_conn, "work", "b.py")
    for line in (1, 2, 3):
        _seed_symbol(ast_cache_conn, f"run{line}", "a.py")
        _call(
            ast_cache_conn, f"run{line}", "work", target_id=target, target_file="b.py"
        )
    result = query_pulse(ast_cache_conn, "b.py", "work", max_callers=2, max_comments=0)
    assert len(result.callers) == 2
    assert result.field_truncation == (FieldTruncation("callers", 2, None, 3),)
