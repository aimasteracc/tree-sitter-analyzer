"""Behavioral tests for bounded qualitative index lag."""

from __future__ import annotations

import os

from tree_sitter_analyzer.index_lag import _newest_source_mtime, compute_qualitative_lag


def test_missing_cache_has_unknown_lag(tmp_path):
    assert compute_qualitative_lag(str(tmp_path), str(tmp_path / "missing.db")) is None


def test_missing_project_has_no_source_mtime(tmp_path):
    assert _newest_source_mtime(str(tmp_path / "missing")) is None


def test_lag_uses_newest_supported_source_and_clamps_at_zero(tmp_path):
    cache = tmp_path / "index.db"
    source = tmp_path / "app.py"
    ignored = tmp_path / "notes.txt"
    cache.write_bytes(b"db")
    source.write_text("value = 1\n")
    ignored.write_text("not source\n")
    os.utime(cache, (20, 20))
    os.utime(source, (10, 10))
    os.utime(ignored, (30, 30))

    assert compute_qualitative_lag(str(tmp_path), str(cache)) == 0.0


def test_source_scan_stops_at_cap(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "first.py").write_text("first = 1\n")
    (tmp_path / "second.py").write_text("second = 2\n")
    monkeypatch.setattr(lag, "_LAG_WALK_FILE_CAP", 1)

    assert lag._newest_source_mtime(str(tmp_path)) is None


def test_symlink_source_is_not_lag_evidence(tmp_path):
    # PR #1253 review thread 2081: lag traversal never follows source aliases.
    target = tmp_path / "target.py"
    target.write_text("value = 1\n")
    linked = tmp_path / "linked.py"
    try:
        linked.symlink_to(target)
    except OSError:
        import pytest

        pytest.skip("GH-1253: symlink creation unavailable")
    target.unlink()

    assert _newest_source_mtime(str(tmp_path)) is None


def test_lag_scan_counts_unsupported_entries(tmp_path, monkeypatch):
    # PR #1253 review thread 2081: unsupported names consume the all-entry budget.
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "notes.txt").write_text("ignored\n")
    (tmp_path / "app.py").write_text("value = 1\n")
    monkeypatch.setattr(lag, "_LAG_ENTRY_CAP", 1)

    assert lag._newest_source_mtime(str(tmp_path)) is None


def test_lag_scan_enforces_total_path_byte_budget(tmp_path, monkeypatch):
    # PR #1253 review thread 2081: relative path bytes are globally bounded.
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "app.py").write_text("value = 1\n")
    monkeypatch.setattr(lag, "_LAG_PATH_BYTE_CAP", 5)

    assert lag._newest_source_mtime(str(tmp_path)) is None


def test_non_posix_lag_is_unavailable(tmp_path, monkeypatch):
    # PR #1253 review thread 2081: pathname fallback is never freshness evidence.
    import tree_sitter_analyzer.index_lag as lag

    monkeypatch.setattr(lag.os, "name", "nt")

    assert (
        lag.compute_qualitative_lag(str(tmp_path), str(tmp_path / "index.db")),
        lag._newest_source_mtime(str(tmp_path)),
    ) == (None, None)


def test_lag_scan_stops_at_deadline(tmp_path, monkeypatch):
    # PR #1253: lag traversal obeys its wall-clock budget before reading entries.
    import tree_sitter_analyzer.index_lag as lag

    expired = 10.0 + lag._LAG_DEADLINE_SECONDS + 1.0
    ticks = [10.0, expired]
    monkeypatch.setattr(
        lag.time, "monotonic", lambda: ticks.pop(0) if ticks else expired
    )

    assert lag._newest_source_mtime(str(tmp_path)) is None


def test_lag_scan_suppresses_descriptor_cleanup_error(tmp_path, monkeypatch):
    # PR #1253: cleanup failure cannot turn unavailable lag into a hard failure.
    import tree_sitter_analyzer.index_lag as lag

    monkeypatch.setattr(lag.os, "open", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(lag.os, "scandir", lambda _fd: iter(()))
    monkeypatch.setattr(
        lag.os,
        "close",
        lambda _fd: (_ for _ in ()).throw(OSError("already closed")),
    )

    assert lag._newest_source_mtime(str(tmp_path)) is None


def test_root_fd_closes_when_scandir_setup_raises(tmp_path, monkeypatch):
    # PR #1253 review thread 3755297953: open/scandir ownership is atomic.
    import tree_sitter_analyzer.index_lag as lag

    opened: list[int] = []
    real_open = lag.os.open
    real_close = lag.os.close

    def tracked_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(lag.os, "open", tracked_open)
    monkeypatch.setattr(
        lag.os, "scandir", lambda _fd: (_ for _ in ()).throw(OSError("scandir"))
    )

    assert lag._newest_source_mtime(str(tmp_path)) is None
    assert len(opened) == 1
    try:
        os.fstat(opened[0])
    except OSError:
        closed = True
    else:
        closed = False
        real_close(opened[0])
    assert closed is True


def test_child_fd_closes_when_scandir_setup_raises(tmp_path, monkeypatch):
    # PR #1253 review thread 3755297953: child ownership transfers after scandir.
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "child").mkdir()
    opened: list[int] = []
    real_open = lag.os.open
    real_close = lag.os.close
    real_scandir = lag.os.scandir
    scans = 0

    def tracked_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def second_scan_raises(fd):
        nonlocal scans
        scans += 1
        if scans == 2:
            raise OSError("scandir")
        return real_scandir(fd)

    monkeypatch.setattr(lag.os, "open", tracked_open)
    monkeypatch.setattr(lag.os, "scandir", second_scan_raises)

    assert lag._newest_source_mtime(str(tmp_path)) is None
    assert len(opened) == 2
    states = []
    for fd in opened:
        try:
            os.fstat(fd)
        except OSError:
            states.append(True)
        else:
            states.append(False)
            real_close(fd)
    assert states == [True, True]
