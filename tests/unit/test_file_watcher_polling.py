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
    original = owner._open_directory

    def open_directory(root, path, *args):
        if str(path) == str(blocked):
            raise OSError("blocked directory")
        return original(root, path, *args)

    monkeypatch.setattr(owner, "_open_directory", open_directory)
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
        # #1405：模拟原生 reader_fd 的二进制模式，不能让 CRT 改写 CRLF。
        handle = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
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
                [
                    SimpleNamespace(
                        name="lost.py", path=str(tmp_path / "lost.py"), stat=self.fail
                    )
                ]
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
    path.write_bytes(b"a = 1\r\n# \x1a\xe9\r\n")
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


@pytest.mark.skipif(os.name == "nt", reason="tracked: #1405 POSIX 特殊文件替换验证")
@pytest.mark.parametrize("replacement", ["symlink", "fifo"])
def test_unsafe_source_replacement_emits_removal_once(scanner, tmp_path, replacement):
    # #1405：失去普通文件身份必须通知失效，不能无限保留旧指纹。
    scan, errors = scanner
    scan.scan(baseline=True)
    path = tmp_path / "a.py"
    path.unlink()
    if replacement == "symlink":
        path.symlink_to(tmp_path / "b.py")
    else:
        os.mkfifo(path)
    assert scan.scan() == [str(path)]
    assert sorted(scan.snapshot) == [str(tmp_path / "b.py")]
    assert scan.scan() == []
    assert errors == ["error", "error"]


@pytest.mark.parametrize("size,attrs", [(0, 0x400), (64 * 1024 * 1024 + 1, 0)])
def test_rejected_source_removal(scanner, tmp_path, monkeypatch, size, attrs):
    # #1405：reparse 和超过容量的源码都必须撤销旧指纹，且只通知一次。
    scan, errors = scanner
    scan.scan(baseline=True)
    path = str(tmp_path / "a.py")
    info = SimpleNamespace(
        st_mode=owner.stat.S_IFREG, st_file_attributes=attrs, st_size=size
    )
    entries = [
        ("file", path, info),
        ("file", str(tmp_path / "b.py"), (tmp_path / "b.py").stat()),
    ]
    monkeypatch.setattr(owner, "_entries", lambda _root: iter(entries))
    monkeypatch.setattr(
        owner.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400, raising=False
    )
    assert scan.scan() == [path]
    assert sorted(scan.snapshot) == [str(tmp_path / "b.py")]
    assert scan.scan() == []
    assert errors == ["error", "error"]


@pytest.mark.skipif(os.name != "posix", reason="tracked: #1405 POSIX 目录替换竞态")
@pytest.mark.parametrize("replacement", ["symlink", "directory"])
def test_directory_replacement_before_descent_is_not_enumerated(
    tmp_path, monkeypatch, replacement
):
    # #1405：在 stat 与打开之间替换目录，不能枚举新目标的名称。
    root = tmp_path / "project"
    child = root / "child"
    child.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_bytes(b"secret = 1\n")
    original = os.scandir
    replaced = []

    class Scanner:
        def __init__(self, path):
            self.inner = original(path)

        def __next__(self):
            entry = next(self.inner)

            def entry_stat(**kwargs):
                info = entry.stat(**kwargs)
                if entry.name == "child" and not replaced:
                    child.rename(tmp_path / "saved")
                    if replacement == "symlink":
                        child.symlink_to(outside, target_is_directory=True)
                    else:
                        outside.rename(child)
                    replaced.append(True)
                return info

            return SimpleNamespace(name=entry.name, path=entry.path, stat=entry_stat)

        def close(self):
            self.inner.close()

    monkeypatch.setattr(owner.os, "scandir", Scanner)
    assert list(owner._entries(str(root))) == [("blocked", str(child), None)]
    assert replaced == [True]


@pytest.mark.parametrize("reject_child", [False, True])
def test_windows_directory_pins_are_released_before_iteration(
    tmp_path, monkeypatch, reject_child
):
    # #1405：创建枚举器时固定全部祖先，成功或拒绝后均释放临时句柄。
    import tree_sitter_analyzer.index_snapshot_windows as native

    child = tmp_path / "child"
    child.mkdir()
    api = NativeHarness("")
    original_open = api.open
    original_scan = os.scandir
    observed = []

    def open_directory(path, directory):
        if reject_child and path == str(child):
            raise ValueError("INDEX_PATH_SYMLINK")
        return original_open(path, directory)

    def scandir(path):
        observed.append([entry[1] for entry in api.directories])
        return original_scan(path)

    monkeypatch.setattr(api, "open", open_directory)
    monkeypatch.setattr(native, "NativeFiles", lambda: api)
    monkeypatch.setattr(owner.os, "scandir", scandir)
    if reject_child:
        with pytest.raises(ValueError, match="INDEX_PATH_SYMLINK"):
            owner._open_windows_directory(str(tmp_path), str(child))
        assert observed == []
    else:
        with owner._open_windows_directory(str(tmp_path), str(child)) as entries:
            assert observed == [[str(tmp_path), str(child)]]
            assert list(entries) == []
    assert api.directories == []


@pytest.mark.skipif(os.name != "nt", reason="tracked: #1405 Windows 搜索句柄原生验证")
def test_windows_search_handle_survives_directory_replacement(tmp_path):
    # #1405：枚举间隔允许重命名，随后迭代仍只读取已打开目录。
    child = tmp_path / "child"
    child.mkdir()
    (child / "original.py").write_bytes(b"original = 1\n")
    entries = owner._open_windows_directory(str(tmp_path), str(child))
    try:
        child.rename(tmp_path / "saved")
        child.mkdir()
        (child / "replacement.py").write_bytes(b"replacement = 1\n")
        assert [entry.name for entry in entries] == ["original.py"]
    finally:
        entries.close()


def test_windows_directory_dispatch_does_not_use_posix_flags(monkeypatch):
    # #1405：Windows 必须经过原生目录固定路径，不能尝试 POSIX 描述符 API。
    calls = []
    marker = SimpleNamespace(close=lambda: calls.append("closed"))

    def open_directory(root, path):
        calls.append((root, path))
        return marker

    monkeypatch.setattr(owner, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(owner, "_open_windows_directory", open_directory)
    assert owner._open_directory("root", "root/child") == (marker, None)
    owner._close_directory(marker, None)
    assert calls == [("root", "root/child"), "closed"]
