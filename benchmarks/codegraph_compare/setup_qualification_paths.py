"""Canonical, no-symlink filesystem operations for qualification evidence."""

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


def _lstat_regular_beneath(root: Path, relative: str) -> Path:
    """Return a regular file beneath root without following any symlink."""
    relative = canonical_relative_path(relative)
    if stat.S_ISLNK(os.lstat(root).st_mode):
        raise ValueError("Root must not be a symlink")
    root = root.resolve(strict=True)
    if stat.S_ISLNK(os.lstat(root).st_mode):
        raise ValueError("Resolved root must not be a symlink")
    current = root
    for component in relative.split("/"):
        current = current / component
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Symlink component is forbidden: {relative}")
    if not stat.S_ISREG(os.lstat(current).st_mode):
        raise ValueError(f"Expected regular file: {relative}")
    if os.path.commonpath((str(root), str(current))) != str(root):
        raise ValueError("Path escaped root")
    return current


def _hash_tree(root: Path) -> str:
    """Hash canonical names and bytes without following index-tree symlinks."""
    if stat.S_ISLNK(os.lstat(root).st_mode) or not root.is_dir():
        raise ValueError("Index root must be a non-symlink directory")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        canonical_relative_path(relative)
        metadata = os.lstat(path)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("Index tree contains a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Index tree contains a special file")
        payload = path.read_bytes()
        encoded = relative.encode()
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
        digest.update(len(payload).to_bytes(8, "big") + payload)
    return digest.hexdigest()
