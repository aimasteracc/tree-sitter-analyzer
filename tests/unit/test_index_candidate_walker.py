from __future__ import annotations

import os
from typing import Any

import pytest

from tree_sitter_analyzer.index_candidate_walker import (
    CandidateDiscoveryBudgetExceeded,
    CandidateDiscoveryError,
    walk_candidate_entries,
)

_DEFAULTS = {
    "excluded_dir_names": frozenset(),
    "entry_budget": 10,
    "path_byte_budget": 1_000,
    "discovery_seconds": 5.0,
    "budget_error": "DISCOVERY_LIMIT",
}


class _Scanner:
    def __init__(self, *entries: Any) -> None:
        self._entries = iter(entries)

    def __iter__(self) -> _Scanner:
        return self

    def __next__(self) -> Any:
        return next(self._entries)

    def close(self) -> None:
        return None


def test_inaccessible_root_raises_typed_discovery_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PR #1253 thread 3758212492: an unreadable root is never an exact empty scope.
    import tree_sitter_analyzer.index_candidate_walker as walker

    monkeypatch.setattr(
        walker.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(walker.CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/denied", **_DEFAULTS))


def test_unencodable_path_exhausts_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    class InvalidPath:
        def __fspath__(self) -> str:
            raise TypeError("not path-like")

    class Entry:
        path = InvalidPath()
        name = "invalid"

    import tree_sitter_analyzer.index_candidate_walker as walker

    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(os, "scandir", lambda _path: _Scanner(Entry()))

    with pytest.raises(CandidateDiscoveryBudgetExceeded, match="DISCOVERY_LIMIT"):
        list(walk_candidate_entries("/root", **_DEFAULTS))


def test_directory_stat_error_treats_entry_as_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Entry:
        path = "/root/source.py"
        name = "source.py"

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            raise OSError("entry disappeared")

    import tree_sitter_analyzer.index_candidate_walker as walker

    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(os, "scandir", lambda _path: _Scanner(Entry()))

    with pytest.raises(walker.CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))


def test_discovery_deadline_rejects_first_late_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.index_candidate_walker as walker

    class Entry:
        path = "/root/late.py"
        name = "late.py"

    monkeypatch.setattr(walker.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(os, "scandir", lambda _path: _Scanner(Entry()))

    with pytest.raises(CandidateDiscoveryBudgetExceeded, match="DISCOVERY_LIMIT"):
        list(
            walk_candidate_entries("/root", **{**_DEFAULTS, "discovery_seconds": -1.0})
        )


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_descendants_are_opened_and_scanned_fd_relative(tmp_path, monkeypatch):
    # PR #1253 thread 3758212517: descendant pathnames are never scanned.
    import tree_sitter_analyzer.index_candidate_walker as walker

    child = tmp_path / "pkg"
    child.mkdir()
    source = child / "source.py"
    source.write_text("value = 1\n")
    real_open = walker.os.open
    real_scandir = walker.os.scandir
    child_opens = []
    scan_targets = []

    def recording_open(path, flags, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            child_opens.append((path, kwargs["dir_fd"], flags))
        return real_open(path, flags, *args, **kwargs)

    def recording_scandir(path):
        scan_targets.append(path)
        return real_scandir(path)

    monkeypatch.setattr(walker.os, "open", recording_open)
    monkeypatch.setattr(walker.os, "scandir", recording_scandir)
    candidates = list(walk_candidate_entries(str(tmp_path), **_DEFAULTS))

    assert candidates == [str(source)]
    assert [item[0] for item in child_opens] == ["pkg"]
    assert all(isinstance(target, int) for target in scan_targets)


def test_builder_records_iteration_failure_as_incomplete(tmp_path):
    # PR #1253 thread 3758212492: partial enumeration is never authoritative.
    from tree_sitter_analyzer.indexing_snapshot import build_index_candidate_snapshot

    source = tmp_path / "kept.py"
    source.write_text("value = 1\n")

    def failing_walk(_root):
        yield str(source)
        raise CandidateDiscoveryError("INDEX_CANDIDATE_DISCOVERY_ERROR")

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=failing_walk,
        language_fn=lambda _path: "python",
    )

    assert (snapshot.selected, snapshot.errors, snapshot.discovery_error) == (
        1,
        1,
        "INDEX_CANDIDATE_DISCOVERY_ERROR",
    )
    assert snapshot.metrics()["discovery_complete"] is False
