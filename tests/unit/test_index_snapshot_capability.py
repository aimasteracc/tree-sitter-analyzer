"""Registry and capacity tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_snapshot = requires_posix_fd


class TestIndexSnapshotRegistry:
    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @staticmethod
    def _snapshot(root):
        from tree_sitter_analyzer.index_snapshot import IndexSnapshot

        return IndexSnapshot(
            None,
            "source",
            "index",
            "generation",
            "complete",
            None,
            str(root.resolve()),
            0,
        )

    def test_registry_capacity_rejects_oversized_snapshot(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(owner, "_MAX_CHARGED_BYTES", 1)
        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_CAPACITY"):
            owner.REGISTRY.ensure_capacity(2)

    def test_registry_rejects_root_mismatch(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(self._snapshot(tmp_path), conn, 0)
        duplicate = sqlite3.connect(":memory:")
        reused = owner.REGISTRY.publish(self._snapshot(tmp_path), duplicate, 0)
        assert reused.snapshot_id == published.snapshot_id
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            duplicate.execute("SELECT 1")
        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_ROOT_MISMATCH"):
            with owner.acquire_index_snapshot(
                published.snapshot_id, str(tmp_path / "other")
            ):
                pass

    def test_registry_rejects_generation_mismatch(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(self._snapshot(tmp_path), conn, 0)
        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            with owner.acquire_index_snapshot(
                published.snapshot_id, str(tmp_path), "forged"
            ):
                pass

    def test_registry_purges_expired_unacquired_snapshot(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(self._snapshot(tmp_path), conn, 0)
        monkeypatch.setattr(owner, "_clock", lambda: 1000.0)
        entry = owner.REGISTRY._entries[published.snapshot_id]
        entry.readers = 1
        monkeypatch.setattr(owner, "_MAX_SNAPSHOTS", 1)
        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_CAPACITY"):
            owner.REGISTRY.ensure_capacity(0)
        entry.readers = 0
        owner.REGISTRY.ensure_capacity(0)
        assert published.snapshot_id not in owner.REGISTRY._entries
        expiring = owner.REGISTRY.publish(
            self._snapshot(tmp_path), sqlite3.connect(":memory:"), 0
        )
        owner.REGISTRY._entries[expiring.snapshot_id].expires_at = 1.0
        owner.REGISTRY.ensure_capacity(0)
        assert expiring.snapshot_id not in owner.REGISTRY._entries


def test_strict_call_graph_marker_verifies_exact_rows():
    from tree_sitter_analyzer.cache.callgraph_state import (
        clear_call_graph_built_strict,
        mark_call_graph_built_strict,
    )

    conn = sqlite3.connect(":memory:")
    clear_call_graph_built_strict(conn)
    mark_call_graph_built_strict(conn)
    rows = conn.execute(
        "SELECT id, built FROM ast_call_graph_state ORDER BY id"
    ).fetchall()
    conn.close()

    assert rows == [(1, 1)]


def test_strict_call_graph_marker_raises_when_sentinel_survives():
    from tree_sitter_analyzer.cache.callgraph_state import (
        clear_call_graph_built_strict,
        mark_call_graph_built_strict,
    )

    conn = sqlite3.connect(":memory:")
    clear_call_graph_built_strict(conn)
    conn.execute(
        "CREATE TRIGGER keep_incomplete BEFORE DELETE ON ast_call_graph_state "
        "WHEN OLD.id = 2 BEGIN SELECT RAISE(IGNORE); END"
    )
    with pytest.raises(
        sqlite3.OperationalError, match="^CALL_GRAPH_MARKER_VERIFY_FAILED$"
    ):
        mark_call_graph_built_strict(conn)
    conn.rollback()
    rows = conn.execute(
        "SELECT id, built FROM ast_call_graph_state ORDER BY id"
    ).fetchall()
    conn.close()

    assert rows == [(1, 0), (2, 0)]


def test_exact_call_graph_marker_missing_table_is_false():
    from tree_sitter_analyzer.index_snapshot_capability import (
        exact_call_graph_marker,
    )

    conn = sqlite3.connect(":memory:")
    result = exact_call_graph_marker(conn)
    conn.close()

    assert result is False


@requires_posix_fd
def test_pinned_path_stat_failure_reports_mismatch(monkeypatch):
    import tree_sitter_analyzer.index_snapshot as owner

    monkeypatch.setattr(
        owner.os, "stat", lambda *_a, **_k: (_ for _ in ()).throw(OSError())
    )
    assert owner._path_matches_pinned_database(1, 2) is False


@requires_posix_fd
def test_missing_project_root_is_distinguished(tmp_path):
    import tree_sitter_analyzer.index_snapshot as owner

    with pytest.raises(FileNotFoundError, match="MISSING_PROJECT_ROOT"):
        owner._open_bound_database(str(tmp_path / "absent"))


@requires_posix_fd
def test_missing_index_database_closes_bound_directories(tmp_path):
    import tree_sitter_analyzer.index_snapshot as owner

    (tmp_path / ".ast-cache").mkdir()
    with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
        owner._open_bound_database(str(tmp_path))


@requires_posix_fd
def test_nonregular_index_database_is_rejected(tmp_path):
    import tree_sitter_analyzer.index_snapshot as owner

    (tmp_path / ".ast-cache" / "index.db").mkdir(parents=True)
    with pytest.raises(ValueError, match="INDEX_PATH_UNSAFE"):
        owner._open_bound_database(str(tmp_path))


@requires_posix_fd
def test_cache_open_error_closes_root_handle(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_snapshot as owner

    (tmp_path / ".ast-cache").mkdir()
    original_open = owner.os.open

    def fail_cache(path, flags, *args, **kwargs):
        if path == ".ast-cache":
            raise PermissionError("cache denied")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(owner.os, "open", fail_cache)
    with pytest.raises(PermissionError, match="cache denied"):
        owner._open_bound_database(str(tmp_path))


@requires_posix_fd
def test_database_open_error_closes_directory_handles(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_snapshot as owner

    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").touch()
    original_open = owner.os.open

    def fail_database(path, flags, *args, **kwargs):
        if path == "index.db":
            raise PermissionError("database denied")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(owner.os, "open", fail_database)
    with pytest.raises(PermissionError, match="database denied"):
        owner._open_bound_database(str(tmp_path))


@requires_posix_fd
def test_canonical_root_symlink_swap_is_rejected(tmp_path, monkeypatch):
    # PR #1253 review 3755386843: canonical root open must not follow a swap.
    import tree_sitter_analyzer.index_snapshot_capability as capability

    root = tmp_path / "root"
    outside = tmp_path / "outside"
    (root / ".ast-cache").mkdir(parents=True)
    outside.mkdir()
    (root / ".ast-cache" / "index.db").touch()
    original_open = capability.os.open
    swapped = False

    def swap_before_root_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == str(root.resolve()) and kwargs.get("dir_fd") is None and not swapped:
            swapped = True
            root.rename(tmp_path / "original-root")
            root.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(capability.os, "open", swap_before_root_open)
    with pytest.raises(ValueError, match="INDEX_PATH_SYMLINK"):
        capability.open_bound_database(str(root))
    assert swapped is True


@requires_posix_fd
def test_canonical_root_directory_swap_fails_identity_check(tmp_path, monkeypatch):
    # PR #1253 review 3755386843: an attacker-controlled directory is not anchored.
    import tree_sitter_analyzer.index_snapshot_capability as capability

    root = tmp_path / "root"
    (root / ".ast-cache").mkdir(parents=True)
    (root / ".ast-cache" / "index.db").touch()
    original_open = capability.os.open
    swapped = False

    def swap_before_root_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == str(root.resolve()) and kwargs.get("dir_fd") is None and not swapped:
            swapped = True
            root.rename(tmp_path / "original-root")
            root.mkdir()
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(capability.os, "open", swap_before_root_open)
    with pytest.raises(ValueError, match="INDEX_PATH_UNSAFE"):
        capability.open_bound_database(str(root))
    assert swapped is True


@requires_posix_fd
def test_empty_regular_sidecar_is_not_a_concurrent_writer(tmp_path):
    import tree_sitter_analyzer.index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    (cache / "index.db-wal").touch()
    fd = os.open(cache, os.O_RDONLY)
    try:
        owner._reject_sidecars(fd)
    finally:
        os.close(fd)
    assert (cache / "index.db-wal").stat().st_size == 0


@requires_posix_snapshot
def test_open_bound_database_reports_missing_file_after_cache_open(tmp_path):
    # PR #1253: the secure fd seam closes parent handles on an index-file race.
    from tree_sitter_analyzer.index_snapshot import _open_bound_database

    (tmp_path / ".ast-cache").mkdir()
    with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
        _open_bound_database(str(tmp_path))


@requires_posix_snapshot
def test_open_bound_database_reports_missing_cache_directory(tmp_path):
    # PR #1253: secure descriptor setup closes the root on a missing cache.
    from tree_sitter_analyzer.index_snapshot import _open_bound_database

    with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
        _open_bound_database(str(tmp_path))


@requires_posix_fd
def test_bound_database_disappearing_is_missing(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    (cache / "index.db").touch()
    monkeypatch.setattr(
        owner,
        "_open_bound_database",
        lambda *_args: (_ for _ in ()).throw(FileNotFoundError("MISSING_INDEX")),
    )
    result = owner.read_existing_snapshot(str(tmp_path))
    assert result.reason == "MISSING_INDEX"


@requires_posix_fd
def test_canonical_root_disappearance_is_missing_project(tmp_path, monkeypatch):
    # PR #1253: a root removed after admission remains a missing-root outcome.
    import tree_sitter_analyzer.index_snapshot_capability as capability

    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(
        capability,
        "_open_pinned_path",
        lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    with pytest.raises(FileNotFoundError, match="MISSING_PROJECT_ROOT"):
        capability.open_bound_database(str(root))


@requires_posix_fd
def test_snapshot_maps_nofollow_open_error_to_symlink_reason(tmp_path, monkeypatch):
    # PR #1253: platform ELOOP is normalized without leaking OS-specific text.
    import errno

    import tree_sitter_analyzer.index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    (cache / "index.db").touch()
    monkeypatch.setattr(
        owner,
        "_open_bound_database",
        lambda *_a: (_ for _ in ()).throw(OSError(errno.ELOOP, "loop")),
    )
    result = owner.read_existing_snapshot(str(tmp_path))
    assert result.reason == "INDEX_PATH_SYMLINK"


@requires_posix_fd
def test_pinned_component_fstat_failure_closes_descriptor(tmp_path, monkeypatch):
    # PR #1253: descriptor validation failures cannot leak capabilities.
    import tree_sitter_analyzer.index_snapshot_capability as capability

    path = tmp_path / "root"
    path.mkdir()
    opened: list[int] = []
    original_open = capability.os.open
    original_fstat = capability.os.fstat

    def recording_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def failing_fstat(fd):
        if fd in opened:
            raise OSError("fstat failed")
        return original_fstat(fd)

    with monkeypatch.context() as patcher:
        patcher.setattr(capability.os, "open", recording_open)
        patcher.setattr(capability.os, "fstat", failing_fstat)
        with pytest.raises(OSError, match="fstat failed"):
            capability._open_pinned_path(
                str(path), os.O_RDONLY | os.O_DIRECTORY, directory=True
            )
    with pytest.raises(OSError):
        os.fstat(opened[0])
