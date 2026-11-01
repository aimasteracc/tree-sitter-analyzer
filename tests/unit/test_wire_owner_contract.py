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


def test_nav_context_unavailable_echoes_action_version(tmp_path: Path) -> None:
    import sys

    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    tool = CodeGraphContextTool(str(tmp_path))
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
    if sys.platform.startswith("linux"):
        # RFC-0022 P0.4: the certified backend runs and classifies the
        # never-published pair; the classified failure still echoes the
        # owner version.
        assert result["success"] is False
        assert result["access_state"] == "unknown"
        assert result["access_reason"] == "INDEX_SNAPSHOT_UNKNOWN"
        assert result["error_code"] == "INDEX_SNAPSHOT_UNKNOWN"
        assert result["source_snapshots"] == []


def test_safe_to_edit_unavailable_echoes_action_version() -> None:
    import sys

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
    if sys.platform.startswith("linux"):
        # RFC-0022 P0.4: the certified backend runs and classifies the
        # never-published pair; the classified failure still echoes the
        # owner version.
        assert result["success"] is False
        assert result["access_state"] == "unknown"
        assert result["access_reason"] == "INDEX_SNAPSHOT_UNKNOWN"
        assert result["error_code"] == "INDEX_SNAPSHOT_UNKNOWN"
        assert result["source_snapshots"] == []


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


# The platform gates on the diff-snapshot consumers treat
# ``read_existing_unavailable`` as potentially None; that defensive branch
# cannot be reached from a read_existing call (the mode implies the access
# token), so force it with a stub to keep the guard exact.
def test_read_existing_consumer_post_read_mismatch_preserves_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An after-read recapture failure still cites the acquired snapshot."""
    import sqlite3

    import tree_sitter_analyzer.index_snapshot as snapshot_owner
    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.index_snapshot import REGISTRY, IndexSnapshot
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.index_source_snapshot import CurrentSourceSnapshot
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    calls = {"n": 0}

    def sequence_capture(root, source_scope, deadline=None):
        calls["n"] += 1
        generation = "gen-1" if calls["n"] == 1 else "gen-2"
        return CurrentSourceSnapshot(frozenset(), "fp", generation, "exact", None)

    monkeypatch.setattr(
        snapshot_owner, "_capture_sources_with_deadline", sequence_capture
    )
    conn = sqlite3.connect(":memory:")
    snapshot = IndexSnapshot(
        None,
        "fp",
        "ifp",
        "gen-1",
        "complete",
        None,
        str(tmp_path.resolve()),
        0,
        None,
        None,
        make_source_scope_descriptor(),
    )
    published = REGISTRY.publish(snapshot, conn, 0)

    def ok_reader(snapshot, conn):
        return {"success": True, "verdict": "INFO"}

    result = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=ok_reader,
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert result["success"] is False
    assert result["error_code"] == "SOURCE_GENERATION_MISMATCH"
    assert result["access_reason"] == "SOURCE_GENERATION_MISMATCH"
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
        }
    ]
    assert result["action_version"] == NAV_CONTEXT_ACTION_VERSION


def test_read_existing_consumer_pre_read_mismatch_preserves_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-yield recapture failure still cites the acquired snapshot."""
    import sqlite3

    import tree_sitter_analyzer.index_snapshot as snapshot_owner
    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.index_snapshot import REGISTRY, IndexSnapshot
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.index_source_snapshot import CurrentSourceSnapshot
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    monkeypatch.setattr(
        snapshot_owner,
        "_capture_sources_with_deadline",
        lambda root, source_scope, deadline=None: CurrentSourceSnapshot(
            frozenset(), "fp", "gen-2", "exact", None
        ),
    )
    conn = sqlite3.connect(":memory:")
    snapshot = IndexSnapshot(
        None,
        "fp",
        "ifp",
        "gen-1",
        "complete",
        None,
        str(tmp_path.resolve()),
        0,
        None,
        None,
        make_source_scope_descriptor(),
    )
    published = REGISTRY.publish(snapshot, conn, 0)

    def ok_reader(snapshot, conn):
        return {"success": True, "verdict": "INFO"}

    result = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=ok_reader,
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert result["success"] is False
    assert result["error_code"] == "SOURCE_GENERATION_MISMATCH"
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
        }
    ]
    assert result["action_version"] == NAV_CONTEXT_ACTION_VERSION


