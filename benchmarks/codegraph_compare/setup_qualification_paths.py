"""Canonical, race-resistant filesystem operations for qualification evidence."""

from __future__ import annotations

import hashlib
import os
import stat
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


def _open_beneath(root_fd: int, relative: str, *, directory: bool = False) -> int:
    parts = canonical_relative_path(relative).split("/")
    current = os.dup(root_fd)
    try:
        for number, component in enumerate(parts):
            last = number == len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW
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


def _read_regular_beneath(root: Path, relative: str) -> bytes:
    """Read a regular file through stable no-follow directory descriptors."""
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, relative)
        with os.fdopen(descriptor, "rb") as stream:
            return stream.read()
    finally:
        os.close(root_fd)


def _lstat_regular_beneath(root: Path, relative: str) -> Path:
    """Compatibility locator; validation must read with `_read_regular_beneath`."""
    _read_regular_beneath(root, relative)
    return root / canonical_relative_path(relative)


def _tree_size(root: Path) -> int:
    """Sum regular file sizes using the same stable no-follow traversal."""
    root_fd = _open_root(root)

    def visit(directory_fd: int) -> int:
        total = 0
        for name in sorted(os.listdir(directory_fd)):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                mode = os.fstat(descriptor).st_mode
                if stat.S_ISDIR(mode):
                    total += visit(descriptor)
                elif stat.S_ISREG(mode):
                    total += os.fstat(descriptor).st_size
                else:
                    raise ValueError("Index tree contains a special file")
            finally:
                os.close(descriptor)
        return total

    try:
        return visit(root_fd)
    finally:
        os.close(root_fd)


def _chmod_regular_tree(root: Path, mode: int) -> None:
    """Change regular evidence modes without path re-resolution."""
    root_fd = _open_root(root)

    def visit(directory_fd: int) -> None:
        for name in sorted(os.listdir(directory_fd)):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                kind = os.fstat(descriptor).st_mode
                if stat.S_ISDIR(kind):
                    visit(descriptor)
                elif stat.S_ISREG(kind):
                    os.fchmod(descriptor, mode)
                else:
                    raise ValueError("Artifact tree contains a special file")
            finally:
                os.close(descriptor)

    try:
        visit(root_fd)
    finally:
        os.close(root_fd)


def _manifest_tree(root: Path) -> dict[str, str]:
    """Return a stable path-to-digest manifest through descriptor traversal."""
    root_fd = _open_root(root)
    result: dict[str, str] = {}

    def visit(directory_fd: int, prefix: str) -> None:
        for name in sorted(os.listdir(directory_fd)):
            relative = f"{prefix}/{name}" if prefix else name
            canonical_relative_path(relative)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                mode = os.fstat(descriptor).st_mode
                if stat.S_ISDIR(mode):
                    visit(descriptor, relative)
                elif stat.S_ISREG(mode):
                    with os.fdopen(os.dup(descriptor), "rb") as stream:
                        result[relative] = hashlib.sha256(stream.read()).hexdigest()
                else:
                    raise ValueError("Artifact tree contains a special file")
            finally:
                os.close(descriptor)

    try:
        visit(root_fd, "")
    finally:
        os.close(root_fd)
    return result


def _hash_tree(root: Path) -> str:
    """Hash canonical names and bytes via recursive openat/O_NOFOLLOW traversal."""
    root_fd = _open_root(root)
    digest = hashlib.sha256()

    def visit(directory_fd: int, prefix: str) -> None:
        for name in sorted(os.listdir(directory_fd)):
            relative = f"{prefix}/{name}" if prefix else name
            canonical_relative_path(relative)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                mode = os.fstat(descriptor).st_mode
                if stat.S_ISDIR(mode):
                    visit(descriptor, relative)
                elif stat.S_ISREG(mode):
                    with os.fdopen(os.dup(descriptor), "rb") as stream:
                        payload = stream.read()
                    encoded = relative.encode()
                    digest.update(len(encoded).to_bytes(8, "big") + encoded)
                    digest.update(len(payload).to_bytes(8, "big") + payload)
                else:
                    raise ValueError("Index tree contains a special file")
            finally:
                os.close(descriptor)

    try:
        visit(root_fd, "")
    finally:
        os.close(root_fd)
    return digest.hexdigest()
