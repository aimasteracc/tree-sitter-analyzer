from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer import diff_snapshot_epoch as epoch_module
from tree_sitter_analyzer import frozen_git_settings as settings
from tree_sitter_analyzer import private_temp_materialization as materialization
from tree_sitter_analyzer.source_epoch import (
    GitEpoch,
    SourceEpoch,
)
from tree_sitter_analyzer.source_oracle import SourceOracleError


def _setting_file(path: bytes, kind: str = "missing", data: bytes | None = None):
    return settings.FrozenSettingFile(path, kind, data)


def _frozen_settings(**changes):
    values = {
        "config_entries": (
            settings.ConfigEntry(b"core.repositoryformatversion", b"0"),
            settings.ConfigEntry(b"core.bare", b"false"),
        ),
        "core_attributes_path": None,
        "core_attributes": None,
        "info_attributes": _setting_file(b"info/attributes"),
        "worktree_attributes": (),
        "object_directory": b"/objects",
        "fingerprint": b"fingerprint",
    }
    values.update(changes)
    return settings.FrozenGitSettings(**values)


def _epoch(git_settings=None, source_epoch=None, tracked_paths=()):
    return GitEpoch(
        b"head",
        "sha1",
        (),
        tracked_paths,
        (),
        (),
        index_bytes=b"index",
        source_epoch=source_epoch,
        git_settings=git_settings,
        settings_inventory=tracked_paths,
    )


def test_effective_config_parser_preserves_order_and_drops_directives() -> None:
    raw = (
        b"file:a\0x.multi\none\0"
        b"file:b\0include.path\nsecret\0"
        b"file:a\0x.flag\0"
        b"file:a\0x.multi\ntwo\0"
        b"file:a\0diff.orderFile\n/tmp/external-order\0"
        b"command line:\0core.fsmonitor\nfalse\0"
        b"file:b\0includeif.gitdir:repo.path\nother\0"
    )

    assert settings.parse_effective_config(raw) == (
        settings.ConfigEntry(b"x.multi", b"one"),
        settings.ConfigEntry(b"x.flag", None),
        settings.ConfigEntry(b"x.multi", b"two"),
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"origin\0key\0extra",
        b"\0key\0",
        b"origin\0\nvalue\0",
    ],
)
def test_effective_config_parser_rejects_malformed_records(raw: bytes) -> None:
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        settings.parse_effective_config(raw)


def test_git_config_serializer_round_trips_hostile_values(tmp_path: Path) -> None:
    entries = (
        settings.ConfigEntry(b"x.sub.dot.value", b'line\nnext\tquote"slash\\'),
        settings.ConfigEntry(b"x.flag", None),
        settings.ConfigEntry(b"core.attributesfile", b"live-secret-path"),
    )
    serialized, materialized = settings.serialize_config(entries, b"/frozen/attrs")
    config = tmp_path / "config"
    config.write_bytes(serialized)
    raw = subprocess.run(
        ["git", "config", "-z", "--file", str(config), "--list", "--show-origin"],
        check=True,
        capture_output=True,
    ).stdout

    assert settings.parse_effective_config(raw) == materialized
    assert b"live-secret-path" not in serialized
    assert materialized[-1].value == b"/frozen/attrs"


def test_git_config_serializer_drops_diff_order_file() -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X3LAP.
    serialized, materialized = settings.serialize_config(
        (settings.ConfigEntry(b"diff.orderFile", b"/external/order"),), None
    )

    assert (serialized, materialized) == (b"", ())


@pytest.mark.parametrize("key", [b"missingdot", b"bad_name.value", b"x.bad_name"])
def test_git_config_serializer_rejects_unsafe_keys(key: bytes) -> None:
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        settings.serialize_config((settings.ConfigEntry(key, b"value"),), None)


def test_settings_fingerprint_frames_core_and_worktree_files() -> None:
    first = settings.settings_fingerprint(
        (),
        b"/core",
        _setting_file(b"/core", "file", b"a"),
        _setting_file(b"/info", "file", b"b"),
        (_setting_file(b".gitattributes", "file", b"c"),),
        b"/objects",
    )
    second = settings.settings_fingerprint(
        (),
        b"/core",
        _setting_file(b"/core", "file", b"changed"),
        _setting_file(b"/info", "file", b"b"),
        (_setting_file(b".gitattributes", "file", b"c"),),
        b"/objects",
    )

    assert first != second


def test_settings_line_parser_strips_crlf_once() -> None:
    assert settings._strip_line(b"path\r\n") == b"path"


