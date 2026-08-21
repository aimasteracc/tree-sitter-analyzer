#!/usr/bin/env python3
"""Tests for the RFC-0028 §3.1 orphan-disposition registry.

The registry exists so the six measured orphans resolve into
``wire`` / ``delete`` / ``deprecate-with-an-expiry`` instead of an allowlist.
These tests are what make the distinction real: a deprecation whose deadline
has arrived fails, and a ``wire`` disposition is checked against the live
registry rather than taken on trust.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer import __version__
from tree_sitter_analyzer.mcp.tool_dispositions import (
    TOOL_DISPOSITIONS,
    Disposition,
    expired_dispositions,
)

#: The exact set §3.1 measured on 2026-08-19, plus nothing else. A new name
#: here means a new orphan appeared and needs its own decision.
_MEASURED_ORPHANS = {
    "CodeGraphPRReviewTool",
    "CodeGraphRefactorTool",
    "GetProjectSummaryTool",
    "MiddlewareDetectorTool",
    "UniversalAnalyzeTool",
    "UnreachableCodeTool",
}


def test_every_measured_orphan_has_a_disposition() -> None:
    assert set(TOOL_DISPOSITIONS) == _MEASURED_ORPHANS


def test_no_disposition_is_missing_a_reason() -> None:
    assert [n for n, d in TOOL_DISPOSITIONS.items() if not d.reason.strip()] == []


def test_deprecations_are_exactly_the_three_unwired_tools() -> None:
    deprecated = {n for n, d in TOOL_DISPOSITIONS.items() if d.kind == "deprecate"}
    assert deprecated == {
        "MiddlewareDetectorTool",
        "UniversalAnalyzeTool",
        "UnreachableCodeTool",
    }


def test_no_deprecation_has_expired() -> None:
    """The clause that stops a deprecation becoming a permanent allowlist.

    When this goes red, the named tools must be wired or deleted — bumping
    ``remove_in`` to silence it is the anti-pattern RFC-0028 §3.1 forbids.
    """
    assert expired_dispositions(__version__) == []


def test_expiry_fires_once_the_removal_version_ships() -> None:
    assert expired_dispositions("1.33.0") == [
        "MiddlewareDetectorTool",
        "UniversalAnalyzeTool",
        "UnreachableCodeTool",
    ]


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
