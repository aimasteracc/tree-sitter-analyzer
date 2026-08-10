from __future__ import annotations

import os
import stat
import sys
import time
import types
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_epoch as epoch_module
import tree_sitter_analyzer.frozen_git_index as frozen_index
import tree_sitter_analyzer.git_subprocess as bounded
import tree_sitter_analyzer.source_oracle_git as oracle
from tree_sitter_analyzer.frozen_git_index import (
    parse_stage_zero_entries,
    private_index_file,
    safe_external_temp_parent,
)
from tree_sitter_analyzer.source_oracle import SourceOracleError


def test_parse_stage_zero_entries_returns_exact_headers() -> None:
    raw = b"100644 a 0\ta.py\0" + b"100755 b 0\tb.py\0"

    entries = parse_stage_zero_entries(raw, max_paths=2)

    assert entries == {b"a.py": b"100644 a 0", b"b.py": b"100755 b 0"}


def test_private_index_file_is_mode_600_and_removed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    observed_path = ""
    with private_index_file(str(project), b"exact") as path:
        observed_path = path
        assert Path(path).read_bytes() == b"exact"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    assert Path(observed_path).exists() is False


def test_private_index_file_rejects_project_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "private-index"

    def create_inside(*, prefix: str, dir: str) -> tuple[int, str]:
        del prefix, dir
        return os.open(target, os.O_CREAT | os.O_RDWR, 0o600), str(target)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"):
        with private_index_file(str(project), b"exact", mkstemp=create_inside):
            pass

    assert target.exists() is False


def _error(call, code: str) -> None:
    with pytest.raises(SourceOracleError, match=f"^{code}$"):
        call()


