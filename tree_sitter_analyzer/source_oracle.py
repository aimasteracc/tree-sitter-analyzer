"""Fail-closed source identity and safe workspace reads for frozen diffs."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess  # nosec B404
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, BinaryIO, TypeVar, cast

_LOCK = threading.RLock()
_T = TypeVar("_T")
_FRAME_DOMAIN = b"tsa-source-generation-v3"
_MAX_INVENTORY_BYTES = 16 * 1024 * 1024
_MAX_WORKTREE_PATHS = 200_000
_MAX_WORKTREE_CONTENT_BYTES = 64 * 1024 * 1024


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
    return os.name != "nt" and hasattr(os, "O_NOFOLLOW")


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


def git_output(root: str, args: list[str], *, deadline: float, limit: int) -> bytes:
    """Run Git fail-closed with a shared deadline and bounded retained output."""
    if limit < 0:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    try:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        env["GIT_OPTIONAL_LOCKS"] = "0"
        proc = subprocess.Popen(  # nosec B603
            ["git", *args],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc

    output = bytearray()
    stderr = bytearray()
    failure: list[str] = []

    def drain(stream: BinaryIO | None, target: bytearray, cap: int, code: str) -> None:
        try:
            if stream is None:
                failure.append("DIFF_SNAPSHOT_GIT_ERROR")
                return
            read = stream.read
            while True:
                chunk = read(64 * 1024)
                if not chunk:
                    break
                if len(target) + len(chunk) > cap:
                    failure.append(code)
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    break
                target.extend(chunk)
        except OSError:
            failure.append("DIFF_SNAPSHOT_GIT_ERROR")

    out_thread = threading.Thread(
        target=drain,
        args=(proc.stdout, output, limit, "DIFF_SNAPSHOT_CAPACITY"),
        daemon=True,
    )
    err_thread = threading.Thread(
        target=drain,
        args=(proc.stderr, stderr, 64 * 1024, "DIFF_SNAPSHOT_GIT_ERROR"),
        daemon=True,
    )
    out_thread.start()
    err_thread.start()
    try:
        proc.wait(timeout=_remaining(deadline))
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait()
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT") from exc
    out_thread.join(timeout=_remaining(deadline))
    err_thread.join(timeout=_remaining(deadline))
    if out_thread.is_alive() or err_thread.is_alive():
        proc.kill()
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")
    if failure:
        raise SourceOracleError(failure[0])
    if proc.returncode != 0:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return bytes(output)


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


def safe_workspace_path(
    root: str,
    path: str,
    *,
    deadline: float,
    limit: int,
    read_regular: bool = True,
    allow_directory: bool = False,
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
    try:
        current = _open(root, flags_dir)
        descriptors.append(current)
        metadata.append(_metadata(os.fstat(current)))
        for component in parts[:-1]:
            current = _open(component, flags_dir, dir_fd=current)
            descriptors.append(current)
            metadata.append(_metadata(os.fstat(current)))
        parent = current
        name = parts[-1]
        try:
            before = _stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return SafePath(None, tuple(metadata + [b"missing"]), "missing")
        metadata.append(_metadata(before))
        if stat.S_ISLNK(before.st_mode):
            target = _readlink(os.fsencode(name), dir_fd=parent)
            data = target if isinstance(target, bytes) else os.fsencode(target)
            after = _stat(name, dir_fd=parent, follow_symlinks=False)
            if _metadata(before) != _metadata(after):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            if len(data) > limit:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            return SafePath(data, tuple(metadata), "symlink")
        if stat.S_ISDIR(before.st_mode) and allow_directory:
            return SafePath(None, tuple(metadata), "directory")
        if not stat.S_ISREG(before.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
        if not read_regular:
            return SafePath(None, tuple(metadata), "file")
        fd = _open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent,
        )
        descriptors.append(fd)
        opened = os.fstat(fd)
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
        fd = _open(
            parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current
        )
        descriptors.append(fd)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _metadata(before) != _metadata(opened):
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


def _head_identity(root: str, *, deadline: float) -> bytes:
    """Return HEAD, or Git's canonical empty-tree identity for an unborn branch."""
    try:
        return git_output(
            root, ["rev-parse", "--verify", "HEAD"], deadline=deadline, limit=4096
        ).strip()
    except SourceOracleError as head_error:
        try:
            # A symbolic HEAD with no object is precisely the unborn-branch case.
            git_output(
                root, ["symbolic-ref", "-q", "HEAD"], deadline=deadline, limit=4096
            )
        except SourceOracleError as symbolic_error:
            raise head_error from symbolic_error
        return b"4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # pragma: allowlist secret


