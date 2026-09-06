"""Bounded streaming source normalization for snapshot certification."""

from __future__ import annotations

import codecs
import hashlib
import os
import stat
import time
from typing import Any


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
    """Hash the writer's replacement-decoded, newline-normalized source stream."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = (
            os.open(name, flags)
            if directory_fd is None
            else os.open(name, flags, dir_fd=directory_fd)
        )
    except OSError:
        return metadata_marker(before), "<unsafe>", False
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending_cr = False
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or not opened_entry_matches(before, opened):
            return metadata_marker(opened), "<unsafe>", False
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
        after = os.fstat(fd)
    finally:
        os.close(fd)
    clean = same_file_metadata(before, after)
    if not clean:
        # #1364/#1373 家族：极新文件的元数据（size/mtime_ns）在 walker 的
        # lstat 快照与读后 fstat 之间仍在沉降（NTFS/Defender 延迟，满载
        # CI 上窗口更大）——旧快照过期被误判为篡改。重取一次 lstat：仅当
        # 「与读后状态一致」且「ctime 未变」（自 walker 观测以来没有真实
        # 写入，只是惰性沉降）才判 clean。原地重写会更新 ctime（POSIX），
        # 即使恢复 mtime/size 也会在此维持 unsafe——防篡改不降级；
        # Windows 上 ctime=创建时间不随重写变化，但此时内容摘要已变，
        # 认证层的行比对（rows != recorded）仍会拦截，纵深防御保留。
        try:
            refreshed = os.lstat(name)
        except OSError:
            refreshed = None  # 无法重取时维持原判定
        if (
            refreshed is not None
            and same_file_metadata(refreshed, after)
            and int(refreshed.st_ctime_ns) == int(before.st_ctime_ns)
        ):
            clean = True
    return (
        metadata_marker(after),
        digest.hexdigest() if clean else "<unsafe>",
        clean,
    )


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
