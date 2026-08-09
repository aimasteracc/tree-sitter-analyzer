"""Canonical, race-resistant filesystem operations for qualification evidence."""

from __future__ import annotations

import hashlib
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any


def canonical_relative_path(value: str) -> str:
    """Accept only an already-canonical POSIX repository-relative path."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError(f"Non-canonical POSIX path: {value!r}")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise ValueError(f"Non-canonical POSIX path: {value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Non-canonical POSIX path: {value!r}")
    if PurePosixPath(value).as_posix() != value:
        raise ValueError(f"Non-canonical POSIX path: {value!r}")
    return value


def _open_root(root: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not os.supports_dir_fd:
        raise RuntimeError("Qualification evidence requires openat/O_NOFOLLOW support")
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _read_flags() -> int:
    # O_NONBLOCK makes opening a producer-created FIFO safe; fstat below then
    # rejects it before any read. It is harmless for regular files/directories.
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)


def _open_beneath(root_fd: int, relative: str, *, directory: bool = False) -> int:
    parts = canonical_relative_path(relative).split("/")
    current = os.dup(root_fd)
    try:
        for number, component in enumerate(parts):
            last = number == len(parts) - 1
            flags = _read_flags()
            if not last or directory:
                flags |= os.O_DIRECTORY
            next_fd = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        mode = os.fstat(current).st_mode
        expected = stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)
        if not expected:
            raise ValueError(f"Unexpected evidence file type: {relative}")
        return current
    except Exception:
        os.close(current)
        raise


def _read_regular_at(root_fd: int, relative: str) -> bytes:
    descriptor = _open_beneath(root_fd, relative)
    try:
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def _read_regular_beneath(root: Path, relative: str) -> bytes:
    root_fd = _open_root(root)
    try:
        return _read_regular_at(root_fd, relative)
    finally:
        os.close(root_fd)


def _lstat_regular_beneath(root: Path, relative: str) -> Path:
    """Compatibility locator; validation must read with `_read_regular_beneath`."""
    _read_regular_beneath(root, relative)
    return root / canonical_relative_path(relative)


def _visit_tree(
    root_fd: int,
    on_file: Callable[[int, str], None],
    on_directory: Callable[[int, str], None] | None = None,
    prefix: str = "",
) -> None:
    for name in sorted(os.listdir(root_fd)):
        relative = f"{prefix}/{name}" if prefix else name
        canonical_relative_path(relative)
        descriptor = os.open(name, _read_flags(), dir_fd=root_fd)
        try:
            mode = os.fstat(descriptor).st_mode
            if stat.S_ISDIR(mode):
                _visit_tree(descriptor, on_file, on_directory, relative)
                if on_directory is not None:
                    on_directory(descriptor, relative)
            elif stat.S_ISREG(mode):
                on_file(descriptor, relative)
            else:
                raise ValueError("Artifact tree contains a special file")
        finally:
            os.close(descriptor)


def _tree_size_at(root_fd: int, relative: str) -> int:
    directory_fd = _open_beneath(root_fd, relative, directory=True)
    total = 0

    def add(descriptor: int, _relative: str) -> None:
        nonlocal total
        total += os.fstat(descriptor).st_size

    try:
        _visit_tree(directory_fd, add)
        return total
    finally:
        os.close(directory_fd)


def _tree_size(root: Path) -> int:
    root_fd = _open_root(root)
    try:
        total = 0

        def add(descriptor: int, _relative: str) -> None:
            nonlocal total
            total += os.fstat(descriptor).st_size

        _visit_tree(root_fd, add)
        return total
    finally:
        os.close(root_fd)


_HASH_CHUNK_BYTES = 1024 * 1024
_DEFAULT_TREE_CEILING_BYTES = 1024 * 1024 * 1024
_DEFAULT_STREAM_TIMEOUT_SECONDS = 30.0


def _hash_regular_descriptor(
    descriptor: int,
    *,
    expected_size: int,
    max_bytes: int,
    timeout_seconds: float = _DEFAULT_STREAM_TIMEOUT_SECONDS,
    digest: Any | None = None,
) -> str:
    """Hash one immutable-size snapshot without following producer growth."""
    metadata = os.fstat(descriptor)
    if metadata.st_size != expected_size:
        raise ValueError("Artifact file size does not match trusted expectation")
    if expected_size < 0 or expected_size > max_bytes:
        raise ValueError("Artifact file exceeds trusted size ceiling")
    allocated = getattr(metadata, "st_blocks", 0) * 512
    if expected_size > 0 and allocated < expected_size:
        raise ValueError("Sparse artifact files are forbidden")

    target = digest if digest is not None else hashlib.sha256()
    deadline = time.monotonic() + timeout_seconds
    read_total = 0
    max_reads = (expected_size + _HASH_CHUNK_BYTES - 1) // _HASH_CHUNK_BYTES
    reads = 0
    while read_total < expected_size:
        if reads >= max_reads or time.monotonic() > deadline:
            raise ValueError("Artifact file hashing exceeded its bounded loop")
        chunk = os.read(descriptor, min(_HASH_CHUNK_BYTES, expected_size - read_total))
        reads += 1
        if not chunk:
            raise ValueError("Artifact file changed while hashing")
        read_total += len(chunk)
        target.update(chunk)

    # Exactly one bounded byte distinguishes the snapshot from a concurrently
    # appended file without ever chasing a producer-controlled EOF.
    if os.read(descriptor, 1):
        raise ValueError("Artifact file grew while hashing")
    if os.fstat(descriptor).st_size != expected_size:
        raise ValueError("Artifact file changed while hashing")
    if time.monotonic() > deadline:
        raise ValueError("Artifact file hashing exceeded its timeout")
    return target.hexdigest()


def _stream_file(descriptor: int, digest: Any, *, remaining: int) -> int:
    metadata = os.fstat(descriptor)
    digest.update(metadata.st_size.to_bytes(8, "big"))
    _hash_regular_descriptor(
        descriptor,
        expected_size=metadata.st_size,
        max_bytes=remaining,
        digest=digest,
    )
    return metadata.st_size


def _update_typed_path(digest: Any, kind: bytes, relative: str) -> None:
    encoded = relative.encode("utf-8")
    digest.update(kind + len(encoded).to_bytes(8, "big") + encoded)


def _hash_tree_descriptor(directory_fd: int, *, max_bytes: int) -> str:
    digest = hashlib.sha256()
    consumed = 0
    file_count = 0
    directory_count = 0

    def collect_file(descriptor: int, item: str) -> None:
        nonlocal consumed, file_count
        _update_typed_path(digest, b"F", item)
        consumed += _stream_file(descriptor, digest, remaining=max_bytes - consumed)
        file_count += 1

    def collect_directory(_descriptor: int, item: str) -> None:
        nonlocal directory_count
        _update_typed_path(digest, b"D", item)
        directory_count += 1

    _visit_tree(directory_fd, collect_file, collect_directory)
    digest.update(
        b"C" + file_count.to_bytes(8, "big") + directory_count.to_bytes(8, "big")
    )
    return digest.hexdigest()


def _hash_tree_at(
    root_fd: int, relative: str, *, max_bytes: int = _DEFAULT_TREE_CEILING_BYTES
) -> str:
    directory_fd = _open_beneath(root_fd, relative, directory=True)
    try:
        return _hash_tree_descriptor(directory_fd, max_bytes=max_bytes)
    finally:
        os.close(directory_fd)


def _hash_tree(root: Path, *, max_bytes: int = _DEFAULT_TREE_CEILING_BYTES) -> str:
    root_fd = _open_root(root)
    try:
        return _hash_tree_descriptor(root_fd, max_bytes=max_bytes)
    finally:
        os.close(root_fd)
