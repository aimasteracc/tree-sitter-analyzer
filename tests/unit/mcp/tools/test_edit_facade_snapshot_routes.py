"""Snapshot and constraint route coverage for the edit facade."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import (
    POSIX_SNAPSHOT_TEST,
    install_fake_snapshot_materializer,
    make_repo,
)


@pytest.mark.asyncio
async def test_edit_impact_preserves_legacy_branch_mode(monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    seen: list[dict[str, object]] = []

    async def fake_execute(self, arguments):
        seen.append(arguments)
        return {"success": True}

    monkeypatch.setattr(ChangeImpactTool, "execute", fake_execute)
    await build_edit_facade(None).execute({"action": "impact", "mode": "branch"})

    assert seen == [{"mode": "branch"}]


@pytest.mark.asyncio
async def test_edit_snapshot_consumer_rejects_conflicting_arguments() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        await build_edit_facade(None).execute(
            {
                "action": "ast_diff",
                "diff_snapshot_id": "ds",
                "file_path": "x.py",
                "old_code": "bad",
            }
        )


@pytest.mark.asyncio
async def test_edit_snapshot_consumer_accepts_only_frozen_arguments() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    result = await build_edit_facade(None).execute(
        {
            "action": "ast_diff",
            "diff_snapshot_id": "missing",
            "file_path": "x.py",
            "output_format": "json",
        }
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_EXPIRED"


@POSIX_SNAPSHOT_TEST
def test_edit_impact_snapshot_opt_in_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    root = make_repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    from tree_sitter_analyzer.diff_snapshot_capture import ChangedFile

    install_fake_snapshot_materializer(
        monkeypatch,
        root,
        records=[ChangedFile("old.py", "M", True, True, False)],
        inventory_paths=["old.py"],
    )
    before = {path.relative_to(root) for path in root.rglob("*")}
    facade = build_edit_facade(str(root))

    result = asyncio.run(
        facade.execute(
            {
                "action": "impact",
                "mode": "diff",
                "capture_diff_snapshot": True,
                "output_format": "json",
            }
        )
    )

    assert result["success"] is True
    assert result["changed_files"] == ["old.py"]
    assert {path.relative_to(root) for path in root.rglob("*")} == before
    assert (
        snapshots.close_route_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )


@POSIX_SNAPSHOT_TEST
def test_edit_impact_rejects_clean_tracked_transient_write_restore(
    tmp_path: Path, monkeypatch
) -> None:
    """Strict impact cannot certify analysis that observed a transient clean file."""
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade
    from tree_sitter_analyzer.mcp.tools.utils import change_impact_analysis

    # RFC-0022 P0.2 review 2026-07-01: dependency analysis consumed a clean
    # tracked transient and certified success after the callback restored it.
    root = make_repo(tmp_path)
    changed = root / "old.py"
    dependency = root / "gone.py"
    changed.write_text("value = 2\n")
    original = dependency.read_bytes()
    from tree_sitter_analyzer.diff_snapshot_capture import ChangedFile

    install_fake_snapshot_materializer(
        monkeypatch,
        root,
        records=[ChangedFile("old.py", "M", True, True, False)],
        inventory_paths=["old.py"],
    )
    observations: list[bytes] = []

    def legacy_dependency_analysis(_project_root):
        dependency.write_bytes(b"TRANSIENT = True\n")
        observations.append(dependency.read_bytes())
        dependency.write_bytes(original)
        return None

    monkeypatch.setattr(
        change_impact_analysis, "_load_dependency_graph", legacy_dependency_analysis
    )

    result = asyncio.run(
        build_edit_facade(str(root)).execute(
            {
                "action": "impact",
                "mode": "diff",
                "capture_diff_snapshot": True,
                "output_format": "json",
            }
        )
    )

    assert observations == []
    assert dependency.read_bytes() == original
    assert result["affected_files_unknown"] is True


def test_edit_release_snapshot_is_same_process_reachable_and_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3746878592.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    root = make_repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "REGISTRY", registry)
    created = registry.create(str(root), "diff", [])
    args = {
        "action": "release_snapshot",
        "diff_snapshot_id": created["diff_snapshot_id"],
        "route_lease_id": created["route_lease_id"],
        "output_format": "json",
    }
    facade = build_edit_facade(str(root))

    first = asyncio.run(facade.execute(args))
    second = asyncio.run(facade.execute(args))

    assert (first["released"], second["released"]) == (True, True)


def test_edit_release_snapshot_rejects_wrong_ownership_token(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3746878592.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    root = make_repo(tmp_path)
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "REGISTRY", registry)
    created = registry.create(str(root), "diff", [])

    result = asyncio.run(
        build_edit_facade(str(root)).execute(
            {
                "action": "release_snapshot",
                "diff_snapshot_id": created["diff_snapshot_id"],
                "route_lease_id": "wrong",
                "output_format": "json",
            }
        )
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_LEASE_MISMATCH"


def test_edit_release_snapshot_rejects_alternate_source_arguments() -> None:
    # PR #1252 review thread 3746878592.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        asyncio.run(
            build_edit_facade(".").execute(
                {
                    "action": "release_snapshot",
                    "diff_snapshot_id": "ds",
                    "route_lease_id": "lease",
                    "file_path": "alternate.py",
                }
            )
        )


def test_edit_release_snapshot_requires_both_ownership_ids() -> None:
    # PR #1252 review thread 3746878592.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    with pytest.raises(
        ValueError, match="diff_snapshot_id and route_lease_id are required"
    ):
        asyncio.run(
            build_edit_facade(".").execute(
                {"action": "release_snapshot", "diff_snapshot_id": "ds"}
            )
        )


def test_change_impact_annotation_is_non_idempotent_for_optional_capture() -> None:
    # PR #1252 review thread 3747113064.
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    definition = ChangeImpactTool().get_tool_definition()
    assert definition["annotations"]["idempotentHint"] is False


_READ_EXISTING_ROUTE_ARGS: dict[str, dict[str, object]] = {
    "safe": {
        "file_path": "inside.py",
        "edit_type": "fix_bug",
        "access_mode": "read_existing",
        "snapshot_id": "idxsnap_test",
        "source_generation": "idxsrc-v3:test",
    },
    "impact": {
        "mode": "diff",
        "include_tests": False,
        "scope_paths": ["inside.py"],
        "access_mode": "read_existing",
    },
    "ast_diff": {
        "diff_snapshot_id": "ds_test",
        "file_path": "inside.py",
        "include_node_bodies": False,
        "access_mode": "read_existing",
    },
    "classify": {
        "diff_snapshot_id": "ds_test",
        "file_path": "inside.py",
        "include_ast_nodes": False,
        "hunk_cap": 2,
        "access_mode": "read_existing",
    },
    "constraints": {
        "persist": False,
        "diff_snapshot_id": "ds_test",
        "scope_paths": ["inside.py"],
        "access_mode": "read_existing",
        "snapshot_id": "idxsnap_test",
        "source_generation": "idxsrc-v3:test",
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", _READ_EXISTING_ROUTE_ARGS)
async def test_edit_read_existing_arguments_survive_exact_projection(
    action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(None)
    seen: list[dict[str, object]] = []

    async def record(arguments):
        seen.append(dict(arguments))
        return {"success": True}

    monkeypatch.setattr(facade.action_map[action], "execute", record)
    arguments = {**_READ_EXISTING_ROUTE_ARGS[action], "output_format": "json"}
    result = await facade.execute({"action": action, **arguments})

    assert (seen, result) == ([arguments], {"success": True})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "reason"),
    [
        # nav-backed consumers still lack a certified read_existing backend.
        ("safe", "READ_EXISTING_AUTHORITY_UNCERTIFIED"),
    ],
)
@pytest.mark.parametrize("output_format", ["json", "toon"])
async def test_edit_read_existing_returns_exact_access_evidence(
    tmp_path: Path, action: str, reason: str, output_format: str
) -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    (tmp_path / "inside.py").write_text("value = 1\n")
    result = await build_edit_facade(str(tmp_path)).execute(
        {
            "action": action,
            **_READ_EXISTING_ROUTE_ARGS[action],
            "output_format": output_format,
        }
    )

    assert {
        key: result[key]
        for key in (
            "success",
            "access_mode",
            "access_state",
            "access_reason",
            "source_snapshots",
            "output_format",
        )
    } == {
        "success": True,
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": reason,
        "source_snapshots": [],
        "output_format": output_format,
    }
    assert (result.get("format"), "toon_content" in result) == (
        ("toon", True) if output_format == "toon" else (None, False)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["ast_diff", "classify", "constraints"])
@pytest.mark.parametrize("output_format", ["json", "toon"])
async def test_edit_snapshot_consumers_read_existing_are_platform_aware(
    tmp_path: Path, action: str, output_format: str
) -> None:
    """RFC-0022 P0.4: diff-snapshot consumers depend on the certified axis.

    On non-Linux axes they return the stable uncertified classification; on
    Linux they run the in-memory registry consumer and classify the missing
    snapshot (the fake ``ds_test`` id) as an unknown acquisition failure.
    """
    import sys

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    (tmp_path / "inside.py").write_text("value = 1\n")
    result = await build_edit_facade(str(tmp_path)).execute(
        {
            "action": action,
            **_READ_EXISTING_ROUTE_ARGS[action],
            "output_format": output_format,
        }
    )

    if sys.platform.startswith("linux"):
        assert result["success"] is False
        assert result["access_mode"] == "read_existing"
        assert result["access_state"] == "unknown"
        assert result["access_reason"] == "DIFF_SNAPSHOT_EXPIRED"
        assert result["error_code"] == "DIFF_SNAPSHOT_EXPIRED"
        assert result["source_snapshots"] == []
    else:
        assert {
            key: result[key]
            for key in (
                "success",
                "access_mode",
                "access_state",
                "access_reason",
                "source_snapshots",
                "output_format",
            )
        } == {
            "success": True,
            "access_mode": "read_existing",
            "access_state": "unknown",
            "access_reason": "READ_EXISTING_AUTHORITY_UNCERTIFIED",
            "source_snapshots": [],
            "output_format": output_format,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("output_format", ["json", "toon"])
async def test_edit_impact_read_existing_gate_is_platform_aware(
    tmp_path: Path, output_format: str
) -> None:
    """RFC-0022 P0.4: impact's producer route depends on the certified axis.

    On non-Linux axes (no pinned native authority) the route returns the
    stable unsupported classification; on Linux it attempts the zero-write
    backend and classifies failures with the exact capture code.
    """
    import sys

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    (tmp_path / "inside.py").write_text("value = 1\n")
    arguments = {
        **_READ_EXISTING_ROUTE_ARGS["impact"],
        "output_format": output_format,
    }
    result = await build_edit_facade(str(tmp_path)).execute(
        {"action": "impact", **arguments}
    )

    if sys.platform.startswith("linux"):
        # The fixture is not a git repository: the producer fails closed
        # with the oracle's stable code and the exact access evidence.
        assert {
            key: result[key]
            for key in (
                "success",
                "access_mode",
                "access_state",
                "access_reason",
                "source_snapshots",
                "output_format",
            )
        } == {
            "success": False,
            "access_mode": "read_existing",
            "access_state": "unknown",
            "access_reason": "DIFF_SNAPSHOT_GIT_ERROR",
            "source_snapshots": [],
            "output_format": output_format,
        }
        assert result["error_code"] == "DIFF_SNAPSHOT_GIT_ERROR"
    else:
        assert {
            key: result[key]
            for key in (
                "success",
                "access_mode",
                "access_state",
                "access_reason",
                "source_snapshots",
                "output_format",
            )
        } == {
            "success": True,
            "access_mode": "read_existing",
            "access_state": "unknown",
            "access_reason": "DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED",
            "source_snapshots": [],
            "output_format": output_format,
        }


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="tracked: RFC-0022 P0.4 producer route is Linux-certified only",
)
@pytest.mark.asyncio
async def test_edit_impact_read_existing_producer_publishes_snapshot(
    tmp_path: Path,
) -> None:
    """The zero-write producer publishes both IDs with full access evidence."""
    import subprocess

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for cfg in (
        ["user.email", "t@t"],
        ["user.name", "t"],
        ["maintenance.auto", "false"],
        ["gc.auto", "0"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), "config", *cfg], check=True)
    (tmp_path / "inside.py").write_text("value = 1\n")
    (tmp_path / "keep.py").write_text("keep = True\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    (tmp_path / "inside.py").write_text("value = 2\n")
    (tmp_path / "new.py").write_text("x = 1\n")

    arguments = dict(_READ_EXISTING_ROUTE_ARGS["impact"])
    arguments["scope_paths"] = []
    result = await build_edit_facade(str(tmp_path)).execute(
        {
            "action": "impact",
            **arguments,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["access_mode"] == "read_existing"
    assert result["access_state"] == "available"
    assert result["access_reason"] is None
    assert result["source_snapshots"] == [
        {
            "kind": "diff",
            "snapshot_id": result["diff_snapshot_id"],
            "source_generation": result["source_generation"],
        }
    ]
    assert result["diff_snapshot_id"].startswith("ds_")
    assert result["route_lease_id"].startswith("dl_")
    assert [
        (record["path"], record["status"]) for record in result["changed_records"]
    ] == [
        ("inside.py", "M"),
        ("new.py", "A"),
    ]
    assert "assessed_scope_paths" in result
    assert result["action_version"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "parameter", "value", "message"),
    [
        (
            "safe",
            "edit_type",
            "bogus",
            "edit_type must be one of ['add_feature', 'behavior_change', "
            "'delete', 'fix_bug', 'refactor', 'rename', 'signature_change']",
        ),
        (
            "impact",
            "include_tests",
            "yes",
            "include_tests must have JSON type boolean",
        ),
        (
            "ast_diff",
            "include_node_bodies",
            "yes",
            "include_node_bodies must have JSON type boolean",
        ),
        ("classify", "hunk_cap", "2", "hunk_cap must have JSON type integer"),
        (
            "constraints",
            "output_format",
            "yaml",
            "output_format must be one of ['json', 'toon']",
        ),
    ],
)
async def test_edit_read_existing_rejects_malformed_action_schema_before_success(
    tmp_path: Path, action: str, parameter: str, value: object, message: str
) -> None:
    # RFC-0022 P0.4 review 2026-07-02: an unavailable adapter must still
    # validate its complete action schema before returning classified success.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    (tmp_path / "inside.py").write_text("value = 1\n")
    arguments = {
        **_READ_EXISTING_ROUTE_ARGS[action],
        "output_format": "json",
        parameter: value,
    }

    with pytest.raises(ValueError) as error:
        await build_edit_facade(str(tmp_path)).execute({"action": action, **arguments})

    assert str(error.value) == message


def test_edit_constraints_snapshot_parameters_are_schema_discoverable() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    properties = build_edit_facade(None).get_tool_definition()["inputSchema"][
        "properties"
    ]

    assert properties["persist"] == {
        "type": "boolean",
        "default": True,
        "description": (
            "Write evaluated violations through to the cache. Set false for "
            "RFC-0022 read-only evaluation; no database or file is created."
        ),
    }
    assert properties["scope_paths"] == {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Primitive-issued frozen scope for action=constraints, or impact "
            "capture scope for action=impact."
        ),
    }


@pytest.mark.asyncio
async def test_edit_constraints_rejects_snapshot_without_persist_false() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    with pytest.raises(ValueError, match="diff_snapshot_id requires persist=false"):
        await build_edit_facade(None).execute(
            {
                "action": "constraints",
                "diff_snapshot_id": "ds_contract",
                "scope_paths": ["src/a.py"],
            }
        )


@pytest.mark.asyncio
async def test_edit_rejects_sibling_access_mode_before_backend(monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(None)

    async def poison(_arguments):
        pytest.fail("guard backend must not run")

    monkeypatch.setattr(facade.action_map["guard"], "execute", poison)
    result = await facade.execute({"action": "guard", "access_mode": "read_existing"})

    assert (result["success"], result["verdict"], result["error"]) == (
        False,
        "ERROR",
        "parameter 'access_mode' applies only to action(s): ast_diff, classify, constraints, impact, safe",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parameter", "value", "allowed"),
    [
        ("capture_diff_snapshot", True, "impact"),
        ("persist", False, "constraints"),
        (
            "diff_snapshot_id",
            "ds_contract",
            "ast_diff, classify, constraints, release_snapshot",
        ),
        ("route_lease_id", "lease_contract", "release_snapshot"),
    ],
)
async def test_edit_action_controls_are_rejected_outside_supported_actions(
    parameter, value, allowed
) -> None:
    # PR #1254 review 3771670610: explicit action intent cannot be discarded.
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    result = await build_edit_facade(None).execute(
        {"action": "safe", "file_path": "src/a.py", parameter: value}
    )

    assert (result["success"], result["verdict"], result["error"]) == (
        False,
        "ERROR",
        f"parameter {parameter!r} applies only to action(s): {allowed}",
    )


@pytest.mark.asyncio
async def test_edit_impact_read_existing_platform_gate_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forcing the non-certified axis returns the stable unsupported result."""
    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: False)
    (tmp_path / "inside.py").write_text("value = 1\n")
    result = await build_edit_facade(str(tmp_path)).execute(
        {
            "action": "impact",
            **_READ_EXISTING_ROUTE_ARGS["impact"],
            "output_format": "json",
        }
    )
    assert {
        key: result[key]
        for key in (
            "success",
            "access_mode",
            "access_state",
            "access_reason",
            "source_snapshots",
        )
    } == {
        "success": True,
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": "DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED",
        "source_snapshots": [],
    }
    assert result["action_version"]


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="tracked: RFC-0022 P0.4 producer route is Linux-certified only",
)
@pytest.mark.asyncio
async def test_edit_impact_read_existing_acquire_failure_classifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An acquire failure after capture closes the lease and classifies."""
    import subprocess

    import tree_sitter_analyzer.diff_snapshot_registry as snapshots
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for cfg in (
        ["user.email", "t@t"],
        ["user.name", "t"],
        ["maintenance.auto", "false"],
        ["gc.auto", "0"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), "config", *cfg], check=True)
    (tmp_path / "inside.py").write_text("value = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    (tmp_path / "inside.py").write_text("value = 2\n")

    closed: list[str] = []
    original_close = snapshots.REGISTRY.close_lease

    def fake_acquire(snapshot_id, project_root, **kwargs):
        return None, "DIFF_SNAPSHOT_EXPIRED"

    def spy_close(snapshot_id, lease):
        closed.append(snapshot_id)
        return original_close(snapshot_id, lease)

    monkeypatch.setattr(snapshots.REGISTRY, "acquire", fake_acquire)
    monkeypatch.setattr(snapshots.REGISTRY, "close_lease", spy_close)
    try:
        tool = ChangeImpactTool(str(tmp_path))
        result = await tool.execute(
            {
                "mode": "diff",
                "access_mode": "read_existing",
                "scope_paths": [],
                "output_format": "json",
            }
        )
    finally:
        monkeypatch.undo()
    assert result["success"] is False
    assert result["access_state"] == "unknown"
    assert result["access_reason"] == "DIFF_SNAPSHOT_EXPIRED"
    assert result["error_code"] == "DIFF_SNAPSHOT_EXPIRED"
    assert len(closed) == 1


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="tracked: RFC-0022 P0.4 consumer route is Linux-certified only",
)
@pytest.mark.asyncio
async def test_edit_snapshot_consumers_read_existing_consume_snapshot(
    tmp_path: Path,
) -> None:
    """The diff-snapshot consumers serve a published snapshot read-only."""
    import subprocess

    from tree_sitter_analyzer.diff_snapshot_registry import REGISTRY, reset_registry
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for cfg in (
        ["user.email", "t@t"],
        ["user.name", "t"],
        ["maintenance.auto", "false"],
        ["gc.auto", "0"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), "config", *cfg], check=True)
    (tmp_path / "base.py").write_text("value = 1\n")
    (tmp_path / "keep.py").write_text("keep = True\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    (tmp_path / "base.py").write_text("value = 2\n")
    (tmp_path / "new.py").write_text("x = 1\n")

    reset_registry()
    created = REGISTRY.create(str(tmp_path), "diff", [], readonly=True)
    assert created.get("success"), created
    snapshot_id = str(created["diff_snapshot_id"])
    scope = [str(path) for path in created["assessed_scope_paths"]]
    facade = build_edit_facade(str(tmp_path))
    results = {}
    for action, arguments in (
        (
            "constraints",
            {
                "diff_snapshot_id": snapshot_id,
                "scope_paths": scope,
                "persist": False,
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
        (
            "ast_diff",
            {
                "diff_snapshot_id": snapshot_id,
                "file_path": "base.py",
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
        (
            "classify",
            {
                "diff_snapshot_id": snapshot_id,
                "file_path": "base.py",
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
    ):
        result = await facade.execute({"action": action, **arguments})
        results[action] = result
        assert result["success"] is True
        assert result["access_mode"] == "read_existing"
        assert result["access_state"] == "available"
        assert result["access_reason"] is None
        assert result["source_snapshots"] == [
            {
                "kind": "diff",
                "snapshot_id": snapshot_id,
                "source_generation": created["source_generation"],
            }
        ]

    assert results["constraints"]["state"] == "not_applicable"
    assert results["constraints"]["reason"] == "NO_CONFIG"
    # Codex P2 (#1297): base.py changed value = 1 -> value = 2, so both
    # consumers must report the change; NOT_FOUND would hide a backend that
    # silently lost the captured diff.
    assert results["ast_diff"]["verdict"] == "INFO"
    assert results["classify"]["verdict"] == "INFO"


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="tracked: RFC-0022 P0.4 secure-fd consume backend is POSIX-only",
)
@pytest.mark.asyncio
async def test_edit_snapshot_consumers_read_existing_consume_portable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force the frozen consume backend on POSIX developer loops.

    Linux runs the identical route under the pinned strace authority; this
    portable variant (platform gate opened) gives macOS local coverage of
    the same frozen backend so the patch-coverage gate is exact.
    """
    import subprocess

    from tree_sitter_analyzer import read_existing_access as read_access
    from tree_sitter_analyzer.diff_snapshot_registry import REGISTRY, reset_registry
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for cfg in (
        ["user.email", "t@t"],
        ["user.name", "t"],
        ["maintenance.auto", "false"],
        ["gc.auto", "0"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), "config", *cfg], check=True)
    (tmp_path / "base.py").write_text("value = 1\n")
    (tmp_path / "keep.py").write_text("keep = True\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    (tmp_path / "base.py").write_text("value = 2\n")
    (tmp_path / "new.py").write_text("x = 1\n")

    reset_registry()
    created = REGISTRY.create(str(tmp_path), "diff", [], readonly=True)
    assert created.get("success"), created
    snapshot_id = str(created["diff_snapshot_id"])
    scope = [str(path) for path in created["assessed_scope_paths"]]
    facade = build_edit_facade(str(tmp_path))
    for action, arguments in (
        (
            "constraints",
            {
                "diff_snapshot_id": snapshot_id,
                "scope_paths": scope,
                "persist": False,
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
        (
            "ast_diff",
            {
                "diff_snapshot_id": snapshot_id,
                "file_path": "base.py",
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
        (
            "classify",
            {
                "diff_snapshot_id": snapshot_id,
                "file_path": "base.py",
                "access_mode": "read_existing",
                "output_format": "json",
            },
        ),
    ):
        result = await facade.execute({"action": action, **arguments})
        assert result["success"] is True
        assert result["access_state"] == "available"
        assert result["source_snapshots"] == [
            {
                "kind": "diff",
                "snapshot_id": snapshot_id,
                "source_generation": created["source_generation"],
            }
        ]