@pytest.mark.parametrize(
    "raw",
    [
        b"malformed\0",
        b"100644 a 0\t\0",
        b"100644 a\tpath\0",
        b"100644 a 1\tpath\0",
        b"invalid a 0\tpath\0",
        b"100644 invalid-hash 0\tpath\0",
        b"100644 a 0\tpath\x00100644 b 0\tpath\0",
    ],
)
def test_index_entries_rejects_hostile_inventory(monkeypatch, raw: bytes) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: raw)

    _error(
        lambda: oracle._index_entries(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_index_entries_uses_private_mode_600_exact_bytes(monkeypatch) -> None:
    observed: list[tuple[bytes, int, str]] = []

    def run(root, args, *, env, **kwargs):
        path = env["GIT_INDEX_FILE"]
        observed.append(
            (Path(path).read_bytes(), stat.S_IMODE(os.stat(path).st_mode), path)
        )
        return b"100644 a 0\tpath\0"

    monkeypatch.setattr(oracle, "run_git_bounded", run)

    entries = oracle._index_entries(
        ".", deadline=time.monotonic() + 1, index_bytes=b"exact-index"
    )

    assert entries == {b"path": b"100644 a 0"}
    assert observed[0][:2] == (b"exact-index", 0o600)
    assert Path(observed[0][2]).exists() is False


def test_index_entries_rejects_private_index_inside_project(
    tmp_path: Path, monkeypatch
) -> None:
    index_path = tmp_path / "private-index"

    def mkstemp(*, prefix, dir):
        del prefix, dir
        descriptor = os.open(index_path, os.O_CREAT | os.O_RDWR, 0o600)
        return descriptor, str(index_path)

    monkeypatch.setattr(oracle.tempfile, "mkstemp", mkstemp)

    _error(
        lambda: oracle._index_entries(
            str(tmp_path), deadline=time.monotonic() + 1, index_bytes=b"index"
        ),
        "DIFF_SNAPSHOT_UNSAFE_TEMP",
    )
    assert index_path.exists() is False


def test_index_entries_cleanup_tolerates_already_removed_temp(monkeypatch) -> None:
    real_unlink = os.unlink
    removed: list[str] = []

    def remove_then_report_missing(path):
        real_unlink(path)
        removed.append(path)
        raise FileNotFoundError

    monkeypatch.setattr(oracle, "run_git_bounded", lambda *a, **k: b"")
    monkeypatch.setattr(oracle.os, "unlink", remove_then_report_missing)

    entries = oracle._index_entries(
        ".", deadline=time.monotonic() + 1, index_bytes=b"index"
    )

    assert entries == {}
    assert len(removed) == 1


def test_index_entries_rejects_bounded_path_count(monkeypatch) -> None:
    raw = b"100644 a 0\ta\x00100644 b 0\tb\0"
    monkeypatch.setattr(oracle, "_MAX_WORKTREE_PATHS", 1)
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: raw)

    _error(
        lambda: oracle._index_entries(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def test_private_index_treats_cross_volume_commonpath_as_outside(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        os.path, "commonpath", lambda paths: (_ for _ in ()).throw(ValueError)
    )

    with private_index_file(str(tmp_path), b"index") as path:
        assert Path(path).read_bytes() == b"index"


def test_reconstructed_index_rejects_nonzero_stage(tmp_path: Path, monkeypatch) -> None:
    from tree_sitter_analyzer.frozen_git_index import reconstructed_index_file

    monkeypatch.setattr(
        "tree_sitter_analyzer.frozen_git_index.run_git_bounded",
        lambda *args, **kwargs: b"",
    )

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        with reconstructed_index_file(
            str(tmp_path), {b"a": b"100644 a 1"}, deadline=1e20
        ):
            pass


def test_reconstructed_index_cleanup_accepts_removed_file(
    tmp_path: Path, monkeypatch
) -> None:
    from tree_sitter_analyzer.frozen_git_index import reconstructed_index_file

    def create_index(*args, **kwargs):
        Path(kwargs["env"]["GIT_INDEX_FILE"]).touch()
        return b""

    monkeypatch.setattr(
        "tree_sitter_analyzer.frozen_git_index.run_git_bounded", create_index
    )

    with reconstructed_index_file(str(tmp_path), {}, deadline=1e20) as path:
        os.unlink(path)

    assert Path(path).exists() is False


def test_core_filemode_parses_false(monkeypatch) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: b"false\n")

    assert oracle._core_filemode(".", deadline=1e20) is False


def test_core_filemode_rejects_invalid_boolean(monkeypatch) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: b"invalid\n")

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        oracle._core_filemode(".", deadline=1e20)


def test_temp_parent_skips_project_tmpdir(tmp_path: Path, monkeypatch) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-y.
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("TMPDIR", str(project))
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    selected = safe_external_temp_parent(str(project))

    assert selected in (os.path.realpath("/var/tmp"), os.path.realpath("/tmp"))


def test_no_safe_temp_parent_rejects_before_mkstemp(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-y.
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("TMPDIR", str(project))
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)
    real_isdir = frozen_index.os.path.isdir
    monkeypatch.setattr(
        frozen_index.os.path,
        "isdir",
        lambda path: (
            False
            if path in (os.path.realpath("/var/tmp"), os.path.realpath("/tmp"))
            else real_isdir(path)
        ),
    )
    calls: list[str] = []

    def forbidden_mkstemp(**kwargs):
        calls.append(str(kwargs))
        raise AssertionError("mkstemp must not be called")

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"):
        with private_index_file(str(project), b"index", mkstemp=forbidden_mkstemp):
            pass

    assert calls == []


def test_temp_parent_deduplicates_candidates(tmp_path: Path, monkeypatch) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-y.
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("TMPDIR", str(project))
    monkeypatch.setenv("TEMP", str(project))
    monkeypatch.delenv("TMP", raising=False)

    selected = safe_external_temp_parent(str(project))

    assert selected == os.path.realpath("/var/tmp")


def test_temp_parent_has_fixed_windows_fallback(tmp_path: Path, monkeypatch) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-y.
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setattr(frozen_index.os, "name", "nt")
    monkeypatch.setattr(frozen_index.tempfile, "gettempdir", lambda: "/var/tmp")

    selected = safe_external_temp_parent(str(project))

    assert selected == os.path.realpath("/var/tmp")


@pytest.mark.parametrize("oid", [b"not-hex", b"a" * 39])
def test_git_filtered_oid_rejects_invalid_git_output(monkeypatch, oid: bytes) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-s.
    monkeypatch.setattr(frozen_index, "run_git_bounded", lambda *args, **kwargs: oid)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        frozen_index.git_filtered_oid(
            ".", b"sample.txt", b"data", deadline=time.monotonic() + 1
        )


def test_reconstructed_index_writes_valid_stage_zero_payload(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[tuple[list[str], bytes | None]] = []

    def record(*args, **kwargs):
        Path(kwargs["env"]["GIT_INDEX_FILE"]).touch()
        calls.append((args[1], kwargs.get("input_")))
        return b""

    monkeypatch.setattr(frozen_index, "run_git_bounded", record)
    entry = b"100644 " + b"a" * 40 + b" 0"

    with frozen_index.reconstructed_index_file(
        str(tmp_path), {b"a.py": entry}, deadline=1e20
    ):
        pass

    assert calls[1] == (
        ["update-index", "-z", "--index-info"],
        b"100644 " + b"a" * 40 + b"\ta.py\0",
    )


@pytest.mark.parametrize("prefix", [b"\0", b"\x80\0"])
def test_invalidate_index_stat_cache_supports_v4_prefix_encoding(prefix: bytes) -> None:
    fixed = b"\1" * 40 + b"\2" * 20 + b"\0\0"
    raw = b"DIRC" + (4).to_bytes(4, "big") + (1).to_bytes(4, "big")
    raw += fixed + prefix + b"a.py\0" + b"\0" * 20

    result = frozen_index.invalidate_index_stat_cache(raw, object_format="sha1")

    assert result[12:36] == b"\0" * 24
    assert result[40:52] == b"\0" * 12


def test_invalidate_index_stat_cache_rejects_truncated_entry() -> None:
    raw = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\0" * 20

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        frozen_index.invalidate_index_stat_cache(raw, object_format="sha1")


def test_invalidate_index_stat_cache_rejects_missing_path_terminator() -> None:
    fixed = b"\0" * 40 + b"a" * 20 + b"\0\0"
    raw = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    raw += fixed + b"a.py" + b"\1" * 20

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        frozen_index.invalidate_index_stat_cache(raw, object_format="sha1")


def _index_bytes(version: int = 2, flags: int = 0, suffix: bytes = b"") -> bytes:
    fixed = b"\0" * 60 + flags.to_bytes(2, "big")
    if version == 4:
        entry = fixed + b"\0a.py\0"
    else:
        entry = fixed + b"a.py\0"
        entry += b"\0" * ((-len(entry)) % 8)
    return (
        b"DIRC"
        + version.to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + entry
        + suffix
        + b"\0" * 20
    )


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"bad", "DIFF_SNAPSHOT_GIT_ERROR"),
        (_index_bytes(version=1), "DIFF_SNAPSHOT_UNSUPPORTED_INDEX"),
        (
            b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\0" * 20,
            "DIFF_SNAPSHOT_GIT_ERROR",
        ),
        (_index_bytes(flags=0x4000), "DIFF_SNAPSHOT_GIT_ERROR"),
    ],
)
def test_has_split_index_rejects_malformed_index(raw: bytes, code: str) -> None:
    # PR #1252 patch-coverage gate: malformed frozen indices fail closed.
    with pytest.raises(SourceOracleError, match=f"^{code}$"):
        frozen_index.has_split_index(raw, object_format="sha1")


