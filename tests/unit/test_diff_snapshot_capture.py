from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import make_repo


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


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
    monkeypatch.setattr(snapshots, "capture_inventory", lambda *a, **k: ())
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


def test_git_epoch_selects_object_format_empty_tree() -> None:
    from tree_sitter_analyzer.source_oracle_git import GitEpoch

    sha1 = GitEpoch(b"head", "sha1", (), (), (), ()).empty_tree
    sha256 = GitEpoch(b"head", "sha256", (), (), (), ()).empty_tree
    assert len(sha1) == 40
    assert len(sha256) == 64


def _epoch(**overrides):
    from tree_sitter_analyzer.source_oracle_git import GitEpoch

    values = {
        "head": b"a" * 40,
        "object_format": "sha1",
        "index_entries": (),
        "tracked_paths": (),
        "dirty_paths": (),
        "untracked_paths": (),
    }
    values.update(overrides)
    return GitEpoch(**values)


def test_wire_codec_round_trips_non_utf8_path() -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire, path_to_wire

    path = os.fsdecode(b"bad-\xff.py")
    token = path_to_wire(path)

    assert (token.startswith("git-path-b64:"), path_from_wire(token)) == (True, path)


def test_wire_codec_escapes_reserved_literal_prefix() -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire, path_to_wire

    path = "git-path-b64:literal"
    token = path_to_wire(path)

    assert (token == path, path_from_wire(token)) == (False, path)


@pytest.mark.parametrize(
    "value", [None, "git-path-b64:", "git-path-b64:!", "git-path-b64:YQ"]
)
def test_wire_codec_rejects_invalid_tokens(value) -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_INVALID_PATH"):
        path_from_wire(value)


def test_epoch_inventory_enforces_wire_storage_limit() -> None:
    from tree_sitter_analyzer.diff_snapshot_paths import epoch_inventory

    epoch = _epoch(tracked_paths=(b"long.py",))

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_CAPACITY"):
        epoch_inventory(epoch, "staged", 1)


def test_frozen_environment_rejects_non_stage_zero_entry(tmp_path: Path) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment

    epoch = _epoch(index_entries=((b"a.py", b"100644 " + b"a" * 40 + b" 1"),))
    frozen = FrozenGitEnvironment(str(tmp_path), epoch, time.monotonic() + 1)

    def run(args, **kwargs):
        if args == ["read-tree", "--empty"]:
            Path(frozen.index_path).write_bytes(b"index")
        return b"oid"

    frozen.run = run  # type: ignore[method-assign]

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        frozen.__enter__()
    assert frozen._directory is None


def test_frozen_workspace_requires_entered_environment(tmp_path: Path) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment

    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 1)

    with pytest.raises(
        snapshots.SourceOracleError, match="DIFF_SNAPSHOT_CAPTURE_ERROR"
    ):
        frozen.apply_workspace({})


def test_frozen_workspace_rejects_unbound_directory(tmp_path: Path) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment
    from tree_sitter_analyzer.source_oracle import SafePath

    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 1)
    frozen._directory = str(tmp_path)
    frozen.index_path = str(tmp_path / "index")
    Path(frozen.index_path).write_bytes(b"")

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_SPECIAL_FILE"):
        frozen.apply_workspace({b"vendor": SafePath(None, (), "directory")})


def test_frozen_workspace_rejects_empty_blob_oid(tmp_path: Path) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment
    from tree_sitter_analyzer.source_oracle import SafePath

    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 1)
    frozen._directory = str(tmp_path)
    frozen.index_path = str(tmp_path / "index")
    Path(frozen.index_path).write_bytes(b"")
    frozen.run = lambda *args, **kwargs: b""  # type: ignore[method-assign]

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        frozen.apply_workspace({b"a.py": SafePath(b"x", (b"1,2,33188,0,0,0",), "file")})


def test_frozen_workspace_rejects_invalid_file_metadata(tmp_path: Path) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment
    from tree_sitter_analyzer.source_oracle import SafePath

    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 1)
    frozen._directory = str(tmp_path)
    frozen.index_path = str(tmp_path / "index")
    Path(frozen.index_path).write_bytes(b"")
    frozen.run = lambda *args, **kwargs: b"a" * 40  # type: ignore[method-assign]

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_UNSAFE_PATH"):
        frozen.apply_workspace({b"a.py": SafePath(b"x", (b"bad",), "file")})


def _prepared_frozen(tmp_path: Path):
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment

    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 1)
    frozen._directory = str(tmp_path)
    frozen.index_path = str(tmp_path / "index")
    Path(frozen.index_path).write_bytes(b"")
    return frozen


def test_frozen_environment_exit_is_idempotent(tmp_path: Path) -> None:
    frozen = _prepared_frozen(tmp_path)
    frozen._directory = None

    assert frozen.__exit__() is None


def test_frozen_environment_without_object_directory_has_minimal_env(
    tmp_path: Path,
) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment

    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 1)

    assert "GIT_OBJECT_DIRECTORY" not in frozen._env()


def test_frozen_workspace_rejects_special_leaf(tmp_path: Path) -> None:
    from tree_sitter_analyzer.source_oracle import SafePath

    frozen = _prepared_frozen(tmp_path)

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_SPECIAL_FILE"):
        frozen.apply_workspace({b"node": SafePath(None, (), "special")})


def test_frozen_workspace_materializes_symlink_mode(tmp_path: Path) -> None:
    from tree_sitter_analyzer.source_oracle import SafePath

    frozen = _prepared_frozen(tmp_path)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return b"a" * 40

    frozen.run = run  # type: ignore[method-assign]
    result = frozen.apply_workspace(
        {b"link": SafePath(b"target", (b"1,2,41471,0,0,0",), "symlink")}
    )

    assert result[b"link"].startswith(b"120000 ")


def test_wire_codec_rejects_non_unicode_literal() -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_INVALID_PATH"):
        path_from_wire("bad-\udcff")


@pytest.mark.skipif(os.name == "nt", reason="tracked: RFC-0022 frozen Git POSIX test")
def test_frozen_environment_accepts_empty_index(tmp_path: Path) -> None:
    from tree_sitter_analyzer.diff_snapshot_epoch import FrozenGitEnvironment

    _repo(tmp_path)
    frozen = FrozenGitEnvironment(str(tmp_path), _epoch(), time.monotonic() + 2)

    with frozen:
        assert Path(frozen.index_path).is_file()
