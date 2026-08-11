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


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_scanner_iteration_error_closes_owned_fd(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class FailingScanner(_Scanner):
        def __next__(self):
            raise OSError("scan failed")

    closed: list[int] = []
    monkeypatch.setattr(walker.os, "open", lambda *_args, **_kwargs: 41)
    monkeypatch.setattr(walker.os, "fstat", lambda _fd: object())
    monkeypatch.setattr(walker.os, "scandir", lambda _fd: FailingScanner())
    monkeypatch.setattr(walker.os, "close", closed.append)

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert closed == [41]


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_unencodable_path_exhausts_byte_budget(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class Entry:
        name = "source.py"

    scanner = _Scanner(Entry())
    monkeypatch.setattr(walker.os, "open", lambda *_args, **_kwargs: 42)
    monkeypatch.setattr(walker.os, "fstat", lambda _fd: object())
    monkeypatch.setattr(walker.os, "scandir", lambda _fd: scanner)
    monkeypatch.setattr(walker.os, "close", lambda _fd: None)
    real_join = walker.os.path.join

    class UnencodablePath(str):
        def encode(self, *_args, **_kwargs):
            raise UnicodeError("not encodable")

    monkeypatch.setattr(
        walker.os.path,
        "join",
        lambda parent, child: (
            UnencodablePath("/root/source.py")
            if parent == "/root" and child == "source.py"
            else real_join(parent, child)
        ),
    )

    with pytest.raises(CandidateDiscoveryBudgetExceeded, match="DISCOVERY_LIMIT"):
        list(walk_candidate_entries("/root", **_DEFAULTS))


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_entry_stat_error_closes_owned_fd(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class Entry:
        name = "source.py"

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            raise OSError("entry stat failed")

    closed: list[int] = []
    monkeypatch.setattr(walker.os, "open", lambda *_args, **_kwargs: 43)
    monkeypatch.setattr(walker.os, "fstat", lambda _fd: object())
    monkeypatch.setattr(walker.os, "scandir", lambda _fd: _Scanner(Entry()))
    monkeypatch.setattr(walker.os, "close", closed.append)

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert closed == [43]


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
@pytest.mark.parametrize("failure", ["open", "fstat", "scandir"])
def test_posix_child_failure_closes_every_acquired_fd(monkeypatch, failure):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class DirectoryEntry:
        name = "pkg"

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return type("Info", (), {"st_dev": 1, "st_ino": 2, "st_mode": 0o040000})()

    root_scanner = _Scanner(DirectoryEntry())
    closed: list[int] = []

    def open_fd(*_args, **kwargs):
        if "dir_fd" not in kwargs:
            return 51
        if failure == "open":
            raise OSError("child open failed")
        return 52

    monkeypatch.setattr(walker.os, "open", open_fd)

    def fstat(fd):
        if failure == "fstat" and fd == 52:
            raise OSError("child fstat failed")
        return type("Info", (), {"st_dev": 1, "st_ino": 2, "st_mode": 0o040000})()

    def scandir(fd):
        if failure == "scandir" and fd == 52:
            raise OSError("child scandir failed")
        return root_scanner

    monkeypatch.setattr(walker.os, "fstat", fstat)
    monkeypatch.setattr(walker.os, "scandir", scandir)
    monkeypatch.setattr(walker.os, "close", closed.append)

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert closed == ([51] if failure == "open" else [52, 51])


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_non_directory_child_fd_is_rejected(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class DirectoryEntry:
        name = "pkg"

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return type("Info", (), {"st_dev": 1, "st_ino": 2, "st_mode": 0o040000})()

    closed: list[int] = []
    monkeypatch.setattr(
        walker.os, "open", lambda *_args, **kwargs: 61 if "dir_fd" not in kwargs else 62
    )
    monkeypatch.setattr(
        walker.os,
        "fstat",
        lambda fd: type(
            "Info",
            (),
            {
                "st_dev": 1,
                "st_ino": 2,
                "st_mode": 0o100000 if fd == 62 else 0o040000,
            },
        )(),
    )
    monkeypatch.setattr(walker.os, "scandir", lambda _fd: _Scanner(DirectoryEntry()))
    monkeypatch.setattr(walker.os, "close", closed.append)

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert closed == [62, 61]


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_cleanup_ignores_close_error_without_masking_budget(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class Entry:
        name = "source.py"

        def is_dir(self, *, follow_symlinks):
            return False

    class CloseErrorScanner(_Scanner):
        def close(self):
            raise OSError("scanner close failed")

    monkeypatch.setattr(walker.os, "open", lambda *_args, **_kwargs: 71)
    monkeypatch.setattr(walker.os, "fstat", lambda _fd: object())
    monkeypatch.setattr(walker.os, "scandir", lambda _fd: CloseErrorScanner(Entry()))
    monkeypatch.setattr(walker.os, "close", lambda _fd: None)

    iterator = walk_candidate_entries("/root", **{**_DEFAULTS, "entry_budget": 0})
    with pytest.raises(CandidateDiscoveryBudgetExceeded, match="DISCOVERY_LIMIT"):
        list(iterator)


def test_path_fallback_root_scandir_error_is_typed(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(
        walker.os,
        "scandir",
        lambda _path: (_ for _ in ()).throw(OSError("root scan failed")),
    )
    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))


def test_path_fallback_iteration_error_closes_scanner(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class FailingScanner(_Scanner):
        closed = False

        def __next__(self):
            raise OSError("iteration failed")

        def close(self):
            self.closed = True

    scanner = FailingScanner()
    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(walker.os, "scandir", lambda _path: scanner)
    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert scanner.closed is True


def test_path_fallback_child_scandir_error_releases_parent_lease(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class DirectoryEntry:
        name = "pkg"
        path = "/root/pkg"

        def is_dir(self, *, follow_symlinks):
            return True

    parent = _Scanner(DirectoryEntry())
    closed = False
    original_close = parent.close

    def close_parent():
        nonlocal closed
        closed = True
        original_close()

    parent.close = close_parent
    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(
        walker.os,
        "scandir",
        lambda path: (
            parent
            if path == "/root"
            else (_ for _ in ()).throw(OSError("child scan failed"))
        ),
    )
    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert closed is True


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_root_fstat_error_closes_root_fd(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    closed: list[int] = []
    monkeypatch.setattr(walker.os, "open", lambda *_args, **_kwargs: 81)
    monkeypatch.setattr(
        walker.os,
        "fstat",
        lambda _fd: (_ for _ in ()).throw(OSError("root fstat failed")),
    )
    monkeypatch.setattr(walker.os, "close", closed.append)

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries("/root", **_DEFAULTS))
    assert closed == [81]


def test_path_fallback_yields_file_and_closes_exhausted_scanner(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class FileEntry:
        name = "source.py"
        path = "/root/source.py"

        def is_dir(self, *, follow_symlinks):
            return False

    class RecordingScanner(_Scanner):
        closed = False

        def close(self):
            self.closed = True

    scanner = RecordingScanner(FileEntry())
    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(walker.os, "scandir", lambda _path: scanner)

    assert list(walk_candidate_entries("/root", **_DEFAULTS)) == ["/root/source.py"]
    assert scanner.closed is True


def test_path_fallback_excluded_directory_is_not_opened(monkeypatch):
    import tree_sitter_analyzer.index_candidate_walker as walker

    class DirectoryEntry:
        name = "vendor"
        path = "/root/vendor"

        def is_dir(self, *, follow_symlinks):
            return True

    scanner = _Scanner(DirectoryEntry())
    calls: list[str] = []

    def scandir(path):
        calls.append(path)
        return scanner

    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(walker.os, "scandir", scandir)
    values = list(
        walk_candidate_entries(
            "/root", **{**_DEFAULTS, "excluded_dir_names": frozenset({"vendor"})}
        )
    )
    assert (values, calls) == ([], ["/root"])


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_excluded_directory_is_not_opened(monkeypatch, tmp_path):
    import tree_sitter_analyzer.index_candidate_walker as walker

    excluded = tmp_path / "vendor"
    excluded.mkdir()
    (excluded / "hidden.py").write_text("value = 1\n")
    opened: list[str] = []
    real_open = walker.os.open

    def recording_open(path, flags, *args, **kwargs):
        opened.append(os.fspath(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(walker.os, "open", recording_open)
    values = list(
        walk_candidate_entries(
            str(tmp_path), **{**_DEFAULTS, "excluded_dir_names": frozenset({"vendor"})}
        )
    )
    assert (values, opened) == ([], [str(tmp_path), str(tmp_path)])


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_empty_root_replacement_is_discovery_error(monkeypatch, tmp_path):
    # PR #1253 thread 3759606788: an exhausted old root cannot certify its replacement.
    import tree_sitter_analyzer.index_candidate_walker as walker

    root = tmp_path / "project"
    root.mkdir()
    original = tmp_path / "old-project"
    real_scandir = walker.os.scandir
    swapped = False

    class SwapOnFirstRead:
        def __init__(self, scanner):
            self.scanner = scanner

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal swapped
            if not swapped:
                swapped = True
                root.rename(original)
                root.mkdir()
                (root / "new.py").write_text("value = 2\n")
                (root / ".ast-cache").mkdir()
                (root / ".ast-cache" / "index.db").write_bytes(b"new")
            return next(self.scanner)

        def close(self):
            self.scanner.close()

    monkeypatch.setattr(
        walker.os, "scandir", lambda fd: SwapOnFirstRead(real_scandir(fd))
    )

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries(str(root), **_DEFAULTS))


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_posix_missing_root_at_final_reopen_is_discovery_error(monkeypatch, tmp_path):
    # PR #1253 thread 3759606788: disappearance at final pathname check is typed.
    import tree_sitter_analyzer.index_candidate_walker as walker

    real_open = walker.os.open
    opens = 0

    def disappear_on_reopen(path, flags, *args, **kwargs):
        nonlocal opens
        opens += 1
        if opens == 2:
            raise FileNotFoundError(path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(walker.os, "open", disappear_on_reopen)

    with pytest.raises(CandidateDiscoveryError, match="INDEX_CANDIDATE"):
        list(walk_candidate_entries(str(tmp_path), **_DEFAULTS))
