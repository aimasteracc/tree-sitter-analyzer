"""Canonical, race-resistant filesystem operations for qualification evidence."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path, PurePosixPath


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


def _seal_tree_at(root_fd: int, mode: int) -> None:
    """Seal files first, then directories bottom-up, including the pinned root."""
    _visit_tree(
        root_fd,
        lambda descriptor, _relative: os.fchmod(descriptor, mode),
        lambda descriptor, _relative: os.fchmod(descriptor, 0o500),
    )
    os.fchmod(root_fd, 0o500)


def _chmod_regular_tree(root: Path, mode: int) -> None:
    root_fd = _open_root(root)
    try:
        _seal_tree_at(root_fd, mode)
    finally:
        os.close(root_fd)


def _manifest_tree_at(root_fd: int) -> dict[str, str]:
    result: dict[str, str] = {}

    def collect(descriptor: int, relative: str) -> None:
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            result[relative] = hashlib.sha256(stream.read()).hexdigest()

    _visit_tree(root_fd, collect)
    return result


def _manifest_tree(root: Path) -> dict[str, str]:
    root_fd = _open_root(root)
    try:
        return _manifest_tree_at(root_fd)
    finally:
        os.close(root_fd)


def _hash_tree_at(root_fd: int, relative: str) -> str:
    directory_fd = _open_beneath(root_fd, relative, directory=True)
    digest = hashlib.sha256()

    def collect(descriptor: int, item: str) -> None:
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            payload = stream.read()
        encoded = item.encode()
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
        digest.update(len(payload).to_bytes(8, "big") + payload)

    try:
        _visit_tree(directory_fd, collect)
        return digest.hexdigest()
    finally:
        os.close(directory_fd)


def _hash_tree(root: Path) -> str:
    root_fd = _open_root(root)
    try:
        digest = hashlib.sha256()

        def collect(descriptor: int, relative: str) -> None:
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                payload = stream.read()
            encoded = relative.encode()
            digest.update(len(encoded).to_bytes(8, "big") + encoded)
            digest.update(len(payload).to_bytes(8, "big") + payload)

        _visit_tree(root_fd, collect)
        return digest.hexdigest()
    finally:
        os.close(root_fd)
