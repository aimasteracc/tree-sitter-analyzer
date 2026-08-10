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
from typing import Any, BinaryIO, TypeVar

_LOCK = threading.RLock()
_T = TypeVar("_T")
_FRAME_DOMAIN = b"tsa-source-generation-v2"


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
        info = os.stat(root, follow_symlinks=True)
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_INVALID") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise SourceOracleError("DIFF_SNAPSHOT_ROOT_INVALID")
    return root, RootIdentity(root, info.st_dev, info.st_ino)


def normalize_repo_path(path: str) -> str:
    value = path.replace("\\", "/")
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
        env = os.environ.copy()
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
    root: str, path: str, *, deadline: float, limit: int
) -> SafePath:
    """Read a repo path without following any symlink or accepting special files."""
    normalized = normalize_repo_path(path)
    if os.name == "nt" or not hasattr(os, "O_NOFOLLOW"):
        raise SourceOracleError("DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")
    parts = normalized.split("/")
    flags_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    descriptors: list[int] = []
    metadata: list[bytes] = []
    try:
        current = os.open(root, flags_dir)
        descriptors.append(current)
        metadata.append(_metadata(os.fstat(current)))
        for component in parts[:-1]:
            current = os.open(component, flags_dir, dir_fd=current)
            descriptors.append(current)
            metadata.append(_metadata(os.fstat(current)))
        parent = current
        name = parts[-1]
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return SafePath(None, tuple(metadata + [b"missing"]), "missing")
        metadata.append(_metadata(before))
        if stat.S_ISLNK(before.st_mode):
            target = os.readlink(os.fsencode(name), dir_fd=parent)
            data = target if isinstance(target, bytes) else os.fsencode(target)
            after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if _metadata(before) != _metadata(after):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            if len(data) > limit:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            return SafePath(data, tuple(metadata), "symlink")
        if not stat.S_ISREG(before.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        descriptors.append(fd)
        opened = os.fstat(fd)
        if _metadata(before) != _metadata(opened):
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        buffer = bytearray()
        while True:
            _remaining(deadline)
            chunk = os.read(fd, min(64 * 1024, limit - len(buffer) + 1))
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
                os.close(fd)
            except OSError:
                pass


def _frame(digest: Any, label: bytes, value: bytes) -> None:
    update = digest.update
    update(len(label).to_bytes(4, "big") + label)
    update(len(value).to_bytes(8, "big") + value)


def oracle_generation(
    project_root: str | None, mode: str = "diff", *, deadline: float | None = None
) -> tuple[str, RootIdentity]:
    """Return a domain-framed generation and the exact canonical root identity."""
    root, identity = canonical_root(project_root)
    end = deadline if deadline is not None else time.monotonic() + 35.0
    digest = hashlib.sha256()
    _frame(digest, b"domain", _FRAME_DOMAIN)
    _frame(digest, b"root", os.fsencode(identity.realpath))
    _frame(digest, b"root-stat", f"{identity.device},{identity.inode}".encode())
    _frame(
        digest,
        b"HEAD",
        git_output(root, ["rev-parse", "--verify", "HEAD"], deadline=end, limit=4096),
    )
    git_dir = git_output(
        root, ["rev-parse", "--git-dir"], deadline=end, limit=64 * 1024
    ).rstrip(b"\n")
    index_path = os.path.join(root, os.fsdecode(git_dir), "index")
    try:
        before_index = os.stat(index_path, follow_symlinks=False)
        if not stat.S_ISREG(before_index.st_mode):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        with open(index_path, "rb") as stream:  # index is inside the canonical git dir
            index_bytes = stream.read(64 * 1024 * 1024 + 1)
        after_index = os.stat(index_path, follow_symlinks=False)
        if _metadata(before_index) != _metadata(after_index):
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        if len(index_bytes) > 64 * 1024 * 1024:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        _frame(digest, b"index-stat", _metadata(before_index))
        _frame(digest, b"index-content", hashlib.sha256(index_bytes).digest())
    except SourceOracleError:
        raise
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
    diff_args = ["diff", "--cached"] if mode == "staged" else ["diff-files"]
    diff_args += ["--binary", "--full-index", "--no-ext-diff"]
    if mode == "diff":
        names = git_output(
            root,
            ["diff-files", "--name-only", "-z", "--no-ext-diff"],
            deadline=end,
            limit=8 * 1024 * 1024,
        )
        untracked = git_output(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            deadline=end,
            limit=8 * 1024 * 1024,
        )
        paths = sorted({item for item in (names + untracked).split(b"\0") if item})
        for raw in paths:
            path = normalize_repo_path(raw.decode("utf-8", "surrogateescape"))
            safe = safe_workspace_path(root, path, deadline=end, limit=64 * 1024 * 1024)
            _frame(digest, b"path", raw)
            for item in safe.metadata:
                _frame(digest, b"stat", item)
            _frame(digest, b"kind", safe.kind.encode())
            _frame(digest, b"content", hashlib.sha256(safe.data or b"").digest())
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