def test_shadow_materializes_exact_attribute_sources(tmp_path: Path) -> None:
    frozen = _frozen_settings(
        core_attributes_path=b"/live/core",
        core_attributes=_setting_file(b"/live/core", "file", b"*.py text\n"),
        info_attributes=_setting_file(b"/live/info", "file", b"*.bin binary\n"),
        worktree_attributes=(
            _setting_file(b"nested/.gitattributes", "file", b"*.txt -text\n"),
            _setting_file(b"nested/child/.gitattributes", "file", b"*.md text\n"),
            _setting_file(b"nested/missing/.gitattributes"),
            _setting_file(b"nested/link/.gitattributes", "symlink", b"target"),
        ),
        object_directory=os.fsencode(tmp_path / ".git" / "objects"),
    )
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(frozen), time.monotonic() + 5
    )

    with environment:
        git_dir = Path(environment.git_dir)
        worktree = Path(environment.worktree_path)
        assert (git_dir / "frozen-core-attributes").read_bytes() == b"*.py text\n"
        assert (git_dir / "info" / "attributes").read_bytes() == b"*.bin binary\n"
        assert (worktree / "nested" / ".gitattributes").read_bytes() == b"*.txt -text\n"
        assert (worktree / "nested" / "missing" / ".gitattributes").exists() is False
        assert (worktree / "nested" / "link" / ".gitattributes").exists() is False


def test_shadow_rejects_special_worktree_attribute(tmp_path: Path) -> None:
    frozen = _frozen_settings(
        worktree_attributes=(_setting_file(b".gitattributes", "directory"),)
    )
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(frozen), time.monotonic() + 5
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_SPECIAL_FILE$"):
        environment.__enter__()


def test_shadow_temporary_accounting_enforces_file_limit(tmp_path: Path) -> None:
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5, storage_file_limit=0
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        environment._account_temporary(0, 1)


def test_shadow_parent_rejects_escape(tmp_path: Path) -> None:
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )
    environment.worktree_path = str(tmp_path / "worktree")

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"):
        environment._ensure_worktree_parent(str(tmp_path / "escape" / "file"))


def test_shadow_parent_wraps_mkdir_failure(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )
    environment.worktree_path = str(worktree)
    monkeypatch.setattr(
        epoch_module.os, "mkdir", lambda *_a, **_k: (_ for _ in ()).throw(OSError())
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        environment._ensure_worktree_parent(str(worktree / "nested" / "file"))


def test_shadow_private_write_wraps_existing_destination(tmp_path: Path) -> None:
    target = tmp_path / "exists"
    target.write_bytes(b"existing")
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        environment._write_private(str(target), b"replacement")


@pytest.mark.parametrize("name", ["config", "index"])
def test_shadow_capacity_rejects_megabyte_private_file_before_open(
    tmp_path: Path, monkeypatch, name: str
) -> None:
    # PR #1252 review comment 3749572169: capacity is a pre-write invariant.
    data = b"x" * (1024 * 1024)
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5, storage_byte_limit=len(data) - 1
    )
    calls: list[str] = []

    def forbidden_open(*args, **kwargs):
        calls.append(str(args[0]))
        raise AssertionError("capacity failure must not open a destination")

    monkeypatch.setattr(materialization, "open", forbidden_open, raising=False)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        environment._write_private(str(tmp_path / name), data)

    assert calls == []


@pytest.mark.parametrize("failure", ["chmod", "write", "fsync"])
def test_shadow_private_write_failure_rolls_back_and_cleans(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    target = tmp_path / "private"
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )
    if failure == "chmod":
        monkeypatch.setattr(
            materialization,
            "set_private_mode",
            lambda *_a: (_ for _ in ()).throw(OSError("chmod")),
        )
    elif failure == "fsync":
        monkeypatch.setattr(
            materialization.os,
            "fsync",
            lambda *_a: (_ for _ in ()).throw(OSError("fsync")),
        )
    else:
        real_open = open

        class FailedWrite:
            def __enter__(self):
                self.stream = real_open(target, "xb")
                return self

            def __exit__(self, *args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def write(self, _data):
                raise OSError("write")

        monkeypatch.setattr(
            materialization, "open", lambda *_a, **_k: FailedWrite(), raising=False
        )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        environment._write_private(str(target), b"payload")

    assert (environment.temporary_bytes, environment.temporary_files) == (0, 0)
    assert target.exists() is False


def test_shadow_rejects_non_regular_setting_file(tmp_path: Path) -> None:
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        environment._materialize_regular(
            _setting_file(b"attr", "symlink", b"target"), str(tmp_path / "attr")
        )


def test_shadow_verification_requires_captured_settings(tmp_path: Path) -> None:
    expected = SourceEpoch(b"attributes", b"config")
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(None, expected), time.monotonic() + 5
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        environment.verify_source_epoch()


def test_shadow_verification_bounds_path_input(tmp_path: Path) -> None:
    expected = SourceEpoch(b"attributes", b"config")
    frozen = _frozen_settings()
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path),
        _epoch(frozen, expected, (b"x" * (16 * 1024 * 1024),)),
        time.monotonic() + 5,
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        environment.verify_source_epoch()


