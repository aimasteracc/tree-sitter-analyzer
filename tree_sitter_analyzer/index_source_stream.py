"""Bounded streaming source normalization for snapshot certification."""

from __future__ import annotations

import codecs
import hashlib
import os
import stat
import time
from typing import Any

# #1654: content-hash marker for a source that could not be opened or read
# (on Windows, a file another process holds locked). It is never a digest, so it
# never matches an indexed row; the reason follows the prefix.
_UNREADABLE_PREFIX = "<unreadable>"


class SourceUnreadable(OSError):
    """``hash_source_at`` could not open or read the file; ``reason`` says why."""

    def __init__(self, cause: OSError) -> None:
        reason = f"source unreadable: {type(cause).__name__}"
        if cause.errno is not None:
            reason += f" [Errno {cause.errno}]"
        if cause.strerror:
            reason += f" {cause.strerror}"
        super().__init__(cause.errno, reason)
        self.reason = reason

    @property
    def marker(self) -> str:
        """The content-hash value that records this failure in a snapshot."""
        return _UNREADABLE_PREFIX + self.reason


def unreadable_source_reason(content_hash: str) -> str | None:
    """Return the failure reason when ``content_hash`` is an unreadable marker."""
    if content_hash.startswith(_UNREADABLE_PREFIX):
        return content_hash[len(_UNREADABLE_PREFIX) :]
    return None


def opened_entry_matches(before: os.stat_result, opened: os.stat_result) -> bool:
    """Bind an opened descriptor to the exact enumerated directory entry."""
    return (before.st_dev, before.st_ino, before.st_mode) == (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
    )


def hash_source_at(
    directory_fd: int | None,
    name: str,
    before: os.stat_result,
    deadline: float,
    counters: dict[str, int],
    byte_budget: int,
    metadata_marker: Any,
    same_file_metadata: Any,
) -> tuple[str, str, bool]:
    """从同一句柄有界读取，并按索引写入端的统一解码规则计算摘要。

    文件已不存在时返回 ``<unsafe>``（源码变化）；其他打开或读取失败（如 Windows
    上被其他进程锁定）抛出 ``SourceUnreadable``，由调用方按文件记录（#1654）。

    #1673：按路径读取（``directory_fd is None``）时，``before``（调用方刚取得的
    ``lstat``）加元数据变更时间与上次干净读取的证据完全相同、且不在时间戳竞争
    窗口内，则复用那次读取的摘要而不重新打开文件（``source_hash_cache``）。
    描述符绑定的读取不经缓存。
    """
    if directory_fd is None:
        from . import source_hash_cache

        cache = source_hash_cache.SOURCE_HASHES
        key = source_hash_cache.evidence(name, before)
        cached = cache.lookup(name, key)
        if cached is not None:
            return metadata_marker(before), cached, True
        marker, digest, clean = _hash_source_uncached(
            None,
            name,
            before,
            deadline,
            counters,
            byte_budget,
            metadata_marker,
            same_file_metadata,
        )
        if clean and digest != "<unsafe>":
            cache.store(name, key, digest)
        else:
            cache.forget(name)
        return marker, digest, clean
    return _hash_source_uncached(
        directory_fd,
        name,
        before,
        deadline,
        counters,
        byte_budget,
        metadata_marker,
        same_file_metadata,
    )


