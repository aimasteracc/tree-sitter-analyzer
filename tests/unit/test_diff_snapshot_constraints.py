from __future__ import annotations

import pytest

import tree_sitter_analyzer.diff_snapshot_constraints as constraints
from tree_sitter_analyzer.source_oracle import SourceOracleError
from tree_sitter_analyzer.source_oracle_git import GitEpoch


class _ConstraintEpoch:
    index_bytes = b"index"
    object_format = "sha1"

    def __init__(self, entry: bytes) -> None:
        self._entry = entry

    def index_map(self) -> dict[bytes, bytes]:
        return {b"architectural-constraints.yml": self._entry}


class _ConstraintGit:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


_REAL_IGNORED_SUBMODULE_SOURCES = constraints._ignored_submodule_sources


def _epoch() -> GitEpoch:
    return GitEpoch(b"a" * 40, "sha1", (), (), (), ())


@pytest.fixture(autouse=True)
def _no_ignored_submodule_sources(monkeypatch):
    monkeypatch.setattr(constraints, "_ignored_submodule_sources", lambda *_args: ())


def test_entry_parts_returns_missing_for_absent_index_entry() -> None:
    assert constraints._entry_parts(None) == (None, None, "missing")


def test_entry_parts_rejects_malformed_index_entry() -> None:
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        constraints._entry_parts(b"100644")


def test_frozen_constraint_config_rejects_non_file_index_entry(monkeypatch) -> None:
    monkeypatch.setattr(constraints, "FrozenGitEnvironment", _ConstraintGit)
    epoch = _ConstraintEpoch(b"120000 " + b"a" * 40 + b" 0")

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        constraints.frozen_index_constraint_config(".", epoch, 1e20, 1024)


def test_frozen_constraint_config_rejects_unreadable_blob(monkeypatch) -> None:
    monkeypatch.setattr(constraints, "FrozenGitEnvironment", _ConstraintGit)
    monkeypatch.setattr(constraints, "_blob", lambda *args: None)
    epoch = _ConstraintEpoch(b"100644 " + b"a" * 40 + b" 0")

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        constraints.frozen_index_constraint_config(".", epoch, 1e20, 1024)


def test_frozen_source_match_rejects_dirty_supported_source(monkeypatch) -> None:
    outputs = iter((b"changed.py\0", b""))
    monkeypatch.setattr(
        constraints, "frozen_index_output", lambda *args, **kwargs: next(outputs)
    )

    result = constraints.frozen_index_sources_match_worktree(".", _epoch(), 1e20, 1024)

    assert result is False


def test_frozen_source_match_allows_dirty_unsupported_file(monkeypatch) -> None:
    outputs = iter((b"README.md\0", b"notes.txt\0"))
    monkeypatch.setattr(
        constraints, "frozen_index_output", lambda *args, **kwargs: next(outputs)
    )

    result = constraints.frozen_index_sources_match_worktree(".", _epoch(), 1e20, 1024)

    assert result is True


def test_frozen_source_match_includes_ignored_untracked_sources(monkeypatch) -> None:
    calls = []

    def output(_root, _index, args, **_kwargs):
        calls.append(args)
        return b"" if len(calls) == 1 else b"ignored.py\0"

    monkeypatch.setattr(constraints, "frozen_index_output", output)

    assert (
        constraints.frozen_index_sources_match_worktree(".", _epoch(), 1e20, 1024)
        is False
    )
    assert calls == [
        [
            "diff-files",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
        ],
        ["ls-files", "--others", "-z"],
    ]