def _frame(digest: Any, label: bytes, value: bytes) -> None:
    update = digest.update
    update(len(label).to_bytes(4, "big") + label)
    update(len(value).to_bytes(8, "big") + value)


def _index_entries(root: str, *, deadline: float) -> dict[bytes, bytes]:
    """Return stage-zero blob identities, rejecting conflicts and malformed rows."""
    raw = git_output(
        root,
        ["ls-files", "--stage", "-z"],
        deadline=deadline,
        limit=_MAX_INVENTORY_BYTES,
    )
    entries: dict[bytes, bytes] = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        header, separator, path = row.partition(b"\t")
        fields = header.split(b" ")
        if not separator or not path or len(fields) != 3 or fields[2] != b"0":
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        try:
            int(fields[0], 8)
            int(fields[1], 16)
        except ValueError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        if path in entries:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        entries[path] = header
    if len(entries) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries


def _head_entries(
    root: str, *, deadline: float, head: bytes = b"HEAD"
) -> dict[bytes, bytes]:
    """Return bounded per-path HEAD tree identities for clean-file binding."""
    if head == b"4b825dc642cb6eb9a060e54bf8d69288fbee4904":  # pragma: allowlist secret
        return {}
    raw = git_output(
        root,
        ["ls-tree", "-rz", "--full-tree", os.fsdecode(head)],
        deadline=deadline,
        limit=_MAX_INVENTORY_BYTES,
    )
    entries: dict[bytes, bytes] = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        header, separator, path = row.partition(b"\t")
        fields = header.split(b" ")
        if not separator or not path or len(fields) != 3:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        try:
            int(fields[0], 8)
            int(fields[2], 16)
        except ValueError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        if fields[1] not in (b"blob", b"commit") or path in entries:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        entries[path] = header
    if len(entries) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries


def _tracked_paths(root: str, *, deadline: float) -> list[bytes]:
    """List every tracked worktree path with exact bounded ``git ls-files -z``."""
    raw = git_output(
        root, ["ls-files", "-z"], deadline=deadline, limit=_MAX_INVENTORY_BYTES
    )
    paths = [path for path in raw.split(b"\0") if path]
    if len(paths) > _MAX_WORKTREE_PATHS or len(paths) != len(set(paths)):
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return paths


def _frame_workspace_path(
    digest: Any,
    root: str,
    raw: bytes,
    *,
    deadline: float,
    content_budget: int,
    content_required: bool,
    index_entry: bytes | None,
    head_entry: bytes | None,
) -> int:
    """Frame one no-follow worktree leaf and return its content charge."""
    path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
    is_gitlink = bool(index_entry and index_entry.split(b" ", 1)[0] == b"160000")
    safe = safe_workspace_path(
        root,
        path,
        deadline=deadline,
        limit=content_budget,
        read_regular=content_required and not is_gitlink,
        allow_directory=is_gitlink,
    )
    _frame(digest, b"worktree-path", raw)
    leaf_metadata = safe.metadata[-1:] if safe.kind != "missing" else ()
    ancestor_metadata = (
        safe.metadata[:-1] if safe.kind != "missing" else safe.metadata[:-1]
    )
    for descriptor in ancestor_metadata:
        _frame(digest, b"worktree-ancestor-stat", descriptor)
    if safe.kind == "missing":
        _frame(digest, b"worktree-kind", b"missing")
    else:
        # Frame the complete root-to-leaf no-follow descriptor chain; the leaf
        # retains the historical field order for stable generation identity.
        fields = leaf_metadata[0].split(b",")
        if len(fields) != 6:
            raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH")
        _frame(
            digest,
            b"worktree-stat",
            b",".join((fields[2], fields[0], fields[1], *fields[3:])),
        )
        _frame(digest, b"worktree-kind", safe.kind.encode("ascii"))
    if index_entry is not None:
        _frame(digest, b"index-blob", index_entry)
    _frame(digest, b"HEAD-blob", head_entry or b"missing")
    if safe.kind == "symlink" or (content_required and not is_gitlink):
        data = safe.data or b""
        _frame(digest, b"worktree-content", hashlib.sha256(data).digest())
        return len(data)
    return 0


