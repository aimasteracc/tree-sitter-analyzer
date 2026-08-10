from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_capture as capture
import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo
from tree_sitter_analyzer.source_oracle import SafePath


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_freezes_add_delete_rename_binary_and_multiple_files(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _git(root, "mv", "old.py", "renamed.py")
    (root / "gone.py").unlink()
    (root / "added.py").write_text("added = True\n")
    (root / "image.bin").write_bytes(b"a\0b")
    _git(root, "add", "-A")
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "staged", ["impact.py"])

    assert result["success"] is True
    records = result["changed_records"]
    assert [record["path"] for record in records] == [
        "added.py",
        "gone.py",
        "image.bin",
        "renamed.py",
    ]
    by_path = {record["path"]: record for record in records}
    assert by_path["added.py"]["old_available"] is False
    assert by_path["gone.py"]["new_available"] is False
    assert by_path["renamed.py"]["old_path"] == "old.py"
    assert by_path["image.bin"]["binary"] is True
    assert result["assessed_scope_paths"] == [
        "added.py",
        "gone.py",
        "image.bin",
        "impact.py",
        "renamed.py",
    ]


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_reads_index_not_workspace(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    _git(root, "add", "old.py")
    (root / "old.py").write_text("value = 3\n")
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("old.py")
    assert frozen is not None
    assert frozen.old_bytes == b"value = 1\n"
    assert frozen.new_bytes == b"value = 2\n"
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_inventory_contains_only_index_tracked_paths(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "untracked.py").write_text("untracked = True\n")
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.inventory_paths == ("gone.py", "old.py")
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_workspace_snapshot_inventory_includes_bounded_untracked_paths(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "untracked.py").write_text("untracked = True\n")
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.inventory_paths == ("gone.py", "old.py", "untracked.py")
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_untracked_executable_uses_canonical_non_git_record(tmp_path: Path) -> None:
    import base64
    import json
    import os

    root = _repo(tmp_path)
    script = root / "odd name.py"
    script.write_bytes(b"print('ok')")
    script.chmod(0o755)
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    segment = json.loads(consumer.snapshot.normalized_patch.splitlines()[-1])

    assert segment["type"] == "tsa-untracked-v1"
    assert segment["mode"] == 0o755
    assert base64.b64decode(segment["path_b64"]) == os.fsencode("odd name.py")
    assert base64.b64decode(segment["content_b64"]) == b"print('ok')"
    consumer.release()


def test_changed_entries_rejects_truncated_git_status(monkeypatch) -> None:
    monkeypatch.setattr(capture, "git_output", lambda *a, **k: b"R\0only-one-path\0")
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._rows(".", "staged", 1.0, 10)


def test_changed_entries_deduplicates_tracked_and_untracked(monkeypatch) -> None:
    outputs = iter([b"M\0same.py\0", b"same.py\0"])
    monkeypatch.setattr(capture, "git_output", lambda *a, **k: next(outputs))
    assert capture._rows(".", "diff", 1.0, 10) == [("M", None, "same.py", True)]


@pytest.mark.parametrize(
    "fault,code",
    [
        ("missing", "DIFF_SNAPSHOT_SOURCE_CHANGED"),
        ("metadata", None),
        ("capacity", "DIFF_SNAPSHOT_CAPACITY"),
    ],
)
def test_capture_payload_handles_workspace_faults(
    monkeypatch, fault: str, code: str | None
) -> None:
    safe = SafePath(
        None if fault == "missing" else b"x",
        (b"bad",) if fault == "metadata" else (),
        "file",
    )
    monkeypatch.setattr(capture, "git_output", lambda *a, **k: b"")
    monkeypatch.setattr(capture, "_rows", lambda *a: [("A", None, "x.py", False)])
    monkeypatch.setattr(capture, "_tracked_binary_paths", lambda *a: set())
    monkeypatch.setattr(capture, "safe_workspace_path", lambda *a, **k: safe)
    limit = 1 if fault == "capacity" else 100
    if code is None:
        assert capture._capture_payload(".", "diff", 1.0, limit)[1][0].new_bytes == b"x"
    else:
        with pytest.raises(snapshots.SourceOracleError, match=code):
            capture._capture_payload(".", "diff", 1.0, limit)


def test_numstat_z_binary_rename_uses_destination_path(monkeypatch) -> None:
    monkeypatch.setattr(
        capture, "git_output", lambda *args, **kwargs: b"-\t-\t\0old.bin\0new.bin\0"
    )

    result = capture._tracked_binary_paths(".", "staged", 1e20, 1024)

    assert result == {"new.bin"}


@pytest.mark.parametrize(
    "raw",
    [
        b"bad\0",
        b"-\t-\t\0old.bin",
        b"-\t-\t\0old.bin\0",
        b"-\t-\t\0\0new.bin\0",
    ],
)
def test_numstat_z_rejects_malformed_rename_continuations(monkeypatch, raw) -> None:
    from tree_sitter_analyzer.source_oracle import SourceOracleError

    monkeypatch.setattr(capture, "git_output", lambda *args, **kwargs: raw)

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._tracked_binary_paths(".", "staged", 1e20, 1024)


def test_bind_assessed_scope_rejects_materialized_capacity(
    tmp_path: Path, monkeypatch
) -> None:
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(_repo(tmp_path)), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    monkeypatch.setattr(snapshots, "MAX_MATERIALIZED_BYTES", registry.stats()[1])

    assert (
        registry.bind_assessed_scope(consumer, ["extra.py"]) == "DIFF_SNAPSHOT_CAPACITY"
    )
    consumer.release()


def test_validate_publish_rejects_released_consumer(tmp_path: Path) -> None:
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(_repo(tmp_path)), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    consumer.release()

    assert registry.validate_publish(consumer) == "DIFF_SNAPSHOT_EXPIRED"


def test_validate_publish_rejects_generation_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(_repo(tmp_path)), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *args, **kwargs: ("sg_changed", consumer.snapshot.root_identity),
    )

    assert registry.validate_publish(consumer) == "DIFF_SNAPSHOT_SOURCE_CHANGED"
    consumer.release()


