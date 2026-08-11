"""Bounded streaming source normalization for snapshot certification."""

from __future__ import annotations

import codecs
import fnmatch
import hashlib
import os
import stat
import time
from typing import TYPE_CHECKING, Any

from .constants import EXCLUDE_DIRS
from .languages.lang_extension_map import EXT_TO_LANG

if TYPE_CHECKING:
    from .index_source_snapshot import SourceScopeDescriptor


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


def inventory_portable(
    root: str,
    deadline: float,
    scope: SourceScopeDescriptor,
    *,
    with_content: bool,
    entry_budget: int,
    entry_path_byte_budget: int,
    path_budget: int,
    byte_budget: int,
    bounded_sorted: Any,
    metadata_marker: Any,
    same_file_metadata: Any,
) -> tuple[tuple[tuple[str, str, str], ...], bool]:
    """Bounded Windows fallback; POSIX always uses descriptor-relative traversal."""
    rows: list[tuple[str, str, str]] = []
    counters = {"entries": 0, "path_bytes": 0, "input": 0, "output": 0}
    unsafe = False
    supported_count = 0
    replay_limit = min(scope.certification_max_files, path_budget)
    root_real = os.path.realpath(root)
    stack: list[tuple[str, str]] = []
    for relative_root in scope.roots:
        directory = os.path.realpath(os.path.join(root, relative_root))
        if os.path.commonpath((root_real, directory)) != root_real:
            raise OSError("source root escapes project")
        stack.append(
            (
                directory,
                ""
                if relative_root == "."
                else relative_root.replace("\\", "/").rstrip("/"),
            )
        )
    while stack:
        directory, prefix = stack.pop()
        records = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if time.monotonic() > deadline:
                    raise TimeoutError
                rel = f"{prefix}/{entry.name}" if prefix else entry.name
                counters["entries"] += 1
                counters["path_bytes"] += len(rel.encode("utf-8", "surrogatepass"))
                if (
                    counters["entries"] > entry_budget
                    or counters["path_bytes"] > entry_path_byte_budget
                ):
                    raise OverflowError
                records.append(
                    (entry.name, entry.path, entry.stat(follow_symlinks=False))
                )
        for name, path, info in reversed(
            tuple(bounded_sorted(records, deadline=deadline))
        ):
            rel = f"{prefix}/{name}" if prefix else name
            if stat.S_ISDIR(info.st_mode):
                if name not in EXCLUDE_DIRS and not name.startswith("."):
                    stack.append((path, rel))
                continue
            language = EXT_TO_LANG.get(os.path.splitext(name)[1].lower())
            if language is None:
                continue
            supported_count += 1
            if supported_count > replay_limit:
                raise OverflowError
            if any(
                fnmatch.fnmatch(rel, pattern) for pattern in scope.effective_excludes
            ):
                continue
            if not stat.S_ISREG(info.st_mode):
                unsafe = True
                rows.append((rel, metadata_marker(info) + "|<unsafe>", language))
            elif not with_content:
                rows.append((rel, metadata_marker(info), language))
            else:
                marker, content_hash, clean = hash_source_at(
                    None,
                    path,
                    info,
                    deadline,
                    counters,
                    byte_budget,
                    metadata_marker,
                    same_file_metadata,
                )
                unsafe = unsafe or not clean
                rows.append((rel, marker + "|" + content_hash, language))
    return tuple(bounded_sorted(rows, deadline=deadline)), unsafe
