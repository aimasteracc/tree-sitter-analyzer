from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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
def test_capacity_is_stable_error_and_close_releases_charge(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "MAX_SNAPSHOTS", 1)
    first = registry.create(str(root), "diff", [])

    second = registry.create(str(root), "diff", [])

    assert second == {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}
    assert (
        registry.close_lease(
            str(first["diff_snapshot_id"]), str(first["route_lease_id"])
        )
        is True
    )
    assert registry.stats() == (0, 0)


@POSIX_SNAPSHOT_TEST
def test_expiry_retains_active_consumer_bytes_until_release(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    now = [10.0]
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    charged = registry.stats()[1]

    now[0] += snapshots.HARD_LIFETIME_SECONDS
    blocked, blocked_error = registry.acquire(
        str(result["diff_snapshot_id"]), str(root)
    )

    assert blocked is None
    assert blocked_error == "DIFF_SNAPSHOT_EXPIRED"
    assert registry.stats() == (1, charged)
    assert consumer is not None
    consumer.release()
    assert registry.stats() == (0, 0)


@POSIX_SNAPSHOT_TEST
def test_snapshot_id_is_bound_to_exact_root_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path / "one")
    other = _repo(tmp_path / "two")
    (root / "old.py").write_text("value = 2\n")
    (other / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])

    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(other))

    assert consumer is None
    assert error == "DIFF_SNAPSHOT_ROOT_MISMATCH"


