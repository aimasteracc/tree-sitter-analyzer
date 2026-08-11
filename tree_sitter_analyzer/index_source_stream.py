"""Bounded streaming source normalization for snapshot certification."""

from __future__ import annotations

import codecs
import hashlib
import os
import stat
import time
from typing import Any


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
    """Validate UTF-8 and hash newline-normalized raw bytes in bounded chunks."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
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
    valid_utf8 = True
    pending_cr = False
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
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
            if valid_utf8:
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError:
                    valid_utf8 = False
            if valid_utf8:
                pending_cr = _hash_normalized_chunk(
                    digest, chunk, pending_cr, deadline, counters, byte_budget
                )
        if valid_utf8:
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                valid_utf8 = False
        if valid_utf8 and pending_cr:
            _hash_output(digest, b"\n", deadline, counters, byte_budget)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    clean = valid_utf8 and same_file_metadata(before, after)
    return (
        metadata_marker(after),
        digest.hexdigest() if clean else "<unsafe>",
        clean,
    )


def _hash_normalized_chunk(
    digest: Any,
    chunk: bytes,
    pending_cr: bool,
    deadline: float,
    counters: dict[str, int],
    byte_budget: int,
) -> bool:
    """Hash CRLF/CR as LF without constructing a normalized buffer."""
    index = 0
    if pending_cr:
        _hash_output(digest, b"\n", deadline, counters, byte_budget)
        if chunk.startswith(b"\n"):
            index = 1
    while index < len(chunk):
        carriage = chunk.find(b"\r", index)
        if carriage < 0:
            _hash_output(digest, chunk[index:], deadline, counters, byte_budget)
            return False
        if carriage > index:
            _hash_output(digest, chunk[index:carriage], deadline, counters, byte_budget)
        if carriage + 1 == len(chunk):
            return True
        _hash_output(digest, b"\n", deadline, counters, byte_budget)
        index = carriage + (2 if chunk[carriage + 1] == 10 else 1)
    return False


def _hash_output(
    digest: Any, raw: bytes, deadline: float, counters: dict[str, int], byte_budget: int
) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError
    counters["output"] += len(raw)
    if counters["output"] > byte_budget:
        raise OverflowError
    digest.update(raw)
