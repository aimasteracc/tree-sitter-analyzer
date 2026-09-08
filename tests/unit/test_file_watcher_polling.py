"""#1405：监听扫描器的续跑、局部故障隔离和原生句柄读取契约。"""

import os
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.file_watcher_polling as owner


@pytest.fixture
def scanner(tmp_path):
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    errors = []
    scanner = owner.PollingScanner(str(tmp_path), lambda: errors.append("error"))
    yield scanner, errors
    scanner.close()


def test_bounded_pass_resumes_without_restarting(scanner, tmp_path, monkeypatch):
    scan, errors = scanner
    monkeypatch.setattr(owner, "_POLL_ENTRIES", 1)
    assert scan.scan(baseline=True) == []
    cursor = scan._cursor
    assert scan.scan() == []
    assert scan._cursor is cursor
    assert scan.scan() == []
    assert scan._cursor is None
    assert sorted(scan.snapshot) == [str(tmp_path / "a.py"), str(tmp_path / "b.py")]
    for path in tmp_path.iterdir():
        path.write_text("changed = 1\n", encoding="utf-8")
    changes = [path for _ in range(3) for path in scan.scan()]
    assert sorted(changes) == sorted(scan.snapshot)
    assert errors == []


def test_deletion_waits_until_full_pass(scanner, tmp_path, monkeypatch):
    scan, errors = scanner
    scan.scan(baseline=True)
    (tmp_path / "a.py").unlink()
    monkeypatch.setattr(owner, "_POLL_ENTRIES", 1)
    assert scan.scan() == []
    assert scan.scan() == [str(tmp_path / "a.py")]
    assert sorted(scan.snapshot) == [str(tmp_path / "b.py")]
    assert errors == []


def test_deadline_preserves_cursor_for_next_tick(scanner, monkeypatch):
    scan, errors = scanner
    ticks = iter([0.0, 2.0])
    with monkeypatch.context() as patcher:
        patcher.setattr(owner, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
        assert scan.scan(baseline=True) == []
    cursor = scan._cursor
    assert scan.scan() == []
    assert scan._cursor is None
    assert cursor.gi_frame is None
    assert len(scan.snapshot) == 2
    assert errors == []


def test_one_unreadable_file_does_not_hide_other_changes(
    scanner, tmp_path, monkeypatch
):
    scan, errors = scanner
    scan.scan(baseline=True)
    before = scan.snapshot[str(tmp_path / "a.py")]
    for path in tmp_path.iterdir():
        path.write_text("saved = 2\n", encoding="utf-8")
    original = scan._fingerprint

    def fingerprint(path, deadline):
        if path.endswith("a.py"):
            raise OSError("temporarily unreadable")
        return original(path, deadline)

    with monkeypatch.context() as patcher:
        patcher.setattr(scan, "_fingerprint", fingerprint)
        assert scan.scan() == [str(tmp_path / "b.py")]
    assert scan.snapshot[str(tmp_path / "a.py")] == before
    assert scan.scan() == [str(tmp_path / "a.py")]
    assert errors == ["error"]


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_unreadable_directory_only_protects_its_own_subtree(
    scanner, tmp_path, monkeypatch, change
):
    scan, errors = scanner
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "inside.py").write_text("inside = 1\n", encoding="utf-8")
    scan.scan(baseline=True)
    before = scan.snapshot[str(blocked / "inside.py")]
    path = tmp_path / "a.py"
    if change == "edit":
        path.write_text("saved = 2\n", encoding="utf-8")
    else:
        path.unlink()
    original = owner.os.scandir

    def scandir(path):
        if str(path) == str(blocked):
            raise OSError("blocked directory")
        return original(path)

    monkeypatch.setattr(owner.os, "scandir", scandir)
    assert scan.scan() == [str(path)]
    assert scan.snapshot[str(blocked / "inside.py")] == before
    assert errors == ["error"]


@pytest.mark.skipif(
    os.name == "nt",
    reason="#1405: native symlink creation needs separate Windows privileges",
)
def test_source_symlink_does_not_disable_ordinary_files(scanner, tmp_path):
    scan, errors = scanner
    (tmp_path / "link.py").symlink_to(tmp_path / "a.py")
    scan.scan(baseline=True)
    (tmp_path / "b.py").write_text("saved = 2\n", encoding="utf-8")
    assert scan.scan() == [str(tmp_path / "b.py")]
    assert sorted(scan.snapshot) == [str(tmp_path / "a.py"), str(tmp_path / "b.py")]
    assert errors == ["error", "error"]


def test_close_releases_suspended_directory_iterator(scanner, monkeypatch):
    scan, _errors = scanner
    monkeypatch.setattr(owner, "_POLL_ENTRIES", 1)
    scan.scan(baseline=True)
    cursor = scan._cursor
    scan.close()
    assert scan._cursor is None
    assert cursor.gi_frame is None


class NativeHarness:
    """使用真实普通文件描述符，独立记录目录句柄所有权。"""

    def __init__(self, fault):
        self.fault = fault
        self.directories = []
        self.files = []
        self.identity_calls = 0

    def open(self, path, directory):
        if directory:
            handle = ("directory", path)
            self.directories.append(handle)
            return handle
        handle = os.open(path, os.O_RDONLY)
        self.files.append(handle)
        return handle

    def close(self, handle):
        if isinstance(handle, tuple):
            self.directories.remove(handle)
        else:
            os.close(handle)

    def identity(self, handle):
        self.identity_calls += 1
        if self.fault == "identity":
            raise OSError("identity failed")
        return (self.identity_calls if self.fault == "changed" else 1,)

    def reader_fd(self, handle):
        if self.fault == "transfer":
            raise OSError("transfer failed")
        return handle