def test_reset_rejects_active_consumer_then_clears(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_CONSUMERS_ACTIVE"):
        registry.reset()
    consumer.release()
    registry.reset()
    assert registry.stats() == (0, 0)


def test_snapshot_consumer_schema_rejects_live_arguments(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )

    arguments = {"diff_snapshot_id": "ds_x", "file_path": "old.py", "old_ref": "HEAD"}

    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        ASTDiffTool(str(tmp_path)).validate_arguments(arguments)
    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        SemanticClassifyTool(str(tmp_path)).validate_arguments(arguments)


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


def test_consumer_lifecycle_is_idempotent_context_managed_and_thread_owned(
    tmp_path: Path, monkeypatch
) -> None:
    import concurrent.futures

    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        wrong_thread = pool.submit(consumer.release).exception()
    assert isinstance(wrong_thread, RuntimeError)
    assert str(wrong_thread) == "DIFF_SNAPSHOT_WRONG_THREAD"
    with consumer as frozen:
        assert frozen.file("../bad") is None
    consumer.release()
    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(str(result["diff_snapshot_id"]), "bad-pin", 0)


def test_registry_defensive_capacity_and_mode_errors(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()

    assert registry.create(str(root), "branch", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_MODE",
    }
    registry._charged_bytes = snapshots.MAX_MATERIALIZED_BYTES
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPACITY",
    }
    registry._erase("unknown")
    called = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(snapshots.REGISTRY, "reset", lambda: called.append(True))
    snapshots.reset_registry()
    monkeypatch.undo()
    assert called == [True]


def _created(tmp_path: Path, monkeypatch):
    """Create registry state without invoking the POSIX workspace oracle."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    identity = snapshots.RootIdentity(str(tmp_path), 1, 2)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(tmp_path), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *args, **kwargs: ("sg_test", identity)
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *args: (b"", ()))
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "diff", [])
    return tmp_path, registry, result


def test_create_releases_reservation_after_unexpected_capture_error(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (_ for _ in ()).throw(RuntimeError())
    )
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert registry._reservations == {}


def test_create_rejects_payload_larger_than_reservation(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    identity = snapshots.RootIdentity(str(root), 1, 2)
    monkeypatch.setattr(snapshots, "MAX_MATERIALIZED_BYTES", 1)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a, **k: ("sg", identity)
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *a: (b"xx", ()))
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPACITY",
    }


def test_create_rejects_generation_change_after_impact(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    identity = snapshots.RootIdentity(str(root), 1, 2)
    generations = iter([("before", identity), ("after", identity)])
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a, **k: next(generations)
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *a: (b"", ()))
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED",
    }


def test_create_rejects_capture_that_exhausts_lifetime(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    times = iter(
        [0.0, 0.0, snapshots.HARD_LIFETIME_SECONDS, snapshots.HARD_LIFETIME_SECONDS]
    )
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: next(times))
    identity = snapshots.RootIdentity(str(root), 1, 2)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a, **k: ("sg", identity)
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *a: (b"", ()))
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_TIMEOUT",
    }


def test_acquire_translates_root_error(monkeypatch) -> None:
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(
        snapshots,
        "canonical_root",
        lambda value: (_ for _ in ()).throw(snapshots.SourceOracleError("ROOT")),
    )
    assert registry.acquire("missing", ".") == (None, "ROOT")


def test_acquire_releases_reserved_pin_after_oracle_error(
    tmp_path: Path, monkeypatch
) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a, **k: (_ for _ in ()).throw(snapshots.SourceOracleError("GEN")),
    )
    assert registry.acquire(str(result["diff_snapshot_id"]), str(root)) == (None, "GEN")
    assert next(iter(registry._states.values())).pins == {}


def test_bind_assessed_scope_translates_invalid_path(
    tmp_path: Path, monkeypatch
) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    assert (
        registry.bind_assessed_scope(consumer, ["../bad"])
        == "DIFF_SNAPSHOT_INVALID_PATH"
    )
    consumer.release()


def test_bind_assessed_scope_rejects_released_consumer(
    tmp_path: Path, monkeypatch
) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    consumer.release()
    assert registry.bind_assessed_scope(consumer, ["ok.py"]) == "DIFF_SNAPSHOT_EXPIRED"


def test_verify_translates_oracle_error(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a: (_ for _ in ()).throw(snapshots.SourceOracleError("GEN")),
    )
    assert registry.verify(consumer) == "GEN"
    consumer.release()


def test_release_rejects_wrong_thread_owner(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert isinstance(consumer, snapshots.SnapshotConsumer)
    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(consumer.snapshot.snapshot_id, consumer._pin, -1)
    consumer.release()


def test_release_rejects_pin_underflow(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    assert (
        registry.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )
    consumer.release()
    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(consumer.snapshot.snapshot_id, consumer._pin, consumer._owner)


def test_close_lease_rejects_wrong_lease(tmp_path: Path, monkeypatch) -> None:
    _, registry, result = _created(tmp_path, monkeypatch)
    assert registry.close_lease(str(result["diff_snapshot_id"]), "wrong") is False


def test_changed_entries_rejects_truncated_git_status(monkeypatch) -> None:
    monkeypatch.setattr(snapshots, "git_output", lambda *a, **k: b"R\0only-one-path\0")
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        snapshots._rows(".", "staged", 1.0, 10)


def test_changed_entries_deduplicates_tracked_and_untracked(monkeypatch) -> None:
    outputs = iter([b"M\0same.py\0", b"same.py\0"])
    monkeypatch.setattr(snapshots, "git_output", lambda *a, **k: next(outputs))
    assert snapshots._rows(".", "diff", 1.0, 10) == [("M", None, "same.py", True)]


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
    monkeypatch.setattr(snapshots, "git_output", lambda *a, **k: b"")
    monkeypatch.setattr(snapshots, "_rows", lambda *a: [("A", None, "x.py", False)])
    monkeypatch.setattr(snapshots, "_tracked_binary_paths", lambda *a: set())
    monkeypatch.setattr(snapshots, "safe_workspace_path", lambda *a, **k: safe)
    limit = 1 if fault == "capacity" else 100
    if code is None:
        assert (
            snapshots._capture_payload(".", "diff", 1.0, limit)[1][0].new_bytes == b"x"
        )
    else:
        with pytest.raises(snapshots.SourceOracleError, match=code):
            snapshots._capture_payload(".", "diff", 1.0, limit)


def test_create_rejects_oracle_root_identity_drift(tmp_path: Path, monkeypatch) -> None:
    root = _repo(tmp_path)
    identity = snapshots.RootIdentity(str(root), 1, 2)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a, **k: ("sg", snapshots.RootIdentity(str(root), 3, 4)),
    )
    assert snapshots.DiffSnapshotRegistry().create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_ROOT_MISMATCH",
    }


def test_acquire_rejects_generation_drift(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    identity = next(iter(registry._states.values())).snapshot.root_identity
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a: ("different", identity)
    )
    assert registry.acquire(str(result["diff_snapshot_id"]), str(root)) == (
        None,
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


def test_verify_rejects_root_identity_drift(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a: (
            consumer.snapshot.source_generation,
            snapshots.RootIdentity(str(root), -1, -1),
        ),
    )
    assert registry.verify(consumer) == "DIFF_SNAPSHOT_ROOT_MISMATCH"
    consumer.release()


def test_sweep_erases_expired_unpinned_snapshot(tmp_path: Path, monkeypatch) -> None:
    _, registry, _ = _created(tmp_path, monkeypatch)
    next(iter(registry._states.values())).expired = True
    assert registry.stats() == (0, 0)


def test_numstat_z_binary_rename_uses_destination_path(monkeypatch) -> None:
    monkeypatch.setattr(
        snapshots, "git_output", lambda *args, **kwargs: b"-\t-\t\0old.bin\0new.bin\0"
    )

    result = snapshots._tracked_binary_paths(".", "staged", 1e20, 1024)

    assert result == {"new.bin"}


def test_create_rejects_excessive_scope_item_count() -> None:
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(
        ".", "diff", [f"path-{index}" for index in range(snapshots.MAX_SCOPE_PATHS + 1)]
    )

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}


def test_validate_publish_rejects_snapshot_expired_while_pinned(
    tmp_path: Path,
) -> None:
    now = [0.0]
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    now[0] = snapshots.HARD_LIFETIME_SECONDS

    result = registry.validate_publish(consumer)

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()


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

    monkeypatch.setattr(snapshots, "git_output", lambda *args, **kwargs: raw)

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        snapshots._tracked_binary_paths(".", "staged", 1e20, 1024)


def test_create_rejects_invalid_scope_storage_inputs() -> None:
    registry = snapshots.DiffSnapshotRegistry()
    too_long = "x" * (snapshots.MAX_PATH_BYTES + 1)
    total_too_long = [f"{index}-" + "x" * 4090 for index in range(257)]

    results = [
        registry.create(".", "diff", [None]),
        registry.create(".", "diff", ["../bad"]),
        registry.create(".", "diff", [too_long]),
        registry.create(".", "diff", total_too_long),
    ]

    assert results == [
        {"success": False, "error_code": "DIFF_SNAPSHOT_INVALID_PATH"},
        {"success": False, "error_code": "DIFF_SNAPSHOT_INVALID_PATH"},
        {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"},
        {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"},
    ]


def test_bind_rejects_invalid_scope_storage_inputs() -> None:
    registry = snapshots.DiffSnapshotRegistry()
    too_many = ["x"] * (snapshots.MAX_SCOPE_PATHS + 1)
    too_long = "x" * (snapshots.MAX_PATH_BYTES + 1)
    total_too_long = [f"{index}-" + "x" * 4090 for index in range(257)]

    results = [
        registry.bind_assessed_scope(None, too_many),
        registry.bind_assessed_scope(None, [None]),
        registry.bind_assessed_scope(None, [too_long]),
        registry.bind_assessed_scope(None, total_too_long),
    ]

    assert results == [
        "DIFF_SNAPSHOT_CAPACITY",
        "DIFF_SNAPSHOT_INVALID_PATH",
        "DIFF_SNAPSHOT_CAPACITY",
        "DIFF_SNAPSHOT_CAPACITY",
    ]


def test_bind_rejects_lease_closed_while_pinned(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    registry.close_lease(
        str(created["diff_snapshot_id"]), str(created["route_lease_id"])
    )

    result = registry.bind_assessed_scope(consumer, ["old.py"])

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()