def _hash_source_uncached(
    directory_fd: int | None,
    name: str,
    before: os.stat_result,
    deadline: float,
    counters: dict[str, int],
    byte_budget: int,
    metadata_marker: Any,
    same_file_metadata: Any,
) -> tuple[str, str, bool]:
    """``hash_source_at`` 的实际读取：每次都打开文件。"""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = (
            os.open(name, flags)
            if directory_fd is None
            else os.open(name, flags, dir_fd=directory_fd)
        )
    except FileNotFoundError:
        return metadata_marker(before), "<unsafe>", False
    except OSError as exc:
        raise SourceUnreadable(exc) from exc
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending_cr = False
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or not opened_entry_matches(before, opened):
            return metadata_marker(opened), "<unsafe>", False
        try:
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                counters["input"] += len(chunk)
                if counters["input"] > byte_budget:
                    raise OverflowError
                if time.monotonic() > deadline:
                    raise TimeoutError
                decoded = decoder.decode(chunk, final=False)
                pending_cr = _hash_normalized_chunk(
                    digest, decoded, pending_cr, deadline, counters, byte_budget
                )
            decoded = decoder.decode(b"", final=True)
            _hash_normalized_chunk(
                digest, decoded, pending_cr, deadline, counters, byte_budget
            )
        except UnicodeDecodeError:
            digest = _hash_detected_source(fd, deadline, counters, byte_budget)
        after = os.fstat(fd)
    except TimeoutError:
        raise  # 预算耗尽（OSError 子类）不是读失败，由调用方类型化。
    except OSError as exc:
        raise SourceUnreadable(exc) from exc
    finally:
        os.close(fd)
    # 摘要绑定同一句柄读前后的完整元数据，后续路径稳定不能洗白读取变化。
    clean = same_file_metadata(opened, after)
    if os.name == "nt":
        # #1356：Windows 3.13 的路径/句柄 ctime 不可直接比较；其余前置字段保留。
        fields = ("st_size", "st_mtime_ns", "st_file_attributes")
        clean = clean and all(
            getattr(before, field, 0) == getattr(opened, field, 0) for field in fields
        )
    else:
        clean = clean and same_file_metadata(before, opened)
    return (
        metadata_marker(after),
        digest.hexdigest() if clean else "<unsafe>",
        clean,
    )


def hash_source_or_unsafe(
    directory_fd: int | None,
    name: str,
    before: os.stat_result,
    deadline: float,
    counters: dict[str, int],
    byte_budget: int,
    metadata_marker: Any,
    same_file_metadata: Any,
) -> tuple[str, str, bool]:
    """``hash_source_at`` for certification scans: an unreadable file is unsafe.

    A file that cannot be certified must never count as clean; these scans
    record it as ``<unsafe>``, exactly as a failed open always was.
    """
    try:
        return hash_source_at(
            directory_fd,
            name,
            before,
            deadline,
            counters,
            byte_budget,
            metadata_marker,
            same_file_metadata,
        )
    except SourceUnreadable:
        return metadata_marker(before), "<unsafe>", False


def _hash_detected_source(
    fd: int, deadline: float, counters: dict[str, int], byte_budget: int
) -> Any:
    """非 UTF-8 时只重读已绑定的普通文件句柄，检测输入有独立的单文件上限。"""
    from .indexing_snapshot import _INDEX_SOURCE_BYTE_LIMIT, decode_index_source

    os.lseek(fd, 0, os.SEEK_SET)
    pieces: list[bytes] = []
    total = 0
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        total += len(chunk)
        counters["input"] += len(chunk)
        if total > _INDEX_SOURCE_BYTE_LIMIT or counters["input"] > byte_budget:
            raise OverflowError
        pieces.append(chunk)
    source = decode_index_source(b"".join(pieces))
    digest = hashlib.sha256()
    for start in range(0, len(source), 65536):
        _hash_text(
            digest, source[start : start + 65536], deadline, counters, byte_budget
        )
    if time.monotonic() > deadline:
        raise TimeoutError
    return digest


def _hash_normalized_chunk(
    digest: Any,
    chunk: str,
    pending_cr: bool,
    deadline: float,
    counters: dict[str, int],
    byte_budget: int,
) -> bool:
    """Hash decoded text with universal-newline translation in bounded spans."""
    index = 0
    if pending_cr:
        _hash_output(digest, b"\n", deadline, counters, byte_budget)
        if chunk.startswith("\n"):
            index = 1
    while index < len(chunk):
        carriage = chunk.find("\r", index)
        if carriage < 0:
            _hash_text(digest, chunk[index:], deadline, counters, byte_budget)
            return False
        if carriage > index:
            _hash_text(digest, chunk[index:carriage], deadline, counters, byte_budget)
        if carriage + 1 == len(chunk):
            return True
        _hash_output(digest, b"\n", deadline, counters, byte_budget)
        index = carriage + (2 if chunk[carriage + 1] == "\n" else 1)
    return False


def _hash_text(
    digest: Any, text: str, deadline: float, counters: dict[str, int], byte_budget: int
) -> None:
    """Encode one decoded span exactly as the index writer hashes it."""
    _hash_output(digest, text.encode("utf-8"), deadline, counters, byte_budget)


def _hash_output(
    digest: Any, raw: bytes, deadline: float, counters: dict[str, int], byte_budget: int
) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError
    counters["output"] += len(raw)
    if counters["output"] > byte_budget:
        raise OverflowError
    digest.update(raw)
