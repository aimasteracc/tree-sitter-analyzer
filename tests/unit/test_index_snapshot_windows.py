"""Windows 原生句柄后端的 ABI 契约、故障清理和真实平台验证。"""

from __future__ import annotations

import ctypes
import errno
import os
import sqlite3
import stat
import sys
import time
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer import index_snapshot_windows as owner


class _Call:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class _Kernel:
    """用真实文件字节模拟 Kernel32 ABI；不是 Windows 原生资格证明。"""

    def __init__(self):
        self.handles = {}
        self.requests = []
        self.error = errno.EIO
        self.fail = None
        self.attributes = None
        self.file_type = 1
        self.next_directory = 1_000_000
        for name, method in (
            ("CreateFileW", self.open),
            ("GetFileInformationByHandle", self.info),
            ("GetFileInformationByHandleEx", self.identifier),
            ("CloseHandle", self.close),
            ("GetFileType", lambda _handle: self.file_type),
        ):
            setattr(self, name, _Call(method))

    def open(self, path, access, share, security, disposition, flags, template):
        self.requests.append(
            (path, access, share, security, disposition, flags, template)
        )
        if self.fail == "open":
            return ctypes.c_void_p(-1).value
        try:
            info = os.lstat(path)
            directory = stat.S_ISDIR(info.st_mode)
            if directory:
                handle = self.next_directory
                self.next_directory += 1
            else:
                handle = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            self.handles[handle] = (path, directory, info)
            return handle
        except OSError as exc:
            self.error = exc.errno
            return ctypes.c_void_p(-1).value

    def metadata(self, handle):
        path, directory, opened = self.handles[handle]
        return opened if directory else os.fstat(handle)

    def info(self, handle, pointer):
        if self.fail == "info":
            return 0
        info = self.metadata(handle)
        target = pointer._obj
        target.attributes = (
            (0x10 if stat.S_ISDIR(info.st_mode) else 0)
            if self.attributes is None
            else self.attributes
        )
        target.size_high, target.size_low = (
            info.st_size >> 32,
            info.st_size & 0xFFFFFFFF,
        )
        target.written[:] = (info.st_mtime_ns & 0xFFFFFFFF, info.st_mtime_ns >> 32)
        target.created[:] = (info.st_ctime_ns & 0xFFFFFFFF, info.st_ctime_ns >> 32)
        return 1

    def identifier(self, handle, kind, pointer, size):
        assert (kind, size) == (18, 24)
        if self.fail == "identifier":
            return 0
        info = self.metadata(handle)
        pointer._obj.volume = info.st_dev
        pointer._obj.identifier[:] = info.st_ino.to_bytes(16, "little")
        return 1

    def close(self, handle):
        _, directory, _ = self.handles.pop(handle)
        if not directory:
            os.close(handle)
        return 0 if self.fail == "close" else 1


@pytest.fixture
def kernel(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_capability as capability

    kernel = _Kernel()
    monkeypatch.setattr(capability, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))
    monkeypatch.setattr(capability, "_WINDOWS_WAL_SUPPORTED", True)
    monkeypatch.setattr(capability, "_WAL_FD_COPY_SUPPORTED", True)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_k: kernel, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: kernel.error, raising=False)
    monkeypatch.setattr(
        ctypes, "WinError", lambda code: OSError(code, "native failure"), raising=False
    )
    monkeypatch.setattr(os, "O_BINARY", getattr(os, "O_BINARY", 0), raising=False)
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(open_osfhandle=lambda handle, _flags: handle),
    )
    return kernel


@pytest.fixture
def pair(tmp_path):
    directory = tmp_path / ".ast-cache"
    directory.mkdir()
    path = directory / "index.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE payload(value)")
    conn.execute("INSERT INTO payload VALUES(42)")
    conn.commit()
    yield path, conn
    conn.close()


def _capture(root, *, byte_limit=1024 * 1024):
    from tree_sitter_analyzer.index_snapshot_capability import private_wal_database

    def check(deadline):
        if time.monotonic() >= deadline:
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    return private_wal_database(
        str(root),
        deadline=time.monotonic() + 5,
        byte_limit=byte_limit,
        check_deadline=check,
    )