@pytest.mark.parametrize(
    "fault",
    ["identity", "transfer", "changed", "bytes", "deadline", "post_deadline", "read"],
)
def test_native_read_failures_release_every_owned_handle(
    scanner, tmp_path, monkeypatch, fault
):
    scan, _errors = scanner
    api = NativeHarness(fault)
    scan._native = api
    if fault == "bytes":
        monkeypatch.setattr(owner, "_FILE_BYTES", 1)
    if fault in {"deadline", "post_deadline"}:
        ticks = iter([0.0, 2.0] if fault == "deadline" else [0.0, 0.0, 0.0, 2.0])
        monkeypatch.setattr(
            owner, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
    if fault == "read":

        def fail_read(*_args):
            raise OSError("read failed")

        monkeypatch.setattr(owner.os, "read", fail_read)
    with pytest.raises(OSError):
        scan._windows_fingerprint(
            str(tmp_path / "a.py"),
            1.0 if fault in {"deadline", "post_deadline"} else float("inf"),
        )
    assert api.directories == []
    assert len(api.files) == 1
    for handle in api.files:
        with pytest.raises(OSError):
            os.fstat(handle)


def test_native_expired_deadline_opens_no_handles(scanner, tmp_path):
    scan, _errors = scanner
    api = NativeHarness("")
    scan._native = api
    with pytest.raises(OSError, match="deadline exceeded"):
        scan._windows_fingerprint(str(tmp_path / "a.py"), -1.0)
    assert api.directories == []
    assert api.files == []


def test_changed_source_capture_is_rejected(scanner, tmp_path, monkeypatch):
    from types import SimpleNamespace

    scan, _errors = scanner
    monkeypatch.setattr(owner, "os", SimpleNamespace(name="posix", path=os.path))
    monkeypatch.setattr(
        owner,
        "safe_workspace_path",
        lambda *_a, **_kw: SimpleNamespace(kind="missing", data=None),
    )
    with pytest.raises(OSError, match="source changed during capture"):
        scan._fingerprint(str(tmp_path / "a.py"), float("inf"))


def test_enumeration_failure_reports_only_the_failed_directory(tmp_path, monkeypatch):
    class BrokenDirectory:
        def __init__(self):
            self.closed = False

        def __next__(self):
            raise OSError("enumeration failed")

        def close(self):
            self.closed = True

    directory = BrokenDirectory()
    monkeypatch.setattr(owner.os, "scandir", lambda _path: directory)
    assert list(owner._entries(str(tmp_path))) == [("blocked", str(tmp_path), None)]
    assert directory.closed is True


def test_entry_stat_failure_does_not_abort_directory(tmp_path, monkeypatch):
    from types import SimpleNamespace

    class Directory:
        def __init__(self):
            self.entries = iter(
                [SimpleNamespace(path=str(tmp_path / "lost.py"), stat=self.fail)]
            )
            self.closed = False

        def fail(self, **_kwargs):
            raise OSError("entry disappeared")

        def __next__(self):
            return next(self.entries)

        def close(self):
            self.closed = True

    directory = Directory()
    monkeypatch.setattr(owner.os, "scandir", lambda _path: directory)
    assert list(owner._entries(str(tmp_path))) == [
        ("blocked", str(tmp_path / "lost.py"), None)
    ]
    assert directory.closed is True


def test_root_open_failure_is_reported_without_traversal(tmp_path, monkeypatch):
    def denied(_path):
        raise OSError("root unavailable")

    monkeypatch.setattr(owner.os, "scandir", denied)
    assert list(owner._entries(str(tmp_path))) == [("blocked", str(tmp_path), None)]


def test_unsupported_file_consumes_an_enumeration_step(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("unsupported", encoding="utf-8")
    assert list(owner._entries(str(tmp_path))) == [("skip", str(path), None)]


def test_windows_dispatch_reuses_native_api_and_reads_raw_bytes(
    scanner, tmp_path, monkeypatch
):
    import hashlib

    import tree_sitter_analyzer.index_snapshot_windows as native

    scan, _errors = scanner
    api = NativeHarness("")
    calls = []

    def create():
        calls.append("created")
        return api

    monkeypatch.setattr(native, "NativeFiles", create)
    monkeypatch.setattr(
        owner,
        "os",
        SimpleNamespace(
            name="nt", path=os.path, sep=os.sep, read=os.read, close=os.close
        ),
    )
    path = tmp_path / "a.py"
    for _ in range(2):
        assert (
            scan._fingerprint(str(path), float("inf"))[0]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )
    assert calls == ["created"]
    assert api.directories == []


def test_baseline_reset_during_pass_removes_deleted_state_without_notification(
    scanner, tmp_path, monkeypatch
):
    scan, errors = scanner
    scan.scan(baseline=True)
    (tmp_path / "a.py").unlink()
    monkeypatch.setattr(owner, "_POLL_ENTRIES", 1)
    assert scan.scan() == []
    assert scan.scan(baseline=True) == []
    assert sorted(scan.snapshot) == [str(tmp_path / "b.py")]
    assert errors == []