@pytest.mark.parametrize("version", [2, 4])
def test_has_split_index_accepts_plain_index_versions(version: int) -> None:
    assert (
        frozen_index.has_split_index(_index_bytes(version), object_format="sha1")
        is False
    )


def test_has_split_index_detects_link_extension() -> None:
    extension = b"link" + (1).to_bytes(4, "big") + b"x"
    assert (
        frozen_index.has_split_index(
            _index_bytes(suffix=extension), object_format="sha1"
        )
        is True
    )


@pytest.mark.parametrize(
    "suffix",
    [b"x", b"ABCD" + (2).to_bytes(4, "big") + b"x"],
)
def test_has_split_index_rejects_malformed_extension(suffix: bytes) -> None:
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        frozen_index.has_split_index(_index_bytes(suffix=suffix), object_format="sha1")


def test_frozen_epoch_without_settings_needs_no_verification(tmp_path: Path) -> None:
    epoch = oracle.GitEpoch(b"head", "sha1", (), (), (), ())
    environment = epoch_module.FrozenGitEnvironment(str(tmp_path), epoch, 1e20)

    environment.verify_source_epoch()


def test_object_store_symlink_is_rejected(tmp_path: Path) -> None:
    objects = tmp_path / "objects"
    objects.mkdir()
    (objects / "link").symlink_to(tmp_path)
    epoch = oracle.GitEpoch(b"head", "sha1", (), (), (), ())
    environment = epoch_module.FrozenGitEnvironment(str(tmp_path), epoch, 1e20)
    environment.object_directory = str(objects)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"):
        environment._refresh_object_usage()


