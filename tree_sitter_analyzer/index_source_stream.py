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
    *,
    raw_content: bool = False,
) -> tuple[str, str, bool]:
    """有界读取同一句柄；监听使用原始字节，索引认证使用统一解码源码。"""
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
                if raw_content:
                    digest.update(chunk)
                    continue
                decoded = decoder.decode(chunk, final=False)
                pending_cr = _hash_normalized_chunk(
                    digest, decoded, pending_cr, deadline, counters, byte_budget
                )
            decoded = "" if raw_content else decoder.decode(b"", final=True)
            _hash_normalized_chunk(
                digest, decoded, pending_cr, deadline, counters, byte_budget
            )
        except UnicodeDecodeError:
            digest = _hash_detected_source(fd, deadline, counters, byte_budget)
        after = os.fstat(fd)
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
