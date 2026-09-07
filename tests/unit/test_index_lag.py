"""Behavioral tests for bounded qualitative index lag."""

from __future__ import annotations

import os

import pytest

from tree_sitter_analyzer.index_lag import _newest_source_mtime, compute_qualitative_lag

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def test_missing_cache_has_unknown_lag(tmp_path):
    assert compute_qualitative_lag(str(tmp_path), str(tmp_path / "missing.db")) is None


def test_missing_project_has_no_source_mtime(tmp_path):
    assert _newest_source_mtime(str(tmp_path / "missing")) is None


@requires_posix_fd
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


@requires_posix_fd
@pytest.mark.parametrize("extension", (".c", ".swift"))
def test_lag_uses_indexer_extension_registry(tmp_path, extension):
    # PR #1253 thread 3760724586: lag and indexing share one extension surface.
    cache = tmp_path / "index.db"
    source = tmp_path / f"app{extension.upper()}"
    cache.write_bytes(b"db")
    source.write_text("source\n")
    os.utime(cache, (10, 10))
    os.utime(source, (25, 25))

    assert compute_qualitative_lag(str(tmp_path), str(cache)) == 15.0


@requires_posix_fd
def test_lag_excludes_arbitrary_hidden_directory(tmp_path):
    # PR #1253 Codex thread 3763183167: lag matches authoritative hidden scope.
    hidden = tmp_path / ".private-sources"
    hidden.mkdir()
    source = hidden / "new.py"
    source.write_text("value = 1\n")

    assert _newest_source_mtime(str(tmp_path)) is None


@requires_posix_fd
def test_source_scan_stops_at_cap(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "first.py").write_text("first = 1\n")
    (tmp_path / "second.py").write_text("second = 2\n")
    monkeypatch.setattr(lag, "_LAG_WALK_FILE_CAP", 1)

    assert lag._newest_source_mtime(str(tmp_path)) is None


@requires_posix_fd
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


@requires_posix_fd
def test_lag_scan_counts_unsupported_entries(tmp_path, monkeypatch):
    # PR #1253 review thread 2081: unsupported names consume the all-entry budget.
    import tree_sitter_analyzer.index_lag as lag

    (tmp_path / "notes.txt").write_text("ignored\n")
    (tmp_path / "app.py").write_text("value = 1\n")
    monkeypatch.setattr(lag, "_LAG_ENTRY_CAP", 1)

    assert lag._newest_source_mtime(str(tmp_path)) is None


@requires_posix_fd
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


@requires_posix_fd
def test_lag_scan_stops_at_deadline(tmp_path, monkeypatch):
    # PR #1253: lag traversal obeys its wall-clock budget before reading entries.
    import tree_sitter_analyzer.index_lag as lag

    expired = 10.0 + lag._LAG_DEADLINE_SECONDS + 1.0
    ticks = [10.0, expired]
    monkeypatch.setattr(
        lag.time, "monotonic", lambda: ticks.pop(0) if ticks else expired
    )

    assert lag._newest_source_mtime(str(tmp_path)) is None


@requires_posix_fd
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


@requires_posix_fd
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


@requires_posix_fd
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


@pytest.fixture
def portable_lag(monkeypatch):
    """仅切换平台分派，目录、文件和时间戳仍由真实文件系统提供。"""
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_lag as lag

    monkeypatch.setattr(
        lag, "os", SimpleNamespace(name="nt", path=os.path, scandir=os.scandir)
    )
    return lag


def test_portable_lag_reads_nested_sources_and_ignores_excluded_entries(
    tmp_path, portable_lag
):
    # PR #1350：Windows 路径应使用同一源文件集合，而不是忽略嵌套目录。
    cache = tmp_path / "index.db"
    cache.write_bytes(b"cache")
    os.utime(cache, (20, 20))
    for relative, mtime in [
        ("src/App.JAVA", 25),
        ("notes.txt", 60),
        (".hidden/secret.py", 70),
        ("node_modules/dependency.py", 80),
    ]:
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
    assert portable_lag.compute_qualitative_lag(str(tmp_path), str(cache)) == 5.0


@pytest.mark.parametrize(
    "budget", ["_LAG_ENTRY_CAP", "_LAG_PATH_BYTE_CAP", "_LAG_WALK_FILE_CAP"]
)
def test_portable_lag_exhausted_budget_returns_unknown(
    tmp_path, portable_lag, monkeypatch, budget
):
    # PR #1350：扫描超预算不能返回已扫描前缀的时间戳。
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 2\n", encoding="utf-8")
    monkeypatch.setattr(portable_lag, budget, 1)
    assert portable_lag._newest_source_mtime(str(tmp_path)) is None


def test_portable_lag_expired_deadline_does_not_scan(
    tmp_path, portable_lag, monkeypatch
):
    from types import SimpleNamespace

    ticks = iter([0.0, 1.0])
    monkeypatch.setattr(
        portable_lag, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )
    scans = []

    def scan(path):
        scans.append(path)
        return os.scandir(path)

    monkeypatch.setattr(portable_lag.os, "scandir", scan)
    assert portable_lag._newest_source_mtime(str(tmp_path)) is None
    assert scans == []


@pytest.mark.parametrize("failure_point", ["scandir", "stat"])
def test_portable_lag_unreadable_subtree_does_not_report_partial_age(
    tmp_path, portable_lag, monkeypatch, failure_point
):
    # PR #1350：只在 OS 边界注入 EACCES，不能把不完整扫描伪装成精确的最新时间。
    import errno
    from types import SimpleNamespace

    (tmp_path / "ok.py").write_text("ok = 1\n", encoding="utf-8")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "new.py").write_text("new = 1\n", encoding="utf-8")
    attempted = []

    def scan(path):
        if os.path.abspath(path) == str(blocked):
            attempted.append(str(blocked))
            if failure_point == "scandir":
                raise PermissionError(errno.EACCES, "denied", str(blocked))

            def denied_stat(*, follow_symlinks):
                assert follow_symlinks is False
                raise PermissionError(errno.EACCES, "denied", str(blocked / "new.py"))

            with os.scandir(path) as entries:
                return [
                    SimpleNamespace(name=entry.name, path=entry.path, stat=denied_stat)
                    for entry in entries
                ]
        return os.scandir(path)

    monkeypatch.setattr(portable_lag.os, "scandir", scan)
    assert portable_lag._newest_source_mtime(str(tmp_path)) is None
    assert attempted == [str(blocked)]