def test_native_abi_preserves_full_identity_and_read_only_flags(tmp_path, kernel):
    path = tmp_path / "db"
    path.write_bytes(b"contents")
    api = owner.NativeFiles()
    handle = api.open(str(path), False)
    try:
        identity = api.identity(handle)
        info = path.stat()
        assert identity[:3] == (info.st_dev, info.st_ino.to_bytes(16, "little"), 8)
        assert kernel.requests == [
            (str(path), 0x80000000, 3, None, 3, 0x02200000, None)
        ]
        assert (ctypes.sizeof(owner._FileInfo), ctypes.sizeof(owner._FileId)) == (
            52,
            24,
        )
    finally:
        api.close(handle)
    assert kernel.handles == {}


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("info", OSError),
        ("reparse", ValueError),
        ("directory", ValueError),
        ("device", ValueError),
    ],
)
def test_rejected_native_handle_is_closed(tmp_path, kernel, fault, expected):
    path = tmp_path / "db"
    path.write_bytes(b"x")
    kernel.fail = "info" if fault == "info" else None
    kernel.attributes = {"reparse": 0x400, "directory": 0x10}.get(fault)
    kernel.file_type = 2 if fault == "device" else 1
    with pytest.raises(expected) as error:
        owner.NativeFiles().open(str(path), False)
    if fault == "info":
        assert error.value.errno == errno.EIO
    else:
        assert str(error.value) == (
            "INDEX_PATH_SYMLINK" if fault == "reparse" else "INDEX_PATH_UNSAFE"
        )
    assert kernel.handles == {}


@pytest.mark.parametrize("recycled", [False, True])
def test_wal_copy_recovers_committed_rows_and_closes_pins(
    tmp_path, pair, kernel, recycled
):
    # 2026-09-08：Windows 能力路径也必须识别真实 SQLite 重用后的当前代帧数。
    if recycled:
        path, writer = pair
        before = path.with_name("index.db-wal").read_bytes()
        assert writer.execute("PRAGMA wal_checkpoint(RESTART)").fetchone() == (0, 3, 3)
        writer.execute("UPDATE payload SET value=43")
        writer.commit()
        assert path.with_name("index.db-wal").stat().st_size == len(before)
    with _capture(tmp_path) as (private, frames):
        assert frames == (1 if recycled else 3)
        conn = sqlite3.connect(private)
        try:
            assert conn.execute("SELECT value FROM payload").fetchall() == [
                (43 if recycled else 42,)
            ]
        finally:
            conn.close()
    assert os.path.exists(private) is False
    for handle, (_, directory, _) in kernel.handles.items():
        assert directory is False
        with pytest.raises(OSError):
            os.fstat(handle)


@pytest.mark.parametrize("fault", ["write", "new_wal", "journal", "replace"])
def test_source_mutation_cannot_publish_snapshot(tmp_path, pair, kernel, fault):
    path, writer = pair
    if fault in ("new_wal", "replace"):
        writer.close()
    expected = PermissionError if os.name == "nt" and fault == "replace" else ValueError
    with pytest.raises(expected) as error:
        with _capture(tmp_path):
            if fault == "write":
                writer.execute("INSERT INTO payload VALUES(43)")
                writer.commit()
            elif fault == "new_wal":
                path.with_name("index.db-wal").write_bytes(b"new")
            elif fault == "journal":
                path.with_name("index.db-journal").write_bytes(b"journal")
            else:
                replacement = path.with_name("replacement")
                replacement.write_bytes(path.read_bytes())
                os.replace(replacement, path)
    if expected is ValueError:
        assert str(error.value) == "CONCURRENT_WRITER"


@pytest.mark.parametrize("missing", ["root", "cache", "database"])
def test_missing_native_hierarchy_is_classified(tmp_path, kernel, missing):
    root = tmp_path / "project"
    if missing != "root":
        root.mkdir()
    if missing == "database":
        (root / ".ast-cache").mkdir()
    expected = "MISSING_PROJECT_ROOT" if missing == "root" else "MISSING_INDEX"
    with pytest.raises(FileNotFoundError, match=f"^{expected}$"):
        with _capture(root):
            pytest.fail("缺失层级不能发布快照")
    assert kernel.handles == {}


@pytest.mark.parametrize("fault", ["identifier", "descriptor", "close"])
def test_native_handle_failure_releases_owned_resources(
    tmp_path, pair, kernel, monkeypatch, fault
):
    if fault == "descriptor":
        monkeypatch.setattr(
            sys.modules["msvcrt"],
            "open_osfhandle",
            lambda *_a: (_ for _ in ()).throw(OSError("descriptor failed")),
        )
    else:
        kernel.fail = fault
    with pytest.raises(OSError):
        with _capture(tmp_path):
            pytest.fail("句柄失败不能发布快照")
    for handle, (_, directory, _) in kernel.handles.items():
        assert directory is False
        with pytest.raises(OSError) as error:
            os.fstat(handle)
        assert error.value.errno == errno.EBADF


