"""Fail-closed source identity and safe workspace reads for frozen diffs."""

from __future__ import annotations

import errno
import os
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, TypeVar, cast

_T = TypeVar("_T")


def _stat(*args: Any, **kwargs: Any) -> os.stat_result:
    """Module-local stat seam; tests must not mutate the process-wide os module."""
    return os.stat(*args, **kwargs)


def _open(*args: Any, **kwargs: Any) -> int:
    """Module-local descriptor-open seam for isolated fault injection."""
    return os.open(*args, **kwargs)


def _read(*args: Any, **kwargs: Any) -> bytes:
    return os.read(*args, **kwargs)


def _readlink(*args: Any, **kwargs: Any) -> str | bytes:
    return cast(str | bytes, os.readlink(*args, **kwargs))


def _close(*args: Any, **kwargs: Any) -> None:
    os.close(*args, **kwargs)


def _supports_nofollow() -> bool:
    # Both flags are required for race-safe leaf opens.  O_NOFOLLOW rejects
    # symlinks; O_NONBLOCK prevents a regular-file-to-FIFO swap from blocking
    # inside open() before the shared deadline can be checked.
    return os.name != "nt" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_NONBLOCK")


def _regular_open_flags() -> int:
    if not _supports_nofollow():
        raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class SourceOracleError(RuntimeError):
    """Stable internal capture failure (the message is a public error code)."""


@dataclass(frozen=True)
class RootIdentity:
    realpath: str
    device: int
    inode: int


@dataclass(frozen=True)
class SafePath:
    data: bytes | None
    metadata: tuple[bytes, ...]
    kind: str


@dataclass(frozen=True)
class WorkspaceManifestEntry:
    """Pre-capture descriptor identity and Git-cleaned blob identity."""

    descriptor_chain: tuple[bytes, ...]
    filtered_oid: bytes | None = None


def canonical_root(project_root: str | None) -> tuple[str, RootIdentity]:
    root = os.path.realpath(project_root or ".")
    try:
        info = _stat(root, follow_symlinks=True)
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_INVALID") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_INVALID")
    return root, RootIdentity(root, info.st_dev, info.st_ino)


def normalize_repo_path(path: str) -> str:
    value = path.replace("\\", "/") if os.name == "nt" else path
    while value.startswith("./"):
        value = value[2:]
    pure = PurePosixPath(value)
    if not value or pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH")
    if "\x00" in value:
        raise SourceOracleError("DIFF_SNAPSHOT_INVALID_PATH")
    return str(pure)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")
    return remaining


def _metadata(info: os.stat_result) -> bytes:
    values = (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )
    return b",".join(str(value).encode("ascii") for value in values)


def stable_descriptor_chain(metadata: tuple[bytes, ...]) -> tuple[bytes, ...]:
    """Return mode/device/inode identities, excluding mutable directory times."""
    result: list[bytes] = []
    for descriptor in metadata:
        if descriptor == b"missing":
            result.append(descriptor)
            continue
        fields = descriptor.split(b",")
        if len(fields) != 6:
            raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH")
        result.append(b",".join(fields[:3]))
    return tuple(result)


