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
    """Hash the writer's replacement-decoded, newline-normalized source stream."""
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
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
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