def test_native_copy_budget_rejects_before_publication(tmp_path, pair, kernel):
    with pytest.raises(RuntimeError, match="^INDEX_BACKUP_BUDGET$"):
        with _capture(tmp_path, byte_limit=1):
            pytest.fail("超预算不能复制")


def test_native_private_copy_accepts_external_volume(
    tmp_path, pair, kernel, monkeypatch
):
    import tree_sitter_analyzer.index_snapshot_capability as capability

    def different_volumes(_paths):
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(
        capability.os,
        "path",
        SimpleNamespace(**{**vars(os.path), "commonpath": different_volumes}),
    )
    with _capture(tmp_path) as (private, frames):
        assert frames == 3
        assert os.path.isfile(private) is True
    assert os.path.exists(private) is False


@pytest.mark.parametrize("wal", [b"", b"invalid"])
def test_native_empty_or_malformed_wal(tmp_path, pair, kernel, wal):
    path, conn = pair
    conn.close()
    path.with_name("index.db-wal").write_bytes(wal)
    if wal:
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            with _capture(tmp_path):
                pytest.fail("损坏 WAL 不能恢复")
    else:
        with _capture(tmp_path) as (_private, frames):
            assert frames == 0


def test_native_path_disappearing_during_verification_is_rejected(
    tmp_path, pair, kernel, monkeypatch
):
    native_open = owner.NativeFiles.open
    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with _capture(tmp_path):
            monkeypatch.setattr(
                owner.NativeFiles,
                "open",
                lambda *_a: (_ for _ in ()).throw(FileNotFoundError("gone")),
            )
    monkeypatch.setattr(owner.NativeFiles, "open", native_open)


@pytest.mark.skipif(os.name != "nt", reason="PR #1404: 原生 Windows 句柄契约")
def test_real_windows_wal_capture(tmp_path, pair):
    with _capture(tmp_path) as (private, _frames):
        conn = sqlite3.connect(private)
        try:
            assert conn.execute("SELECT value FROM payload").fetchall() == [(42,)]
        finally:
            conn.close()
    assert os.path.exists(private) is False
    pair[1].close()
    pair[0].unlink()
    pair[0].parent.rename(tmp_path / "released-cache")


@pytest.mark.skipif(os.name != "nt", reason="PR #1404: 原生 Windows 并发与层级保护")
@pytest.mark.parametrize(
    "fault", ["write", "database_replace", "cache_replace", "root_replace"]
)
def test_real_windows_mutation_is_rejected(tmp_path, pair, fault):
    path, conn = pair
    if fault == "write":
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            with _capture(tmp_path):
                conn.execute("INSERT INTO payload VALUES(43)")
                conn.commit()
    else:
        with _capture(tmp_path):
            with pytest.raises(PermissionError):
                if fault == "cache_replace":
                    path.parent.rename(tmp_path / "old-cache")
                elif fault == "root_replace":
                    tmp_path.rename(tmp_path.with_name(tmp_path.name + "-moved"))
                else:
                    replacement = tmp_path / "replacement"
                    replacement.write_bytes(path.read_bytes())
                    os.replace(replacement, path)


@pytest.mark.skipif(os.name != "nt", reason="PR #1404: 原生 Windows 重解析点")
def test_real_windows_cache_junction_is_rejected(tmp_path, pair):
    import subprocess

    path, conn = pair
    conn.close()
    target = tmp_path / "actual-cache"
    path.parent.rename(target)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(path.parent), str(target)],
        check=True,
        capture_output=True,
    )
    try:
        with pytest.raises(ValueError, match="^INDEX_PATH_SYMLINK$"):
            with _capture(tmp_path):
                pytest.fail("目录联接不能作为固定缓存层级")
    finally:
        os.rmdir(path.parent)


@pytest.mark.skipif(os.name != "nt", reason="PR #1404: 原生 Windows 同大小字节复核")
def test_real_windows_same_size_change_rejects_restored_mtime(tmp_path, pair):
    path, conn = pair
    conn.close()
    before = path.stat()
    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with _capture(tmp_path):
            with path.open("r+b") as changed:
                changed.seek(-1, os.SEEK_END)
                value = changed.read(1)[0]
                changed.seek(-1, os.SEEK_END)
                changed.write(bytes([value ^ 1]))
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


