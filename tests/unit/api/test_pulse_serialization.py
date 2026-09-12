"""Pulse 序列化视图的契约测试。

从 test_pulse.py 拆出（issue #1444/#1445 的测试增长使原文件越过 800 行
治理阈值），断言原样迁移，仅调整导入位置。
"""

from __future__ import annotations

import dataclasses

import pytest

from tree_sitter_analyzer.api.pulse import (
    CalleeRef,
    CallerRef,
    CommentRef,
    GitHeat,
    ImportRef,
    PulseResponse,
    SiblingRef,
    SymbolInfo,
)
from tree_sitter_analyzer.api.serialization import serialize

_MINIMAL_SYM = SymbolInfo(
    name="fn",
    kind="function",
    file="a.py",
    line=1,
    end_line=5,
    language="python",
)

_MINIMAL_PR = PulseResponse(symbol=_MINIMAL_SYM)


@pytest.mark.parametrize("format", ["compact", "verbose"])
def test_serialization_preserves_relationship_payloads(format):
    # PR #1352：发布格式不能丢失关系身份、解析状态或 Git 消息。
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


def test_compact_availability_keys_and_conditional_reason():
    """issue #1444：iga 常驻；cgr 仅在 call_graph 不可用时出现；verbose 出全键。"""
    ok = serialize(_MINIMAL_PR, format="compact")
    assert ok["cg"] is True
    assert "cgr" not in ok
    assert ok["iga"] is True

    broken = dataclasses.replace(
        _MINIMAL_PR,
        call_graph_available=False,
        call_graph_reason="sql: call-graph not supported",
        imports_graph_available=False,
        truncated_fields=("imported_by",),
    )
    out = serialize(broken, format="compact")
    assert out["cgr"] == "sql: call-graph not supported"
    assert out["iga"] is False
    assert out["trunc"] == ["imported_by"]
    verbose = serialize(broken, format="verbose")
    assert verbose["imports_graph_available"] is False
    assert verbose["call_graph_reason"] == "sql: call-graph not supported"