def oracle_generation(
    project_root: str | None, mode: str = "diff", *, deadline: float | None = None
) -> tuple[str, RootIdentity]:
    """Return a domain-framed generation and the exact canonical root identity."""
    root, identity = canonical_root(project_root)
    if not _supports_nofollow():
        raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")
    end = deadline if deadline is not None else time.monotonic() + 35.0
    digest = hashlib.sha256()
    _frame(digest, b"domain", _FRAME_DOMAIN)
    _frame(digest, b"root", os.fsencode(identity.realpath))
    _frame(digest, b"root-stat", f"{identity.device},{identity.inode}".encode())
    top_level = git_output(
        root, ["rev-parse", "--show-toplevel"], deadline=end, limit=64 * 1024
    ).rstrip(b"\r\n")
    try:
        top_root, top_identity = canonical_root(os.fsdecode(top_level))
    except (UnicodeError, SourceOracleError) as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH") from exc
    if top_root != root or top_identity != identity:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH")
    head = _head_identity(root, deadline=end)
    _frame(digest, b"HEAD", head)
    git_dir = git_output(
        root, ["rev-parse", "--git-dir"], deadline=end, limit=64 * 1024
    ).rstrip(b"\r\n")
    decoded_git_dir = os.fsdecode(git_dir)
    index_path = (
        os.path.join(decoded_git_dir, "index")
        if os.path.isabs(decoded_git_dir)
        else os.path.join(root, decoded_git_dir, "index")
    )
    safe_index = _safe_absolute_regular(
        index_path,
        deadline=end,
        limit=64 * 1024 * 1024,
        allow_missing=head
        == b"4b825dc642cb6eb9a060e54bf8d69288fbee4904",  # pragma: allowlist secret
    )
    for descriptor in safe_index.metadata:
        _frame(digest, b"index-descriptor-stat", descriptor)
    _frame(digest, b"index-kind", safe_index.kind.encode("ascii"))
    index_bytes = safe_index.data or b""
    _frame(digest, b"index-content", hashlib.sha256(index_bytes).digest())
    # Dependency analysis reads the live checkout, not only dirty paths. Bind
    # every tracked path so a transient clean-file write+restore or atomic
    # replacement changes inode/ctime and invalidates the strict result.
    tracked = _tracked_paths(root, deadline=end)
    index_entries = _index_entries(root, deadline=end)
    head_entries = _head_entries(root, deadline=end, head=head)
    if set(tracked) != set(index_entries):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    dirty_raw = git_output(
        root,
        ["diff-files", "--name-only", "-z", "--no-ext-diff"],
        deadline=end,
        limit=_MAX_INVENTORY_BYTES,
    )
    untracked_raw = git_output(
        root,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        deadline=end,
        limit=_MAX_INVENTORY_BYTES,
    )
    dirty = {path for path in dirty_raw.split(b"\0") if path}
    untracked = {path for path in untracked_raw.split(b"\0") if path}
    if len(dirty | untracked) > _MAX_WORKTREE_PATHS:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    tracked_set = set(tracked)
    if not dirty <= tracked_set or untracked & tracked_set:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")

    remaining_content = _MAX_WORKTREE_CONTENT_BYTES
    for raw in sorted(tracked, key=os.fsencode):
        charge = _frame_workspace_path(
            digest,
            root,
            raw,
            deadline=end,
            content_budget=remaining_content,
            content_required=raw in dirty,
            index_entry=index_entries[raw],
            head_entry=head_entries.get(raw),
        )
        remaining_content -= charge
    for raw in sorted(untracked, key=os.fsencode):
        charge = _frame_workspace_path(
            digest,
            root,
            raw,
            deadline=end,
            content_budget=remaining_content,
            content_required=True,
            index_entry=None,
            head_entry=None,
        )
        remaining_content -= charge

    diff_args = ["diff", "--cached"] if mode == "staged" else ["diff-files"]
    diff_args += ["--binary", "--full-index", "--no-ext-diff"]
    patch = git_output(root, diff_args, deadline=end, limit=64 * 1024 * 1024)
    _frame(digest, b"patch", hashlib.sha256(patch).digest())
    return "sg_" + digest.hexdigest(), identity


def source_generation(project_root: str | None, mode: str = "diff") -> str:
    with _LOCK:
        return oracle_generation(project_root, mode)[0]


def capture_consistent(
    project_root: str | None, capture: Callable[[], _T]
) -> tuple[str | None, _T]:
    """Compatibility helper; ctime-inclusive generations reject ordinary ABA writes."""
    with _LOCK:
        before, _ = oracle_generation(project_root)
        value = capture()
        after, _ = oracle_generation(project_root)
    return (before if before == after else None), value
