from __future__ import annotations

import os
from typing import Any

import pytest

from tree_sitter_analyzer.index_candidate_walker import (
    CandidateDiscoveryBudgetExceeded,
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


def test_inaccessible_root_has_no_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    def inaccessible(_path: str) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "scandir", inaccessible)

    assert list(walk_candidate_entries("/denied", **_DEFAULTS)) == []


def test_unencodable_path_exhausts_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    class InvalidPath:
        def __fspath__(self) -> str:
            raise TypeError("not path-like")

    class Entry:
        path = InvalidPath()
        name = "invalid"

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

    monkeypatch.setattr(os, "scandir", lambda _path: _Scanner(Entry()))

    assert list(walk_candidate_entries("/root", **_DEFAULTS)) == ["/root/source.py"]


def test_discovery_deadline_rejects_first_late_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.index_candidate_walker as walker

    class Entry:
        path = "/root/late.py"
        name = "late.py"

    monkeypatch.setattr(walker.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(os, "scandir", lambda _path: _Scanner(Entry()))

    with pytest.raises(CandidateDiscoveryBudgetExceeded, match="DISCOVERY_LIMIT"):
        list(
            walk_candidate_entries("/root", **{**_DEFAULTS, "discovery_seconds": -1.0})
        )
