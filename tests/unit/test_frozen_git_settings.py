from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.unit._diff_snapshot_support import make_repo
from tree_sitter_analyzer import diff_snapshot_epoch as epoch_module
from tree_sitter_analyzer import frozen_git_settings as settings
from tree_sitter_analyzer.diff_snapshot_registry import DiffSnapshotRegistry
from tree_sitter_analyzer.source_epoch import (
    GitEpoch,
    SourceEpoch,
    capture_source_epoch,
)
from tree_sitter_analyzer.source_oracle import SafePath, SourceOracleError


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
    )


def test_effective_config_parser_preserves_order_and_drops_directives() -> None:
    raw = (
        b"file:a\0x.multi\none\0"
        b"file:b\0include.path\nsecret\0"
        b"file:a\0x.flag\0"
        b"file:a\0x.multi\ntwo\0"
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


def test_capture_settings_rejects_nul_core_attributes_path(tmp_path: Path) -> None:
    def output(_root, args, **_kwargs):
        if args[0] == "config" and "--path" in args:
            return b"bad\0path\n"
        return b""

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        settings.capture_frozen_git_settings(str(tmp_path), (), 1e20, output)


def test_capture_settings_enforces_total_byte_budget(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "_MAX_SETTINGS_BYTES", 1)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )


def test_capture_settings_enforces_attribute_file_budget(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "_MAX_SETTINGS_FILES", 1)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (b".gitattributes",), 1e20, lambda *_a, **_k: b""
        )


def test_capture_settings_rejects_invalid_attribute_leaf(
    tmp_path: Path, monkeypatch
) -> None:
    reader = lambda *_a, **_k: SafePath(None, (), "directory")  # noqa: E731
    monkeypatch.setattr(settings, "safe_workspace_path", reader)
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_SPECIAL_FILE$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (b".gitattributes",), 1e20, lambda *_a, **_k: b""
        )
    oversized = SafePath(b"x" * settings._MAX_SETTINGS_BYTES, (), "file")
    monkeypatch.setattr(settings, "safe_workspace_path", lambda *_a, **_k: oversized)
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )


def test_capture_settings_charges_attribute_path_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    info = os.fsencode(settings._absolute_path(str(tmp_path), b".git/info/attributes"))
    objects = os.fsencode(settings._absolute_path(str(tmp_path), b".git/objects"))
    budget = len(info) + len(objects) + len(b".gitattributes") - 1
    monkeypatch.setattr(settings, "_MAX_SETTINGS_BYTES", budget)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )


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


def test_source_epoch_bounds_attribute_path_input(monkeypatch) -> None:
    monkeypatch.setattr("tree_sitter_analyzer.source_epoch._MAX_SETTINGS_PATH_BYTES", 1)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        capture_source_epoch(".", b"", (b"long",), deadline=1e20, object_format="sha1")


@pytest.mark.parametrize("inactive", [b"unspecified", b"unset"])
def test_filter_attribute_inactive_semantics_are_allowed(inactive: bytes) -> None:
    # PR #1252 review thread 4861: only inactive filter states are deterministic.
    settings.reject_active_filters(b"a.py\0filter\0" + inactive + b"\0", (b"a.py",))


@pytest.mark.parametrize("active", [b"set", b"lfs", b"custom-driver"])
def test_filter_attribute_active_semantics_are_rejected(active: bytes) -> None:
    # PR #1252 review thread 4861: external clean drivers must never run.
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_UNSUPPORTED_FILTER"):
        settings.reject_active_filters(b"a.py\0filter\0" + active + b"\0", (b"a.py",))


@pytest.mark.parametrize(
    "raw",
    [
        b"a.py\0filter",
        b"",
        b"other.py\0filter\0unspecified\0",
        b"a.py\0text\0unspecified\0",
    ],
)
def test_filter_attribute_malformed_output_fails_closed(raw: bytes) -> None:
    # PR #1252 review thread 4861: frozen check-attr output is exact.
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        settings.reject_active_filters(raw, (b"a.py",))


def test_filter_attribute_output_without_final_nul_is_accepted() -> None:
    # PR #1252 review thread 4861: bounded Git output need not end in a NUL.
    settings.reject_active_filters(b"a.py\0filter\0unspecified", (b"a.py",))


def test_ignored_directory_attributes_are_frozen_for_binary_diff(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X2mXl: ignored settings still apply.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "a.txt").write_bytes(b"before\n")
    (tmp_path / ".gitignore").write_text("dir/.gitattributes\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    (directory / ".gitattributes").write_text("*.txt binary\n")
    (directory / "a.txt").write_bytes(b"after\n")
    result = DiffSnapshotRegistry().create(str(tmp_path), "diff", [])

    assert result["success"] is True
    assert [(item["path"], item["binary"]) for item in result["changed_records"]] == [
        ("dir/a.txt", True)
    ]


def test_active_replace_ref_cannot_split_snapshot_head_evidence(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X2mXp: use the original object graph.
    root = make_repo(tmp_path)
    run = lambda *args, input_=None: subprocess.run(  # noqa: E731
        ["git", *args], cwd=root, input=input_, check=True, capture_output=True
    ).stdout.strip()
    original = run("rev-parse", "HEAD")
    raw_blob = run("rev-parse", "HEAD:old.py")
    blob = run("hash-object", "-w", "--stdin", input_=b"replacement = True\n")
    tree = run("mktree", input_=b"100644 blob " + blob + b"\told.py\n")
    replacement = run("commit-tree", tree.decode(), input_=b"replacement commit\n")
    run("update-ref", "refs/replace/" + original.decode(), replacement.decode())
    (root / "old.py").write_bytes(b"value = 2\n")
    run("add", "old.py")
    live_patch = run("diff", "--cached")
    result = (registry := DiffSnapshotRegistry()).create(str(root), "staged", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("old.py")
    assert b"-replacement = True" in live_patch
    assert frozen is not None
    old_oid = result["changed_records"][0]["old_oid"].encode("ascii")
    assert (frozen.old_bytes, old_oid) == (b"value = 1\n", raw_blob)
    assert b"-value = 1" in consumer.snapshot.normalized_patch
    consumer.release()


@pytest.mark.parametrize(
    "argv", [[], ["--fsize", "-1", "--", "git"], ["--fsize", "1", "--", "sh"]]
)
def test_git_exec_guard_rejects_unsafe_invocation(argv: list[str]) -> None:
    # PR #1252: the file-size guard accepts only bounded Git commands.
    from tree_sitter_analyzer import git_exec_guard

    assert git_exec_guard.main(argv) == 2