@pytest.mark.skipif(os.name != "nt", reason="PR #1404: 原生 Windows 预算与 sidecar")
@pytest.mark.parametrize("fault", ["budget", "journal", "new_wal"])
def test_real_windows_budget_and_sidecar_rejection(tmp_path, pair, fault):
    path, conn = pair
    if fault == "budget":
        with pytest.raises(RuntimeError, match="^INDEX_BACKUP_BUDGET$"):
            with _capture(tmp_path, byte_limit=1):
                pytest.fail("超预算不能发布")
    else:
        conn.close()
        suffix = "journal" if fault == "journal" else "wal"
        with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
            with _capture(tmp_path):
                path.with_name("index.db-" + suffix).write_bytes(b"changed")


def test_native_pins_reject_new_generation_publication(tmp_path, pair, kernel):
    from tree_sitter_analyzer.cache.generation_indexing import project_store
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    (tmp_path / "a.py").write_text("def saved(): return 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with _capture(tmp_path):
            project_store(str(tmp_path), make_source_scope_descriptor()).sync()


def test_native_workspace_reader_pins_hierarchy_and_releases_handles(tmp_path, kernel):
    # PR #1491：Windows 正文读取复用原生 File ID 能力，不能退化成普通 pathname open。
    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "sample.py"
    source.write_bytes(b"value = 1\n")

    data, metadata = owner.read_pinned_workspace_file(
        str(tmp_path),
        "pkg/sample.py",
        deadline=time.monotonic() + 5,
        limit=1024,
    )

    assert data == b"value = 1\n"
    assert len(metadata) == 3
    assert all(isinstance(item, bytes) for item in metadata)
    assert kernel.handles
    for handle, (_path, directory, _info) in kernel.handles.items():
        assert directory is False
        with pytest.raises(OSError) as error:
            os.fstat(handle)
        assert error.value.errno == errno.EBADF


def test_native_workspace_reader_enforces_deadline_and_byte_budget(tmp_path, kernel):
    # PR #1491：源码句柄读取与数据库读取共享同一个绝对 deadline 和请求预算。
    source = tmp_path / "sample.py"
    source.write_bytes(b"abcdef")

    with pytest.raises(TimeoutError, match="INDEX_SNAPSHOT_DEADLINE"):
        owner.read_pinned_workspace_file(
            str(tmp_path), "sample.py", deadline=0.0, limit=1024
        )
    with pytest.raises(OverflowError, match="INDEX_SOURCE_CAPACITY"):
        owner.read_pinned_workspace_file(
            str(tmp_path),
            "sample.py",
            deadline=time.monotonic() + 5,
            limit=1,
        )


def test_native_workspace_reader_rejects_change_after_read(
    tmp_path, kernel, monkeypatch
):
    # PR #1491：读取后必须重新验证固定句柄与 pathname，不能发布漂移期间的字节。
    source = tmp_path / "sample.py"
    source.write_bytes(b"before\n")
    real_read = owner._read_descriptor
    changed = False

    def read_then_change(fd, size):
        nonlocal changed
        data = real_read(fd, size)
        if data and not changed:
            changed = True
            source.write_bytes(b"after-content\n")
        return data

    monkeypatch.setattr(owner, "_read_descriptor", read_then_change)
    with pytest.raises(ValueError, match="INDEX_SOURCE_CHANGED"):
        owner.read_pinned_workspace_file(
            str(tmp_path),
            "sample.py",
            deadline=time.monotonic() + 5,
            limit=1024,
        )


@pytest.mark.parametrize(
    ("relative_path", "limit"),
    [
        ("", 1),
        ("/absolute.py", 1),
        ("../escape.py", 1),
        ("C:/drive.py", 1),
        ("a.py", -1),
    ],
)
def test_native_workspace_reader_rejects_unsafe_paths(
    tmp_path, kernel, relative_path, limit
):
    """Windows 原生读取器必须在打开句柄前拒绝不安全路径。"""
    with pytest.raises(ValueError, match="^INDEX_PATH_UNSAFE$"):
        owner.read_pinned_workspace_file(
            str(tmp_path),
            relative_path,
            deadline=time.monotonic() + 5,
            limit=limit,
        )
    assert kernel.handles == {}


def test_native_workspace_reader_closes_handle_when_fd_adoption_fails(
    tmp_path, kernel, monkeypatch
):
    """CRT 接管失败时也必须关闭刚打开的原生文件句柄。"""
    source = tmp_path / "sample.py"
    source.write_bytes(b"value = 1\n")
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(
            open_osfhandle=lambda *_args: (_ for _ in ()).throw(
                OSError("descriptor adoption failed")
            )
        ),
    )

    with pytest.raises(OSError, match="descriptor adoption failed"):
        owner.read_pinned_workspace_file(
            str(tmp_path),
            "sample.py",
            deadline=time.monotonic() + 5,
            limit=1024,
        )
    assert kernel.handles == {}


