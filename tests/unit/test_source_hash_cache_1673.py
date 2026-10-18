"""#1673：按 stat 证据复用源码内容摘要（``source_hash_cache``）。

每个复用键都必须真的参与判定：任一键被“强制命中”时，下面至少一个测试变红
（见 PR 的变异检查）。摘要仍按内容计算（RFC-0030）；缓存只避免为同一份字节重复
读取，并且从不只按路径判定。
"""

from __future__ import annotations

import os
import time

import pytest

from tree_sitter_analyzer import index_source_stream, source_hash_cache
from tree_sitter_analyzer.portable_source_snapshot import _marker, _same

_LATER_NS = 60_000_000_000


@pytest.fixture
def cache(monkeypatch):
    """新的空缓存；``time_ns`` 前移 60 秒，使刚写的文件不在竞争窗口内。"""
    fresh = source_hash_cache.SourceHashCache()
    monkeypatch.setattr(source_hash_cache, "SOURCE_HASHES", fresh)
    monkeypatch.setattr(
        source_hash_cache, "_now_ns", lambda: time.time_ns() + _LATER_NS
    )
    return fresh


@pytest.fixture
def reads(monkeypatch):
    """统计真正打开文件的次数。"""
    calls: list[str] = []
    original = index_source_stream._hash_source_uncached

    def counted(directory_fd, name, *args, **kwargs):
        calls.append(name)
        return original(directory_fd, name, *args, **kwargs)

    monkeypatch.setattr(index_source_stream, "_hash_source_uncached", counted)
    return calls


def _hash(path) -> str:
    before = os.lstat(path)
    _, digest, clean = index_source_stream.hash_source_at(
        None,
        str(path),
        before,
        time.monotonic() + 30,
        {"input": 0, "output": 0},
        1 << 30,
        _marker,
        _same,
    )
    assert clean is True
    return digest


def _rewrite_keeping_mtime(path, data: bytes) -> None:
    info = os.stat(path)
    path.write_bytes(data)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))


def test_unchanged_file_is_not_read_again(tmp_path, cache, reads) -> None:
    path = tmp_path / "a.py"
    path.write_bytes(b"def a():\n    return 1\n")

    first = _hash(path)
    second = _hash(path)

    assert (first == second, len(reads), cache.hits) == (True, 1, 1)


def test_same_size_and_mtime_rewrite_is_read_again(tmp_path, cache, reads) -> None:
    # 大小、mtime 都不变的改写：只有 ctime（与内容）不同，必须重新读取。
    path = tmp_path / "a.py"
    path.write_bytes(b"def a():\n    return 1\n")
    first = _hash(path)
    time.sleep(0.05)  # 让 ctime 跨过一个时间戳刻度
    _rewrite_keeping_mtime(path, b"def a():\n    return 2\n")

    second = _hash(path)

    assert (first != second, len(reads)) == (True, 2)


def test_mtime_change_is_read_again(tmp_path, cache, reads) -> None:
    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    _hash(path)
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))

    _hash(path)

    assert len(reads) == 2


def test_size_change_is_read_again(tmp_path, cache, reads) -> None:
    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    first = _hash(path)
    _rewrite_keeping_mtime(path, b"x = 1\n\n")

    second = _hash(path)

    assert (len(reads), first != second) == (2, True)


def test_replaced_file_is_read_again(tmp_path, cache, reads) -> None:
    # 原子替换（新 inode），即使大小与 mtime 相同。
    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    first = _hash(path)
    info = os.stat(path)
    other = tmp_path / "a.tmp"
    other.write_bytes(b"x = 2\n")
    os.utime(other, ns=(info.st_atime_ns, info.st_mtime_ns))
    os.replace(other, path)

    second = _hash(path)

    assert (len(reads), first != second) == (2, True)


def test_recent_file_is_never_cached(tmp_path, monkeypatch, reads) -> None:
    # 时间戳竞争窗口：mtime/ctime 距当前不足 5 秒的文件每次都重新读取。
    fresh = source_hash_cache.SourceHashCache()
    monkeypatch.setattr(source_hash_cache, "SOURCE_HASHES", fresh)
    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")

    _hash(path)
    _hash(path)

    assert (len(reads), len(fresh)) == (2, 0)


def test_unclean_read_is_not_cached(tmp_path, cache, monkeypatch) -> None:
    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    monkeypatch.setattr(
        index_source_stream,
        "_hash_source_uncached",
        lambda *_a, **_k: ("m", "<unsafe>", False),
    )
    before = os.lstat(path)
    index_source_stream.hash_source_at(
        None,
        str(path),
        before,
        time.monotonic() + 30,
        {"input": 0},
        1 << 30,
        _marker,
        _same,
    )

    key = source_hash_cache.evidence(str(path), before)
    assert (len(cache), cache.lookup(str(path), key)) == (0, None)


def test_stat_key_covers_every_identity_field() -> None:
    info = os.stat(__file__)
    assert source_hash_cache.stat_key(info, 12345) == (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        12345,
        getattr(info, "st_file_attributes", 0),
    )


def test_change_time_reflects_a_rewrite_with_restored_mtime(tmp_path) -> None:
    # Windows 路径 stat 的 st_ctime 是创建时间；变更时间必须来自 NTFS ChangeTime。
    from tree_sitter_analyzer.file_change_time import change_time_ns

    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    before = change_time_ns(str(path), os.lstat(path))
    time.sleep(0.05)
    _rewrite_keeping_mtime(path, b"x = 2\n")
    after = change_time_ns(str(path), os.lstat(path))

    assert (type(before), type(after), before != after) == (int, int, True)


def test_missing_change_time_is_never_reused(tmp_path, cache, reads, monkeypatch):
    path = tmp_path / "a.py"
    path.write_bytes(b"x = 1\n")
    monkeypatch.setattr(source_hash_cache, "change_time_ns", lambda *_a: None)

    _hash(path)
    _hash(path)

    assert (len(reads), len(cache)) == (2, 0)


def test_cache_is_bounded(monkeypatch) -> None:
    small = source_hash_cache.SourceHashCache(max_entries=2)
    info = os.stat(__file__)
    key = source_hash_cache.stat_key(info, int(info.st_mtime_ns))
    monkeypatch.setattr(
        source_hash_cache, "_now_ns", lambda: time.time_ns() + _LATER_NS
    )
    for name in ("a", "b", "c"):
        small.store(name, key, "d" * 64)

    assert (len(small), small.lookup("a", key), small.lookup("c", key)) == (
        2,
        None,
        "d" * 64,
    )
