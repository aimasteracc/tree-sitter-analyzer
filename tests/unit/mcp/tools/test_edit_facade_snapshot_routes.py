"""Snapshot and constraint route coverage for the edit facade."""

from __future__ import annotations

import asyncio
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
        ("safe", "READ_EXISTING_AUTHORITY_UNCERTIFIED"),
        ("impact", "DIFF_SNAPSHOT_READ_EXISTING_UNSUPPORTED"),
        ("ast_diff", "READ_EXISTING_AUTHORITY_UNCERTIFIED"),
        ("classify", "READ_EXISTING_AUTHORITY_UNCERTIFIED"),
        ("constraints", "READ_EXISTING_AUTHORITY_UNCERTIFIED"),
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