def test_read_existing_consumer_classifies_reader_sql_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sqlite3.OperationalError from a reader maps to stable wire codes.

    Codex P2 (#1299 round-3): a damaged index column (e.g. edges lacking
    caller_name) must classify as CORRUPT_INDEX and the deadline progress
    handler's interrupt as INDEX_SNAPSHOT_DEADLINE — never escape the wire
    contract.
    """
    import sqlite3

    import tree_sitter_analyzer.index_snapshot as snapshot_owner
    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.index_snapshot import REGISTRY, IndexSnapshot
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.index_source_snapshot import CurrentSourceSnapshot
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    monkeypatch.setattr(
        snapshot_owner,
        "_capture_sources_with_deadline",
        lambda root, source_scope, deadline=None: CurrentSourceSnapshot(
            frozenset(), "fp", "gen-1", "exact", None
        ),
    )
    conn = sqlite3.connect(":memory:")
    snapshot = IndexSnapshot(
        None,
        "fp",
        "ifp",
        "gen-1",
        "complete",
        None,
        str(tmp_path.resolve()),
        0,
        None,
        None,
        make_source_scope_descriptor(),
    )
    published = REGISTRY.publish(snapshot, conn, 0)

    def reader_raising(message: str):
        def bad_reader(snapshot, conn):
            raise sqlite3.OperationalError(message)

        return bad_reader

    corrupt = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=reader_raising("no such column: caller_name"),
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert corrupt["success"] is False
    assert corrupt["error_code"] == "CORRUPT_INDEX"
    assert corrupt["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
        }
    ]

    interrupted = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=reader_raising("interrupted"),
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert interrupted["success"] is False
    assert interrupted["error_code"] == "INDEX_SNAPSHOT_DEADLINE"
    assert interrupted["action_version"] == NAV_CONTEXT_ACTION_VERSION

    # Codex P2 round-4 (C20): a damaged edges row surfaces as IndexError
    # Codex P2 round-12 (C55): a BLOB in a nominally textual edge column
    # surfaces as TypeError from parse_node_id — classified too.
    def type_error_reader(snapshot, conn):
        raise TypeError("startswith first arg must be str")

    type_error = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=type_error_reader,
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert type_error["success"] is False
    assert type_error["error_code"] == "CORRUPT_INDEX"

    # Codex P2 round-11 (C50): a metadata cell holding valid JSON of a
    # non-object type surfaces as AttributeError — classified too.
    def attr_error_reader(snapshot, conn):
        raise AttributeError("'list' object has no attribute 'get'")

    attr_error = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=attr_error_reader,
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert attr_error["success"] is False
    assert attr_error["error_code"] == "CORRUPT_INDEX"

    # from EdgeStore._edge_from_row — classified, never escaping the wire
    # contract.
    def index_error_reader(snapshot, conn):
        raise IndexError("tuple index out of range")

    index_error = read_access.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=index_error_reader,
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert index_error["success"] is False
    assert index_error["error_code"] == "CORRUPT_INDEX"
    assert index_error["action_version"] == NAV_CONTEXT_ACTION_VERSION


@pytest.mark.parametrize(
    ("tool_type", "module_name"),
    [
        ("constraints", "tree_sitter_analyzer.mcp.tools.constraint_check_tool"),
        ("ast_diff", "tree_sitter_analyzer.mcp.tools.ast_diff_tool"),
        ("classify", "tree_sitter_analyzer.mcp.tools.semantic_classify_tool"),
    ],
)
def test_diff_consumer_platform_gate_handles_none_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_type: str, module_name: str
) -> None:
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.setattr(
        module.read_access, "read_existing_platform_supported", lambda: False
    )
    if module_name == "tree_sitter_analyzer.mcp.tools.semantic_classify_tool":
        monkeypatch.setattr(
            module.read_access,
            "format_read_existing_unavailable",
            lambda *a, **k: None,
        )
    else:
        monkeypatch.setattr(module, "read_existing_unavailable", lambda *a, **k: None)
    tool_cls = getattr(
        module,
        {
            "constraints": "ConstraintCheckTool",
            "ast_diff": "ASTDiffTool",
            "classify": "SemanticClassifyTool",
        }[tool_type],
    )
    arguments = {"access_mode": "read_existing", "diff_snapshot_id": "s1"}
    if tool_type == "constraints":
        arguments["persist"] = False
        arguments["scope_paths"] = ["src"]
    else:
        arguments["file_path"] = "a.py"
    result = _run(tool_cls(str(tmp_path)).execute(arguments))
    # The guard passed through to the real backend; the frozen route then
    # reports the missing snapshot as an unknown acquisition failure.
    assert result["success"] is False
    assert result["error_code"] in {
        "DIFF_SNAPSHOT_EXPIRED",
        "DIFF_SNAPSHOT_UNKNOWN",
        "MISSING_PROJECT_ROOT",
    }


# RFC-0022 P0.4 (Codex P1 #1297, extended to the P0.1 consumers): with the
# platform authority forced open, the acquire-failure envelopes of nav.context
# and edit.safe must still echo their wire-owner action_version.
def test_nav_and_safe_certified_failure_echoes_action_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
    from tree_sitter_analyzer.wire_owner import (
        EDIT_SAFE_ACTION_VERSION,
        NAV_CONTEXT_ACTION_VERSION,
    )

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    nav = _run(
        CodeGraphContextTool(str(tmp_path)).execute(
            {
                "task": "x",
                "access_mode": "read_existing",
                "snapshot_id": "s1",
                "source_generation": "1",
                "output_format": "json",
            }
        )
    )
    assert nav["action_version"] == NAV_CONTEXT_ACTION_VERSION
    assert nav["success"] is False
    assert nav["access_reason"] == "INDEX_SNAPSHOT_UNKNOWN"
    safe = _run(
        SafeToEditTool(str(tmp_path)).execute(
            {
                "file_path": "x.py",
                "access_mode": "read_existing",
                "snapshot_id": "s1",
                "source_generation": "1",
                "output_format": "json",
            }
        )
    )
    assert safe["action_version"] == EDIT_SAFE_ACTION_VERSION
    assert safe["success"] is False
    assert safe["access_reason"] == "INDEX_SNAPSHOT_UNKNOWN"


# The P0.1 consumer seam classifies an unbound project root as a
# MISSING_PROJECT_ROOT failure envelope with evidence + action_version
# (Codex review P2, #1299): the raise is inside read_existing_index_consumer,
# not a bare escape that loses the wire contract.
def test_read_existing_consumer_unbound_root_is_classified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)

    class UnboundTool(CodeGraphContextTool):
        def __init__(self) -> None:
            super().__init__(None)

    result = _run(
        UnboundTool().execute(
            {
                "task": "x",
                "access_mode": "read_existing",
                "snapshot_id": "s1",
                "source_generation": "1",
                "output_format": "json",
            }
        )
    )
    assert result["success"] is False
    assert result["error_code"] == "MISSING_PROJECT_ROOT"
    assert result["access_reason"] == "MISSING_PROJECT_ROOT"
    assert result["access_state"] == "missing"
    assert result["action_version"] == NAV_CONTEXT_ACTION_VERSION
    assert result["source_snapshots"] == []


# A reader that returns a non-dict payload is classified as
# INDEX_SNAPSHOT_FAILED by the consumer seam (never served to the caller).
def test_read_existing_consumer_rejects_non_dict_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.index_snapshot import REGISTRY, IndexSnapshot
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
        CodeGraphContextTool,
    )
    from tree_sitter_analyzer.wire_owner import NAV_CONTEXT_ACTION_VERSION

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    # The pre-read recapture (Codex P1 #1299) must see the same generation
    # the capability was published with, exactly like a real publish would.
    import tree_sitter_analyzer.index_snapshot as snapshot_owner
    from tree_sitter_analyzer.index_source_snapshot import CurrentSourceSnapshot

    monkeypatch.setattr(
        snapshot_owner,
        "_capture_sources_with_deadline",
        lambda root, source_scope, deadline=None: CurrentSourceSnapshot(
            frozenset(), "fp", "gen-1", "exact", None
        ),
    )
    scope = make_source_scope_descriptor()
    conn = sqlite3.connect(":memory:")
    snapshot = IndexSnapshot(
        None,
        "fp",
        "ifp",
        "gen-1",
        "complete",
        None,
        str(tmp_path.resolve()),
        0,
        None,
        None,
        scope,
    )
    published = REGISTRY.publish(snapshot, conn, 0)

    import tree_sitter_analyzer.read_existing_access as seam

    def bad_reader(snapshot, conn):
        return "not-a-dict"

    result = seam.read_existing_index_consumer(
        CodeGraphContextTool(str(tmp_path)),
        {
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
            "output_format": "json",
        },
        reader=bad_reader,
        action_version=NAV_CONTEXT_ACTION_VERSION,
    )
    assert result["success"] is False
    assert result["error_code"] == "INDEX_SNAPSHOT_FAILED"
    assert result["access_reason"] == "INDEX_SNAPSHOT_FAILED"
    assert result["action_version"] == NAV_CONTEXT_ACTION_VERSION
    # Codex P2 (#1299): a failure AFTER acquisition still cites the exact
    # capability identity that was read.
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": "gen-1",
        }
    ]
