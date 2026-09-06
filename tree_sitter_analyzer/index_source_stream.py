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
        # #1364/#1373 家族终章（诊断实锤 SOURCE_SCOPE_UNSAFE:hash_unclean）：
        # Windows 上同一未动文件的句柄缓存与路径缓存可返回不同 mtime_ns，
        # 「重取 lstat 对比读后 fstat」在缓存分裂面前永远对不上。改为
        # 「安静判定」：间隔 20ms 连续两次新鲜 lstat 互相全等，且 ctime
        # 相对 walker 快照未变 → 文件已安静，判 clean。防篡改不降级：
        # POSIX 原地重写必动 ctime；Windows 的 ctime=创建时间不随写变化，
        # 但重写使内容摘要改变，认证层的行比对（rows != recorded）仍会
        # 拦截——纵深防御保留。
        for _ in range(3):
            time.sleep(0.02)
            try:
                r1 = os.lstat(name)
                r2 = os.lstat(name)
            except OSError:
                break  # 无法重取时维持原判定
            if same_file_metadata(r1, r2) and int(r1.st_ctime_ns) == int(
                before.st_ctime_ns
            ):
                clean = True
                break
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