def test_object_store_lstat_error_is_stable(tmp_path: Path, monkeypatch) -> None:
    objects = tmp_path / "objects"
    objects.mkdir()
    (objects / "entry").touch()
    epoch = oracle.GitEpoch(b"head", "sha1", (), (), (), ())
    environment = epoch_module.FrozenGitEnvironment(str(tmp_path), epoch, 1e20)
    environment.object_directory = str(objects)
    monkeypatch.setattr(
        epoch_module, "_lstat", lambda path: (_ for _ in ()).throw(OSError())
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        environment._refresh_object_usage()


@pytest.mark.parametrize(("hard", "expected"), [(100, 50), (-1, 50)])
def test_exec_guard_sets_bounded_rlimit(monkeypatch, hard: int, expected: int) -> None:
    # PR #1252 review thread 4867: only the single-threaded guard sets RLIMIT.
    from tree_sitter_analyzer import git_exec_guard

    calls: list[tuple[int, tuple[int, int]]] = []
    resource = types.SimpleNamespace(
        RLIMIT_FSIZE=1,
        RLIM_INFINITY=-1,
        getrlimit=lambda kind: (75, hard),
        setrlimit=lambda kind, value: calls.append((kind, value)),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)
    monkeypatch.setattr(
        git_exec_guard.os, "execvp", lambda *args: (_ for _ in ()).throw(OSError())
    )

    result = git_exec_guard.main(["--fsize", "50", "--", "git", "status"])

    assert result == 126
    assert calls == [(1, (expected, hard))]


def test_negative_file_size_limit_is_rejected() -> None:
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        bounded.run_git_bounded(".", [], deadline=1e20, limit=1, file_size_limit=-1)


def test_has_split_index_rejects_truncated_v4_prefix() -> None:
    fixed = b"\0" * 60 + b"\0\0"
    raw = (
        b"DIRC"
        + (4).to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + fixed
        + b"\x80"
        + b"\1" * 20
    )
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        frozen_index.has_split_index(raw, object_format="sha1")


def test_has_split_index_accepts_multibyte_v4_prefix() -> None:
    fixed = b"\0" * 60 + b"\0\0"
    raw = b"DIRC" + (4).to_bytes(4, "big") + (1).to_bytes(4, "big")
    raw += fixed + b"\x80\0a.py\0" + b"\0" * 20

    assert frozen_index.has_split_index(raw, object_format="sha1") is False
