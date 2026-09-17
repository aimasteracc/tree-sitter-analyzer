#!/usr/bin/env python3
"""验证 RFC-0028 §3.1 的孤立工具处置登记与到期约束。"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer import __version__
from tree_sitter_analyzer.mcp.tool_dispositions import (
    TOOL_DISPOSITIONS,
    Disposition,
    expired_dispositions,
)

#: §3.1 测得且在删除到期弃用项后仍需保留处置记录的工具类。
_MEASURED_ORPHANS = {
    "CodeGraphPRReviewTool",
    "CodeGraphRefactorTool",
    "GetProjectSummaryTool",
    "MiddlewareDetectorTool",
    "UnreachableCodeTool",
}


def test_every_measured_orphan_has_a_disposition() -> None:
    assert set(TOOL_DISPOSITIONS) == _MEASURED_ORPHANS


def test_no_disposition_is_missing_a_reason() -> None:
    assert [n for n, d in TOOL_DISPOSITIONS.items() if not d.reason.strip()] == []


def test_deprecations_are_exactly_the_remaining_unwired_tools() -> None:
    deprecated = {n for n, d in TOOL_DISPOSITIONS.items() if d.kind == "deprecate"}
    assert deprecated == set()


def test_no_deprecation_has_expired() -> None:
    """发布版本不得包含已经到期的弃用项。"""
    assert expired_dispositions(__version__) == []


def test_expiry_fires_once_the_removal_version_ships(monkeypatch) -> None:
    monkeypatch.setitem(
        TOOL_DISPOSITIONS,
        "LegacyTool",
        Disposition(kind="deprecate", reason="测试到期边界", remove_in="1.33.0"),
    )
    assert expired_dispositions("1.32.9") == []
    assert expired_dispositions("1.33.0") == ["LegacyTool"]


def test_deprecate_without_remove_in_is_rejected() -> None:
    with pytest.raises(ValueError, match="remove_in"):
        Disposition(kind="deprecate", reason="no deadline")


def test_remove_in_on_a_wire_disposition_is_rejected() -> None:
    with pytest.raises(ValueError, match="remove_in"):
        Disposition(kind="wire", reason="wired", remove_in="1.33.0")


def test_wired_tools_are_reachable_from_the_live_registry() -> None:
    """A ``wire`` disposition is a claim about the registry — verify it.

    Reachability counts a registered *subclass*: ``edit action=pr`` holds a
    ``_PRReviewViaFacade`` instance, not a ``CodeGraphPRReviewTool`` one, and a
    gate that compares class identity reports that as an orphan forever.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(".")
    registered_mro_names = {
        base.__name__
        for _facade_name, facade in tools
        for inner in (*facade.action_map.values(),)
        for base in type(inner).__mro__
    }
    wired = {n for n, d in TOOL_DISPOSITIONS.items() if d.kind == "wire"}
    assert wired - registered_mro_names == set()


def test_deprecated_tools_are_not_reachable_from_the_live_registry() -> None:
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(".")
    registered_mro_names = {
        base.__name__
        for _facade_name, facade in tools
        for inner in (*facade.action_map.values(),)
        for base in type(inner).__mro__
    }
    deprecated = {n for n, d in TOOL_DISPOSITIONS.items() if d.kind == "deprecate"}
    assert deprecated & registered_mro_names == set()