def _frozen_result(
    monkeypatch,
    *,
    records,
    inventory_paths=(),
    scope_paths=None,
    bind_error=None,
    publish_error=None,
    agent_summary_only=False,
):
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(
            assessed_scope_paths=(), inventory_paths=tuple(inventory_paths)
        )
    )
    monkeypatch.setattr(
        snapshots.REGISTRY, "bind_assessed_scope", lambda *args: bind_error
    )
    monkeypatch.setattr(
        snapshots.REGISTRY, "validate_publish", lambda *args: publish_error
    )
    return ChangeImpactTool(None)._execute_frozen_snapshot(
        frozen={"success": True, "changed_records": records},
        consumer=consumer,
        mode="diff",
        scope_paths=scope_paths or [],
        scope_mode="strict",
        output_format="json",
        agent_summary_only=agent_summary_only,
        compact_only=False,
    )


def test_frozen_impact_builds_no_changes_result(monkeypatch) -> None:
    result = _frozen_result(monkeypatch, records=[])

    assert result["changed_files"] == []


def test_frozen_impact_returns_bind_failure(monkeypatch) -> None:
    result = _frozen_result(
        monkeypatch, records=[], bind_error="DIFF_SNAPSHOT_CAPACITY"
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_CAPACITY"


def test_frozen_impact_returns_publish_failure(monkeypatch) -> None:
    result = _frozen_result(
        monkeypatch, records=[], publish_error="DIFF_SNAPSHOT_SOURCE_CHANGED"
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_SOURCE_CHANGED"


def test_frozen_impact_supports_agent_summary_only(monkeypatch) -> None:
    result = _frozen_result(
        monkeypatch,
        records=[{"path": "a.py"}],
        agent_summary_only=True,
    )

    assert result["agent_summary_only"] is True


def test_frozen_scope_accepts_exact_clean_tracked_file(monkeypatch) -> None:
    # PR #1252: scope validity comes from frozen inventory, not changed records.
    result = _frozen_result(
        monkeypatch,
        records=[],
        inventory_paths=("src/clean.py",),
        scope_paths=["src/clean.py"],
    )

    assert result["success"] is True
    assert result["changed_files"] == []


def test_frozen_scope_accepts_clean_directory_prefix(monkeypatch) -> None:
    # PR #1252: a frozen descendant establishes directory-prefix existence.
    result = _frozen_result(
        monkeypatch,
        records=[],
        inventory_paths=("src/pkg/clean.py",),
        scope_paths=["src/pkg"],
    )

    assert result["success"] is True
    assert result["changed_files"] == []


def test_frozen_scope_rejects_truly_absent_path(monkeypatch) -> None:
    # PR #1252: only identities absent from the frozen inventory are invalid.
    result = _frozen_result(
        monkeypatch,
        records=[],
        inventory_paths=("src/clean.py",),
        scope_paths=["missing.py"],
    )

    assert result["success"] is True
    assert result["scope_paths_invalid"] == ["missing.py"]


@POSIX_SNAPSHOT_TEST
def test_frozen_scope_inventory_does_not_admit_post_capture_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252: later live workspace identities cannot enter the frozen epoch.
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    captured_inventory = consumer.snapshot.inventory_paths
    (root / "later.py").write_text("later = True\n")

    assert consumer.snapshot.inventory_paths == captured_inventory
    assert "later.py" not in consumer.snapshot.inventory_paths
    consumer.release()