def test_shadow_verification_rejects_materialized_config_mismatch(
    tmp_path: Path,
) -> None:
    expected = SourceEpoch(b"attributes", settings.config_fingerprint(()))
    frozen = _frozen_settings(config_entries=())
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(frozen, expected), time.monotonic() + 5
    )
    environment._materialized_config = (settings.ConfigEntry(b"x.value", b"one"),)
    environment.run = lambda *_a, **_k: b""  # type: ignore[method-assign]

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_SOURCE_CHANGED$"):
        environment.verify_source_epoch()


def test_shadow_verification_rejects_attribute_fingerprint_mismatch(
    tmp_path: Path,
) -> None:
    expected = SourceEpoch(b"wrong", settings.config_fingerprint(()))
    frozen = _frozen_settings(config_entries=())
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(frozen, expected), time.monotonic() + 5
    )
    environment.run = lambda *_a, **_k: b""  # type: ignore[method-assign]

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_SOURCE_CHANGED$"):
        environment.verify_source_epoch()


def test_shadow_full_usage_requires_entered_environment(tmp_path: Path) -> None:
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        environment._refresh_all_usage()


def test_shadow_full_usage_rejects_symlink(tmp_path: Path) -> None:
    directory = tmp_path / "shadow"
    directory.mkdir()
    (directory / "link").symlink_to(tmp_path)
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )
    environment._directory = str(directory)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"):
        environment._refresh_all_usage()


def test_shadow_full_usage_wraps_scan_error(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "shadow"
    directory.mkdir()
    (directory / "file").write_bytes(b"x")
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )
    environment._directory = str(directory)
    monkeypatch.setattr(
        epoch_module, "_lstat", lambda *_a: (_ for _ in ()).throw(OSError())
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        environment._refresh_all_usage()


def test_shadow_full_usage_enforces_byte_limit(tmp_path: Path) -> None:
    directory = tmp_path / "shadow"
    directory.mkdir()
    (directory / "file").write_bytes(b"xx")
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5, storage_byte_limit=1
    )
    environment._directory = str(directory)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        environment._refresh_all_usage()


@pytest.mark.parametrize(
    "argv", [[], ["--fsize", "-1", "--", "git"], ["--fsize", "1", "--", "sh"]]
)
def test_git_exec_guard_rejects_unsafe_invocation(argv: list[str]) -> None:
    # PR #1252: the file-size guard accepts only bounded Git commands.
    from tree_sitter_analyzer import git_exec_guard

    assert git_exec_guard.main(argv) == 2


def test_private_copy_failures_have_stable_accounting(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"x")
    destination = tmp_path / "taken"
    destination.touch()
    rolled = []
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        materialization.copy_private(
            str(source), str(destination), lambda *a: None, lambda *a: rolled.append(a)
        )
    assert rolled == [(1, 1)]


def test_shadow_git_commands_run_from_shadow_worktree(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3751341011: cwd cannot expose live old-side attributes.
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), _epoch(), time.monotonic() + 5
    )
    environment.worktree_path = str(tmp_path / "shadow-worktree")
    observed: list[str] = []

    def spy(cwd, _args, **_kwargs):
        observed.append(cwd)
        return b""

    monkeypatch.setattr(epoch_module, "run_git_bounded", spy)

    environment.run(["status"])

    assert observed == [environment.worktree_path]


def test_frozen_settings_storage_charges_optional_core_attributes() -> None:
    # PR #1252 thread 3751628120: all retained setting bytes share the ceiling.
    frozen = _frozen_settings(
        core_attributes_path=b"/core",
        core_attributes=_setting_file(b"/core", "file", b"x"),
    )

    assert settings.frozen_settings_storage(frozen) == 77


def test_frozen_settings_rejects_exhausted_ceiling_before_git() -> None:
    # PR #1252 thread 3751628120: fail before settings output allocation.
    calls = []

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            ".", (), 1e20, lambda *args, **kwargs: calls.append(True), byte_ceiling=0
        )

    assert calls == []