@pytest.mark.parametrize("hint", ["--assume-unchanged", "--skip-worktree"])
def test_frozen_source_match_clears_index_hints_before_worktree_compare(
    tmp_path, hint
) -> None:
    # PR #1254 reviews 3767273213/3767273219: advisory index bits cannot hide bytes.
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "main.py"
    source.write_text("old\n")
    subprocess.run(["git", "add", "main.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(["git", "update-index", hint, "main.py"], cwd=tmp_path, check=True)
    index_bytes = (tmp_path / ".git" / "index").read_bytes()
    source.write_text("new\n")
    epoch = GitEpoch(b"a" * 40, "sha1", (), (), (), (), index_bytes=index_bytes)

    assert (
        constraints.frozen_index_sources_match_worktree(
            str(tmp_path), epoch, __import__("time").monotonic() + 30, 1024
        )
        is False
    )


def test_frozen_source_match_rejects_dirty_gitlink_container(monkeypatch) -> None:
    # PR #1254 review 3768096801: extensionless gitlinks own indexed descendants.
    outputs = iter((b"libs/component\0", b""))
    monkeypatch.setattr(
        constraints, "frozen_index_output", lambda *args, **kwargs: next(outputs)
    )
    entry = b"160000 " + b"a" * 40 + b" 0"
    epoch = GitEpoch(
        b"a" * 40,
        "sha1",
        ((b"libs/component", entry),),
        (b"libs/component",),
        (),
        (),
        index_bytes=b"index",
    )

    result = constraints.frozen_index_sources_match_worktree(".", epoch, 1e20, 1024)

    assert result is False


def test_ignored_submodule_supported_source_marks_staged_plane_divergent(
    monkeypatch,
) -> None:
    # PR #1254 review 3769193852: ignored child files do not dirty a gitlink.
    outputs = iter((b"", b""))
    monkeypatch.setattr(
        constraints, "frozen_index_output", lambda *_args, **_kwargs: next(outputs)
    )
    monkeypatch.setattr(
        constraints, "_ignored_submodule_sources", lambda *_args: (b"vendor/hidden.py",)
    )

    result = constraints.frozen_index_sources_match_worktree(".", _epoch(), 1e20, 1024)

    assert result is False


def test_constraint_error_maps_snapshot_capacity_to_config_capacity() -> None:
    error = SourceOracleError("DIFF_SNAPSHOT_CAPACITY")

    assert constraints._constraint_error(error) == "CONSTRAINT_CONFIG_CAPACITY"


def test_constraint_error_hides_unclassified_source_oracle_failure() -> None:
    error = SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")

    assert constraints._constraint_error(error) == "CONSTRAINT_CONFIG_UNSAFE"


def test_staged_constraint_config_preserves_consumer_specific_error() -> None:
    def rejected(*_args):
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")

    result = constraints.staged_constraint_config(
        "/project", _epoch(), 10.0, 20, rejected
    )
    assert result == (None, None, (), "CONSTRAINT_CONFIG_CAPACITY")


def test_ignored_submodule_inventory_parses_supported_and_unsupported_records(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        constraints, "_ignored_submodule_sources", _REAL_IGNORED_SUBMODULE_SOURCES
    )
    (tmp_path / ".gitmodules").write_text("[submodule]\n")
    gitlink = b"160000 " + b"a" * 40 + b" 0"
    epoch = GitEpoch(b"a" * 40, "sha1", ((b"vendor", gitlink),), (), (), ())
    monkeypatch.setattr(
        constraints,
        "run_git_bounded",
        lambda *_a, **_k: b"H\0vendor\0? ignored.txt\0? ignored.py\0",
    )
    assert constraints._ignored_submodule_sources(str(tmp_path), epoch, 1e20, 20) == (
        b"vendor/ignored.py",
    )


def test_ignored_submodule_inventory_rejects_orphan_record(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        constraints, "_ignored_submodule_sources", _REAL_IGNORED_SUBMODULE_SOURCES
    )
    (tmp_path / ".gitmodules").write_text("[submodule]\n")
    gitlink = b"160000 " + b"a" * 40 + b" 0"
    epoch = GitEpoch(b"a" * 40, "sha1", ((b"vendor", gitlink),), (), (), ())
    outputs = iter((b"orphan.py", b"H"))
    monkeypatch.setattr(constraints, "run_git_bounded", lambda *_a, **_k: next(outputs))
    for _case in range(2):
        with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
            constraints._ignored_submodule_sources(str(tmp_path), epoch, 1e20, 20)
