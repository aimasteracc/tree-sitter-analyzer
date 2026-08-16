"""RFC-0022 P0.5 wire-owner contract: every route echoes its action_version.

The registry in ``tree_sitter_analyzer/wire_owner.py`` is the single source
of truth; each adapter imports its constant and echoes it on success,
classified-unavailable, and missing-root responses. These tests pin the
wire bytes so a version change (or a dropped echo) turns red.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.wire_owner import ACTION_VERSIONS


def _run(coro):
    return asyncio.run(coro)


def test_wire_owner_versions_cover_every_route() -> None:
    # RFC-0022 P0.5: every adapter route must own exactly one version.
    assert ACTION_VERSIONS == {
        ("index", "status"): "index.status/v1",
        ("nav", "context"): "nav.context/v1",
        ("edit", "safe"): "edit.safe/v1",
        ("edit", "impact"): "edit.impact/v1",
        ("edit", "ast_diff"): "edit.ast_diff/v1",
        ("edit", "classify"): "edit.classify/v1",
        ("edit", "constraints"): "edit.constraints/v1",
    }


def test_wire_owner_versions_are_unique() -> None:
    assert len(set(ACTION_VERSIONS.values())) == len(ACTION_VERSIONS)


def test_nav_context_success_echoes_action_version(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    tool = CodeGraphContextTool(str(tmp_path))
    result = _run(tool.execute({"task": "does_not_exist_zzz", "max_nodes": 5}))
    assert result["action_version"] == NAV_CONTEXT_ACTION_VERSION
    assert result["action_version"] == "nav.context/v1"


def test_nav_context_unavailable_echoes_action_version() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    tool = CodeGraphContextTool()
    result = _run(
        tool.execute(
            {
                "task": "x",
                "access_mode": "read_existing",
                "snapshot_id": "s1",
                "source_generation": "1",
            }
        )
    )
    assert result["action_version"] == NAV_CONTEXT_ACTION_VERSION


def test_safe_to_edit_unavailable_echoes_action_version() -> None:
    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
    from tree_sitter_analyzer.wire_owner import EDIT_SAFE_ACTION_VERSION

    tool = SafeToEditTool(str(Path.cwd()))
    result = _run(
        tool.execute(
            {
                "file_path": "src/x.py",
                "access_mode": "read_existing",
                "snapshot_id": "s1",
                "source_generation": "1",
            }
        )
    )
    assert result["action_version"] == EDIT_SAFE_ACTION_VERSION
    assert result["action_version"] == "edit.safe/v1"


def test_change_impact_unavailable_echoes_action_version(tmp_path: Path) -> None:
    # RFC-0022 P0.4: on the Linux axis the read-existing producer is live,
    # so the unavailable fixture must be a non-repository directory — the
    # working-tree root would trigger a real full-repo capture and blow the
    # unit perf budget. The classified failure still echoes the owner
    # version; non-Linux axes keep the stable unsupported envelope.
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool
    from tree_sitter_analyzer.wire_owner import EDIT_IMPACT_ACTION_VERSION

    tool = ChangeImpactTool(str(tmp_path))
    result = _run(
        tool.execute(
            {
                "mode": "diff",
                "access_mode": "read_existing",
                "scope_paths": ["src"],
            }
        )
    )
    assert result["action_version"] == EDIT_IMPACT_ACTION_VERSION
    assert result["action_version"] == "edit.impact/v1"


def test_constraints_unavailable_echoes_action_version(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        ConstraintCheckTool,
    )
    from tree_sitter_analyzer.wire_owner import EDIT_CONSTRAINTS_ACTION_VERSION

    tool = ConstraintCheckTool(str(tmp_path))
    result = _run(
        tool.execute(
            {
                "access_mode": "read_existing",
                "diff_snapshot_id": "s1",
                "persist": False,
                "scope_paths": ["src"],
            }
        )
    )
    assert result["action_version"] == EDIT_CONSTRAINTS_ACTION_VERSION
    assert result["action_version"] == "edit.constraints/v1"


def test_constraints_missing_root_echoes_action_version() -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        ConstraintCheckTool,
    )
    from tree_sitter_analyzer.wire_owner import EDIT_CONSTRAINTS_ACTION_VERSION

    tool = ConstraintCheckTool()
    result = _run(tool.execute({}))
    assert result["action_version"] == EDIT_CONSTRAINTS_ACTION_VERSION


def test_ast_diff_unavailable_echoes_action_version(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.wire_owner import EDIT_AST_DIFF_ACTION_VERSION

    tool = ASTDiffTool(str(tmp_path))
    result = _run(
        tool.execute(
            {
                "access_mode": "read_existing",
                "diff_snapshot_id": "s1",
                "file_path": "a.py",
            }
        )
    )
    assert result["action_version"] == EDIT_AST_DIFF_ACTION_VERSION


def test_classify_unavailable_echoes_action_version(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )
    from tree_sitter_analyzer.wire_owner import EDIT_CLASSIFY_ACTION_VERSION

    tool = SemanticClassifyTool(str(tmp_path))
    result = _run(
        tool.execute(
            {
                "file_path": "a.py",
                "access_mode": "read_existing",
                "diff_snapshot_id": "s1",
            }
        )
    )
    assert result["action_version"] == EDIT_CLASSIFY_ACTION_VERSION
    assert result["action_version"] == "edit.classify/v1"


def test_read_existing_unavailable_omits_version_without_argument() -> None:
    # The shared builder only echoes a version when the caller supplies one;
    # unowned callers must not fabricate a wire owner.
    from tree_sitter_analyzer.read_existing_access import read_existing_unavailable

    result = read_existing_unavailable({"access_mode": "read_existing"})
    assert "action_version" not in result


def test_change_impact_frozen_agent_summary_keeps_wire_owner(
    tmp_path: Path, monkeypatch
) -> None:
    # REQ-1 (review round 2, #1264): edit.impact frozen success with
    # agent_summary_only=true rebuilds the envelope through an allowlist
    # builder — the wire owner echo must be written after that rebuild so
    # the summary-only variant keeps it.
    from unittest.mock import MagicMock

    import tree_sitter_analyzer.mcp.tools.change_impact_tool as tool_module
    from tree_sitter_analyzer import diff_snapshot_registry as registry
    from tree_sitter_analyzer.wire_owner import EDIT_IMPACT_ACTION_VERSION

    tool = tool_module.ChangeImpactTool(str(tmp_path))
    consumer = MagicMock()
    consumer.snapshot.assessed_scope_paths = []
    monkeypatch.setattr(registry.REGISTRY, "bind_assessed_scope", lambda *a: None)
    monkeypatch.setattr(registry.REGISTRY, "validate_publish", lambda *a: None)
    monkeypatch.setattr(
        tool_module,
        "build_frozen_scope_result",
        lambda *a: (
            {
                "success": True,
                "verdict": "SAFE",
                "mode": "diff",
                "agent_summary": {"summary_line": "s"},
            },
            [],
            [],
            [],
        ),
    )
    result = tool._execute_frozen_snapshot(
        frozen={
            "diff_snapshot_id": "ds",
            "source_generation": "g",
            "success": True,
        },
        consumer=consumer,
        mode="diff",
        scope_paths=[],
        scope_mode="report",
        output_format="json",
        agent_summary_only=True,
        compact_only=False,
    )
    assert result["action_version"] == EDIT_IMPACT_ACTION_VERSION


# Codex-adjacent P0.5 gap found by PR CI (#1297): on the Linux frozen path
# (platform authority present) the acquire-error envelopes of the three
# diff-snapshot consumers must still echo their action_version.
def test_diff_snapshot_consumers_frozen_error_echoes_action_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.mcp.tools.ast_diff_tool as ast_diff
    import tree_sitter_analyzer.mcp.tools.constraint_check_tool as constraints
    import tree_sitter_analyzer.mcp.tools.semantic_classify_tool as classify
    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        ConstraintCheckTool,
    )
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )
    from tree_sitter_analyzer.wire_owner import (
        EDIT_AST_DIFF_ACTION_VERSION,
        EDIT_CLASSIFY_ACTION_VERSION,
        EDIT_CONSTRAINTS_ACTION_VERSION,
    )

    for module in (ast_diff, constraints, classify):
        monkeypatch.setattr(
            module.read_access,
            "read_existing_platform_supported",
            lambda: True,
        )
    expected = {
        ConstraintCheckTool: (
            EDIT_CONSTRAINTS_ACTION_VERSION,
            {
                "access_mode": "read_existing",
                "diff_snapshot_id": "s1",
                "persist": False,
                "scope_paths": ["src"],
            },
        ),
        ASTDiffTool: (
            EDIT_AST_DIFF_ACTION_VERSION,
            {
                "access_mode": "read_existing",
                "diff_snapshot_id": "s1",
                "file_path": "a.py",
            },
        ),
        SemanticClassifyTool: (
            EDIT_CLASSIFY_ACTION_VERSION,
            {
                "access_mode": "read_existing",
                "diff_snapshot_id": "s1",
                "file_path": "a.py",
            },
        ),
    }
    for tool_type, (version, arguments) in expected.items():
        result = _run(tool_type(str(tmp_path)).execute(arguments))
        assert result["action_version"] == version
        assert result["success"] is False
