"""Contract tests for the RFC-0022 P0.2 in-memory frozen registry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_registry as snapshots


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "old.py").write_text("value = 1\n")
    (tmp_path / "gone.py").write_text("gone = True\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


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


def test_workspace_mutation_after_capture_returns_stable_source_error(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])
    (root / "old.py").write_text("value = 99\n")

    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))

    assert consumer is None
    assert error == "DIFF_SNAPSHOT_SOURCE_CHANGED"


def test_workspace_symlink_freezes_link_text_without_following(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outside = tmp_path.parent / "outside-secret"
    outside.write_bytes(b"TOP-SECRET")
    (root / "link.py").symlink_to(outside)
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("link.py")
    assert frozen is not None
    assert frozen.new_bytes == bytes(outside)
    assert frozen.new_bytes != b"TOP-SECRET"
    consumer.release()


def test_workspace_fifo_is_rejected_without_opening(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    fifo = root / "pipe.py"
    fifo.touch()
    _git(root, "add", "pipe.py")
    _git(root, "commit", "-m", "pipe base")
    fifo.unlink()
    fifo.parent.joinpath("pipe.py")
    import os

    os.mkfifo(fifo)
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "diff", [])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_SPECIAL_FILE"}


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


def test_invalid_assessed_scope_is_stable_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "diff", ["../outside.py"])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_INVALID_PATH"}
    assert registry.stats() == (0, 0)


def test_non_repository_capture_fails_closed(tmp_path: Path) -> None:
    result = snapshots.DiffSnapshotRegistry().create(str(tmp_path), "diff", [])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_GIT_ERROR"}


def test_expiry_boundary_is_exact_with_open_lease(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    now = [20.0]
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    result = registry.create(str(root), "diff", [])
    now[0] += snapshots.HARD_LIFETIME_SECONDS - 0.001

    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    consumer.release()
    now[0] += 0.001
    expired, expired_error = registry.acquire(
        str(result["diff_snapshot_id"]), str(root)
    )
    assert expired is None
    assert expired_error == "DIFF_SNAPSHOT_EXPIRED"


def test_reset_rejects_active_consumer_then_clears(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    import pytest

    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_CONSUMERS_ACTIVE"):
        registry.reset()
    consumer.release()
    registry.reset()
    assert registry.stats() == (0, 0)


def test_snapshot_consumers_use_frozen_utf8_bytes(tmp_path: Path) -> None:
    import asyncio

    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )

    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    result = snapshots.REGISTRY.create(str(root), "diff", [])
    request = {
        "diff_snapshot_id": result["diff_snapshot_id"],
        "file_path": "old.py",
        "output_format": "json",
    }

    ast_result = asyncio.run(ASTDiffTool(str(root)).execute(request))
    semantic_result = asyncio.run(SemanticClassifyTool(str(root)).execute(request))

    assert ast_result["success"] is True
    assert len(ast_result["hunks"]) == 2
    assert semantic_result["success"] is True
    assert semantic_result["change_count"] == 2
    assert (
        snapshots.REGISTRY.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )


def test_snapshot_consumers_reject_binary_content_stably(tmp_path: Path) -> None:
    import asyncio

    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )

    root = _repo(tmp_path)
    (root / "blob.py").write_bytes(b"a\0b")
    result = snapshots.REGISTRY.create(str(root), "diff", [])
    request = {
        "diff_snapshot_id": result["diff_snapshot_id"],
        "file_path": "blob.py",
        "output_format": "json",
    }

    ast_result = asyncio.run(ASTDiffTool(str(root)).execute(request))
    semantic_result = asyncio.run(SemanticClassifyTool(str(root)).execute(request))

    assert ast_result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"
    assert semantic_result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"
    assert (
        snapshots.REGISTRY.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )


def test_snapshot_consumer_schema_rejects_live_arguments(tmp_path: Path) -> None:
    import pytest

    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )

    arguments = {"diff_snapshot_id": "ds_x", "file_path": "old.py", "old_ref": "HEAD"}

    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        ASTDiffTool(str(tmp_path)).validate_arguments(arguments)
    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        SemanticClassifyTool(str(tmp_path)).validate_arguments(arguments)


def test_edit_impact_is_strict_and_does_not_write(tmp_path: Path) -> None:
    import asyncio

    import pytest

    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    before = {path.relative_to(root) for path in root.rglob("*")}
    facade = build_edit_facade(str(root))

    result = asyncio.run(
        facade.execute({"action": "impact", "mode": "diff", "output_format": "json"})
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
    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_REQUIRED"):
        asyncio.run(
            facade.execute({"action": "impact", "capture_diff_snapshot": False})
        )


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


def test_capture_detects_aba_even_when_bytes_are_restored(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    target = root / "old.py"
    target.write_text("value = 2\n")
    original = snapshots._capture_payload

    def transient(*args, **kwargs):
        payload = original(*args, **kwargs)
        target.write_text("transient = True\n")
        target.write_text("value = 2\n")
        return payload

    monkeypatch.setattr(snapshots, "_capture_payload", transient)

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED"}


def test_consumer_missing_and_expired_ids_are_stable(tmp_path: Path) -> None:
    import asyncio

    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )

    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    result = snapshots.REGISTRY.create(str(root), "diff", [])
    missing = {
        "diff_snapshot_id": result["diff_snapshot_id"],
        "file_path": "absent.py",
        "output_format": "json",
    }

    ast_missing = asyncio.run(ASTDiffTool(str(root)).execute(missing))
    semantic_missing = asyncio.run(SemanticClassifyTool(str(root)).execute(missing))
    assert ast_missing["error_code"] == "DIFF_SNAPSHOT_FILE_NOT_FOUND"
    assert semantic_missing["error_code"] == "DIFF_SNAPSHOT_FILE_NOT_FOUND"
    assert (
        snapshots.REGISTRY.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )

    expired = {
        "diff_snapshot_id": result["diff_snapshot_id"],
        "file_path": "old.py",
        "output_format": "json",
    }
    ast_expired = asyncio.run(ASTDiffTool(str(root)).execute(expired))
    semantic_expired = asyncio.run(SemanticClassifyTool(str(root)).execute(expired))
    assert ast_expired["error_code"] == "DIFF_SNAPSHOT_EXPIRED"
    assert semantic_expired["error_code"] == "DIFF_SNAPSHOT_EXPIRED"


def test_consumer_lifecycle_is_idempotent_context_managed_and_thread_owned(
    tmp_path: Path,
) -> None:
    import concurrent.futures

    import pytest

    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])
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


def test_oracle_rejects_invalid_roots_and_nul_paths(tmp_path: Path) -> None:
    import pytest

    from tree_sitter_analyzer.source_oracle import (
        SourceOracleError,
        canonical_root,
        normalize_repo_path,
    )

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_ROOT_INVALID"):
        canonical_root(str(tmp_path / "missing"))
    regular = tmp_path / "regular"
    regular.write_text("not a directory")
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_ROOT_INVALID"):
        canonical_root(str(regular))
    assert normalize_repo_path("././folder/file.py") == "folder/file.py"
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_INVALID_PATH"):
        normalize_repo_path("bad\0path")