def test_native_workspace_reader_translates_reopen_failure(
    tmp_path, kernel, monkeypatch
):
    """读取后 pathname 无法重开时必须报告源码变化并清理全部句柄。"""
    source = tmp_path / "sample.py"
    source.write_bytes(b"value = 1\n")
    real_read = owner._read_descriptor

    def read_then_reject_reopen(fd, size):
        data = real_read(fd, size)
        if data:
            kernel.fail = "open"
        return data

    monkeypatch.setattr(owner, "_read_descriptor", read_then_reject_reopen)
    with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
        owner.read_pinned_workspace_file(
            str(tmp_path),
            "sample.py",
            deadline=time.monotonic() + 5,
            limit=1024,
        )
    for handle, (_path, directory, _info) in kernel.handles.items():
        assert directory is False
        with pytest.raises(OSError) as error:
            os.fstat(handle)
        assert error.value.errno == errno.EBADF


def _populate(tmp_path, count):
    package = tmp_path / "pkg"
    package.mkdir()
    for number in range(count):
        (package / f"m{number}.py").write_bytes(f"value = {number}\n".encode())
    return [f"pkg/m{number}.py" for number in range(count)]


def test_batch_reader_opens_each_directory_once_per_scan(tmp_path, kernel):
    # #1783 root cause: the per-file reader reopened and re-verified the whole
    # ancestor chain for every file (2*(depth+2) CreateFileW each).  On Windows
    # with on-access scanning that made a 553-file scan exceed the 5 s budget.
    paths = _populate(tmp_path, 10)

    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        data = [reader.read(path, limit=1024)[0] for path in paths]
        reads = list(kernel.requests)
        reader.verify()

    assert data == [f"value = {number}\n".encode() for number in range(10)]
    directory_opens = [request for request in reads if request[1] == 0x80]
    file_opens = [request for request in reads if request[1] == 0x80000000]
    # root + pkg pinned once for the whole scan; each file opened + reopened once.
    assert len(directory_opens) == 2
    assert len(file_opens) == 2 * len(paths)
    # The per-file reader needs 3x as many opens for the same work.
    kernel.requests.clear()
    for path in paths:
        owner.read_pinned_workspace_file(
            str(tmp_path), path, deadline=time.monotonic() + 5, limit=1024
        )
    assert len(kernel.requests) == 6 * len(paths)


def test_batch_reader_releases_every_directory_handle(tmp_path, kernel):
    paths = _populate(tmp_path, 3)

    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(paths[0], limit=1024)

    assert all(directory is False for _p, directory, _i in kernel.handles.values())
    with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
        reader.read(paths[1], limit=1024)


def test_batch_reader_rejects_file_change_during_read(tmp_path, kernel, monkeypatch):
    (source,) = _populate(tmp_path, 1)
    real_read = owner._read_descriptor

    def read_then_change(fd, size):
        data = real_read(fd, size)
        if data:
            (tmp_path / source).write_bytes(b"after-content-is-longer\n")
        return data

    monkeypatch.setattr(owner, "_read_descriptor", read_then_change)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
            reader.read(source, limit=1024)


def test_batch_reader_verify_rejects_replaced_directory(tmp_path, kernel):
    # Directory identities are proven once at the end of the scan; a swapped
    # directory must still fail the whole scan closed.
    paths = _populate(tmp_path, 2)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(paths[0], limit=1024)
        (tmp_path / "pkg").rename(tmp_path / "old-pkg")
        (tmp_path / "pkg").mkdir()
        with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
            reader.verify()


def test_batch_reader_enforces_deadline_budget_and_paths(tmp_path, kernel):
    (source,) = _populate(tmp_path, 1)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        with pytest.raises(OverflowError, match="INDEX_SOURCE_CAPACITY"):
            reader.read(source, limit=1)
        with pytest.raises(ValueError, match="^INDEX_PATH_UNSAFE$"):
            reader.read("../escape.py", limit=1024)
        with pytest.raises(FileNotFoundError):
            reader.read("pkg/missing.py", limit=1024)
    with pytest.raises(TimeoutError, match="INDEX_SNAPSHOT_DEADLINE"):
        owner.PinnedWorkspaceReader(str(tmp_path), deadline=0.0)