def safe_workspace_path(
    root: str,
    path: str,
    *,
    deadline: float,
    limit: int,
    read_regular: bool = True,
    allow_directory: bool = False,
    expected_chain: tuple[bytes, ...] | None = None,
) -> SafePath:
    """Read a repo path without following any symlink or accepting special files."""
    normalized = normalize_repo_path(path)
    if not _supports_nofollow():
        raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")
    parts = normalized.split("/")
    flags_dir = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptors: list[int] = []
    metadata: list[bytes] = []

    def validate_chain(items: list[bytes]) -> None:
        actual = stable_descriptor_chain(tuple(items))
        if expected_chain is not None and actual != expected_chain:
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")

    try:
        current = _open(root, flags_dir)
        descriptors.append(current)
        metadata.append(_metadata(os.fstat(current)))
        for component in parts[:-1]:
            parent = current
            try:
                before_ancestor = _stat(component, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                missing_metadata = metadata + [b"missing"]
                validate_chain(missing_metadata)
                return SafePath(None, tuple(missing_metadata), "missing")
            try:
                current = _open(component, flags_dir, dir_fd=parent)
            except FileNotFoundError:
                missing_metadata = metadata + [b"missing"]
                validate_chain(missing_metadata)
                return SafePath(None, tuple(missing_metadata), "missing")
            except OSError as exc:
                if exc.errno not in (errno.ENOTDIR, errno.ELOOP):
                    raise
                # O_DIRECTORY|O_NOFOLLOW reports a stable regular/symlink
                # ancestor as ENOTDIR/ELOOP.  It means every descendant is
                # absent, not that the existing ancestor itself is unsafe.
                try:
                    after_ancestor = _stat(
                        component, dir_fd=parent, follow_symlinks=False
                    )
                except OSError:
                    raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
                if (
                    stat.S_ISDIR(before_ancestor.st_mode)
                    or stat.S_ISDIR(after_ancestor.st_mode)
                    or _metadata(before_ancestor) != _metadata(after_ancestor)
                ):
                    raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
                missing_metadata = metadata + [
                    _metadata(before_ancestor),
                    b"missing",
                ]
                validate_chain(missing_metadata)
                return SafePath(None, tuple(missing_metadata), "missing")
            descriptors.append(current)
            opened_ancestor = os.fstat(current)
            if _metadata(before_ancestor) != _metadata(opened_ancestor):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            metadata.append(_metadata(opened_ancestor))
        parent = current
        name = parts[-1]
        try:
            before = _stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            missing_metadata = metadata + [b"missing"]
            validate_chain(missing_metadata)
            return SafePath(None, tuple(missing_metadata), "missing")
        metadata.append(_metadata(before))
        if stat.S_ISLNK(before.st_mode):
            target = _readlink(os.fsencode(name), dir_fd=parent)
            data = target if isinstance(target, bytes) else os.fsencode(target)
            after = _stat(name, dir_fd=parent, follow_symlinks=False)
            if _metadata(before) != _metadata(after):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            if len(data) > limit:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            validate_chain(metadata)
            return SafePath(data, tuple(metadata), "symlink")
        if stat.S_ISDIR(before.st_mode) and allow_directory:
            validate_chain(metadata)
            return SafePath(None, tuple(metadata), "directory")
        if not stat.S_ISREG(before.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
        if not read_regular:
            validate_chain(metadata)
            return SafePath(None, tuple(metadata), "file")
        fd = _open(name, _regular_open_flags(), dir_fd=parent)
        descriptors.append(fd)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
        if _metadata(before) != _metadata(opened):
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        buffer = bytearray()
        while True:
            _remaining(deadline)
            chunk = _read(fd, min(64 * 1024, limit - len(buffer) + 1))
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        after = os.fstat(fd)
        if _metadata(opened) != _metadata(after):
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        validate_chain(metadata)
        return SafePath(bytes(buffer), tuple(metadata), "file")
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
    finally:
        for fd in reversed(descriptors):
            try:
                _close(fd)
            except OSError:
                pass


def _safe_absolute_regular(
    path: str, *, deadline: float, limit: int, allow_missing: bool = False
) -> SafePath:
    """Read an absolute regular file through a complete no-follow descriptor chain."""
    absolute = os.path.abspath(path)
    if not os.path.isabs(absolute) or not _supports_nofollow():
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    parts = [part for part in absolute.split(os.sep) if part]
    flags_dir = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptors: list[int] = []
    metadata: list[bytes] = []
    try:
        current = _open(os.sep, flags_dir)
        descriptors.append(current)
        metadata.append(_metadata(os.fstat(current)))
        for component in parts[:-1]:
            current = _open(component, flags_dir, dir_fd=current)
            descriptors.append(current)
            metadata.append(_metadata(os.fstat(current)))
        try:
            before = _stat(parts[-1], dir_fd=current, follow_symlinks=False)
        except FileNotFoundError:
            if allow_missing:
                return SafePath(None, tuple(metadata + [b"missing"]), "missing")
            raise
        if not stat.S_ISREG(before.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        fd = _open(parts[-1], _regular_open_flags(), dir_fd=current)
        descriptors.append(fd)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if _metadata(before) != _metadata(opened):
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        metadata.append(_metadata(opened))
        data = bytearray()
        while True:
            _remaining(deadline)
            chunk = _read(fd, min(64 * 1024, limit - len(data) + 1))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > limit:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        if _metadata(opened) != _metadata(os.fstat(fd)):
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        return SafePath(bytes(data), tuple(metadata), "file")
    except SourceOracleError:
        raise
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
    finally:
        for fd in reversed(descriptors):
            try:
                _close(fd)
            except OSError:
                pass


def git_output(root: str, args: list[str], *, deadline: float, limit: int) -> bytes:
    from .source_oracle_git import git_output as run_git

    return run_git(root, args, deadline=deadline, limit=limit)


def oracle_generation(
    project_root: str | None,
    mode: str = "diff",
    *,
    deadline: float | None = None,
    manifest: dict[str, WorkspaceManifestEntry] | None = None,
    epoch_out: list[Any] | None = None,
) -> tuple[str, RootIdentity]:
    from .source_oracle_git import oracle_generation as generate

    return generate(
        project_root,
        mode,
        deadline=deadline,
        manifest=manifest,
        epoch_out=epoch_out,
    )


def capture_inventory(
    root: str, mode: str, *, deadline: float, limit: int
) -> tuple[str, ...]:
    from .source_oracle_git import capture_inventory as capture

    return capture(root, mode, deadline=deadline, limit=limit)


def source_generation(project_root: str | None, mode: str = "diff") -> str:
    from .source_oracle_git import source_generation as generate

    return generate(project_root, mode)


def capture_consistent(
    project_root: str | None, capture: Callable[[], _T]
) -> tuple[str | None, _T]:
    from .source_oracle_git import capture_consistent as capture_epoch

    return capture_epoch(project_root, capture)


_GIT_EXPORTS = {
    "_head_identity",
    "_frame",
    "_index_entries",
    "_head_entries",
    "_tracked_paths",
    "_frame_workspace_path",
}


def __getattr__(name: str) -> Any:
    """Lazily re-export Git generation helpers without creating an import cycle."""
    if name not in _GIT_EXPORTS:
        raise AttributeError(name)
    from . import source_oracle_git

    return getattr(source_oracle_git, name)
