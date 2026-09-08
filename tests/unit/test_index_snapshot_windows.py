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


def test_wal_copy_recovers_committed_rows_and_closes_pins(tmp_path, pair, kernel):
    with _capture(tmp_path) as (private, frames):
        assert frames == 3
        conn = sqlite3.connect(private)
        try:
            assert conn.execute("SELECT value FROM payload").fetchall() == [(42,)]
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