def test_batch_reader_is_safe_under_concurrent_reads(tmp_path, kernel):
    from concurrent.futures import ThreadPoolExecutor

    paths = _populate(tmp_path, 24)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        with ThreadPoolExecutor(max_workers=8) as pool:
            data = list(pool.map(lambda path: reader.read(path, limit=1024)[0], paths))
        reader.verify()

    assert data == [f"value = {number}\n".encode() for number in range(24)]
    assert len([r for r in kernel.requests if r[1] == 0x80]) == 2 + 2  # pin + verify


@pytest.fixture
def windows_oracle(kernel, monkeypatch):
    from tree_sitter_analyzer import source_oracle

    monkeypatch.setattr(source_oracle, "_supports_nofollow", lambda: False)
    monkeypatch.setattr(
        source_oracle, "os", SimpleNamespace(**{**vars(os), "name": "nt"})
    )
    return source_oracle


def test_source_batch_reader_maps_windows_reader_outcomes(tmp_path, windows_oracle):
    (source,) = _populate(tmp_path, 1)
    oracle = windows_oracle

    with oracle.SourceBatchReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        captured = reader.read(source, limit=1024)
        missing = reader.read("pkg/absent.py", limit=1024)
        with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
            reader.read(source, limit=1)
        reader.verify()

    assert (captured.kind, captured.data) == ("file", b"value = 0\n")
    assert len(captured.metadata) == 3
    assert missing.kind == "missing"


def test_source_batch_reader_verify_maps_directory_drift(tmp_path, windows_oracle):
    (source,) = _populate(tmp_path, 1)
    oracle = windows_oracle
    with oracle.SourceBatchReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(source, limit=1024)
        (tmp_path / "pkg").rename(tmp_path / "moved")
        (tmp_path / "pkg").mkdir()
        with pytest.raises(
            oracle.SourceOracleError, match="^DIFF_SNAPSHOT_SOURCE_CHANGED$"
        ):
            reader.verify()


def test_source_batch_reader_maps_construction_failures(
    tmp_path, windows_oracle, kernel
):
    oracle = windows_oracle
    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_TIMEOUT$"):
        oracle.SourceBatchReader(str(tmp_path), deadline=0.0)
    kernel.fail = "open"
    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_PATH$"):
        oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)


def test_source_batch_reader_close_failure_surfaces_only_on_success(
    tmp_path, windows_oracle, kernel
):
    oracle = windows_oracle
    reader = oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)
    kernel.fail = "close"
    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_PATH$"):
        with reader:
            pass
    kernel.fail = None
    reader = oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)
    kernel.fail = "close"
    with pytest.raises(KeyError, match="original"):
        with reader:
            raise KeyError("original")


def test_source_batch_reader_rejects_unsupported_platforms(tmp_path, monkeypatch):
    from tree_sitter_analyzer import source_oracle

    monkeypatch.setattr(source_oracle, "_supports_nofollow", lambda: False)
    monkeypatch.setattr(
        source_oracle, "os", SimpleNamespace(**{**vars(os), "name": "java"})
    )
    with pytest.raises(
        source_oracle.SourceOracleError, match="^DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED$"
    ):
        source_oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)


def test_batch_reader_releases_handle_when_identity_fails(tmp_path, kernel):
    paths = _populate(tmp_path, 1)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        kernel.fail = "identifier"
        with pytest.raises(OSError):
            reader.read(paths[0], limit=1024)
        kernel.fail = None
    assert all(directory is False for _p, directory, _i in kernel.handles.values())
    kernel.fail = "identifier"
    with pytest.raises(OSError):
        owner.PinnedWorkspaceReader(str(tmp_path), deadline=time.monotonic() + 5)
    assert all(directory is False for _p, directory, _i in kernel.handles.values())


def test_batch_reader_close_reports_failure_after_releasing_all(tmp_path, kernel):
    paths = _populate(tmp_path, 1)
    reader = owner.PinnedWorkspaceReader(str(tmp_path), deadline=time.monotonic() + 5)
    reader.read(paths[0], limit=1024)
    kernel.fail = "close"
    with pytest.raises(OSError):
        reader.close()
    assert all(directory is False for _p, directory, _i in kernel.handles.values())


def test_batch_reader_verify_maps_reopen_failure(tmp_path, kernel):
    paths = _populate(tmp_path, 1)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(paths[0], limit=1024)
        kernel.fail = "open"
        with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
            reader.verify()
        kernel.fail = None
