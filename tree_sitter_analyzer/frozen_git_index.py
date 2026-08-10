"""Private frozen-index materialization and stage-zero parsing."""

from __future__ import annotations

import hashlib
import os
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .git_subprocess import run_git_bounded
from .source_oracle import SourceOracleError
from .temp_cleanup import cleanup_path

GitOutput = Callable[..., bytes]
BoundedGit = Callable[..., bytes]


def git_filtered_oid(root: str, raw: bytes, data: bytes, *, deadline: float) -> bytes:
    """Return Git's cleaned blob identity for exact raw repository path bytes."""
    oid = run_git_bounded(
        root,
        ["hash-object", "--path=" + os.fsdecode(raw), "--stdin"],
        deadline=deadline,
        limit=4096,
        input_=data,
    ).strip()
    try:
        int(oid, 16)
    except ValueError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
    if len(oid) not in (40, 64):
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return oid


def safe_external_temp_parent(root: str) -> str:
    """Select an existing writable temporary parent outside the project."""
    real_root = os.path.realpath(root)
    candidates: list[str] = []
    for name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            candidates.append(value)
    if os.name == "nt":
        candidates.extend((r"C:\Windows\Temp", tempfile.gettempdir()))
    else:
        candidates.extend(("/var/tmp", "/tmp"))  # nosec B108
    seen: set[str] = set()
    for candidate in candidates:
        real_candidate = os.path.realpath(candidate)
        if real_candidate in seen:
            continue
        seen.add(real_candidate)
        try:
            inside = os.path.commonpath((real_root, real_candidate)) == real_root
        except ValueError:
            inside = False
        if (
            not inside
            and os.path.isabs(real_candidate)
            and os.path.isdir(real_candidate)
            and os.access(real_candidate, os.W_OK | os.X_OK)
        ):
            return real_candidate
    raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")


@contextmanager
def private_index_file(
    root: str,
    index_bytes: bytes,
    *,
    mkstemp: Callable[..., tuple[int, str]] = tempfile.mkstemp,
    unlink: Callable[[str], None] = os.unlink,
) -> Iterator[str]:
    """Materialize exact index bytes outside ``root`` with mode 0600."""
    temp_parent = safe_external_temp_parent(root)
    descriptor, path = mkstemp(prefix="tsa-index-", dir=temp_parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(index_bytes)
        real_root = os.path.realpath(root)
        try:
            inside_root = (
                os.path.commonpath((real_root, os.path.realpath(path))) == real_root
            )
        except ValueError:
            inside_root = False
        if inside_root:
            raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")
        yield path
    finally:
        cleanup_path(path, unlink=unlink)


@contextmanager
def reconstructed_index_file(
    root: str,
    entries: dict[bytes, bytes],
    *,
    deadline: float,
) -> Iterator[str]:
    """Build a plain private index from captured stage-zero identities."""
    temp_parent = safe_external_temp_parent(root)
    descriptor, path = tempfile.mkstemp(
        prefix="tsa-reconstructed-index-", dir=temp_parent
    )
    os.close(descriptor)
    cleanup_path(path)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    env.update({"GIT_INDEX_FILE": path, "GIT_OPTIONAL_LOCKS": "0"})
    try:
        run_git_bounded(
            root, ["read-tree", "--empty"], deadline=deadline, limit=4096, env=env
        )
        payload = bytearray()
        for raw_path, header in sorted(entries.items()):
            mode, oid, stage = header.split(b" ")
            if stage != b"0":
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            payload.extend(mode + b" " + oid + b"\t" + raw_path + b"\0")
        if payload:
            run_git_bounded(
                root,
                ["update-index", "-z", "--index-info"],
                deadline=deadline,
                limit=4096,
                env=env,
                input_=bytes(payload),
            )
        os.chmod(path, 0o600)
        yield path
    finally:
        cleanup_path(path)


def invalidate_index_stat_cache(
    index_bytes: bytes, *, object_format: str, assume_valid: bool = False
) -> bytes:
    """Derive an index with forced checks, or frozen assume-valid entries."""
    hash_size = 32 if object_format == "sha256" else 20
    version = int.from_bytes(index_bytes[4:8], "big")
    count = int.from_bytes(index_bytes[8:12], "big")
    content_end = len(index_bytes) - hash_size
    result = bytearray(index_bytes)
    offset = 12
    flags_offset = 40 + hash_size
    for _ in range(count):
        start = offset
        if offset + flags_offset + 2 > content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        flags = int.from_bytes(
            index_bytes[offset + flags_offset : offset + flags_offset + 2], "big"
        )
        if assume_valid:
            result[offset + flags_offset : offset + flags_offset + 2] = (
                flags | 0x8000
            ).to_bytes(2, "big")
        else:
            result[offset : offset + 24] = b"\0" * 24
            result[offset + 28 : offset + 40] = b"\0" * 12
        offset += flags_offset + 2 + (2 if flags & 0x4000 else 0)
        if version == 4:
            while offset < content_end and index_bytes[offset] & 0x80:
                offset += 1
            offset += 1
        terminator = index_bytes.find(b"\0", offset, content_end)
        if terminator < 0:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        offset = terminator + 1
        if version in (2, 3):
            offset = start + ((offset - start + 7) & ~7)
    digest = hashlib.sha256 if object_format == "sha256" else hashlib.sha1
    result[-hash_size:] = digest(result[:-hash_size]).digest()
    return bytes(result)


def frozen_index_output(
    root: str,
    index_bytes: bytes,
    args: list[str],
    *,
    deadline: float,
    limit: int,
    refresh: bool = False,
    object_format: str = "sha1",
    input_: bytes | None = None,
    extra_env: dict[str, str] | None = None,
) -> bytes:
    """Run Git against an external mode-0600 byte-for-byte index snapshot."""
    materialized = (
        invalidate_index_stat_cache(index_bytes, object_format=object_format)
        if refresh and index_bytes
        else index_bytes
    )
    context = (
        private_index_file(root, materialized)
        if index_bytes
        else reconstructed_index_file(root, {}, deadline=deadline)
    )
    with context as index_path:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        env.update({"GIT_INDEX_FILE": index_path, "GIT_OPTIONAL_LOCKS": "0"})
        if extra_env is not None:
            env.update(extra_env)
        return run_git_bounded(
            root, args, deadline=deadline, limit=limit, env=env, input_=input_
        )


def reject_frozen_filters(
    root: str,
    index_bytes: bytes,
    paths: tuple[bytes, ...],
    deadline: float,
    object_format: str,
) -> None:
    """Reject active filters resolved against the captured index environment."""
    from .frozen_git_settings import reject_active_filters

    path_input = b"".join(path + b"\0" for path in paths)
    raw = frozen_index_output(
        root,
        index_bytes,
        ["check-attr", "-z", "filter", "--stdin"],
        deadline=deadline,
        limit=16 * 1024 * 1024,
        input_=path_input,
        object_format=object_format,
    )
    reject_active_filters(raw, paths)


def parse_stage_zero_entries(raw: bytes, *, max_paths: int) -> dict[bytes, bytes]:
    """Parse a bounded ``git ls-files --stage -z`` response."""
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
    if len(entries) > max_paths:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries


def has_split_index(index_bytes: bytes, *, object_format: str) -> bool:
    """Return whether an exact Git index contains the split-index ``link`` extension."""
    hash_size = 32 if object_format == "sha256" else 20
    if len(index_bytes) < 12 + hash_size or index_bytes[:4] != b"DIRC":
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    version = int.from_bytes(index_bytes[4:8], "big")
    if version not in (2, 3, 4):
        raise SourceOracleError("DIFF_SNAPSHOT_UNSUPPORTED_INDEX")
    count = int.from_bytes(index_bytes[8:12], "big")
    offset = 12
    flags_offset = 40 + hash_size
    content_end = len(index_bytes) - hash_size
    for _ in range(count):
        start = offset
        if offset + flags_offset + 2 > content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        flags = int.from_bytes(
            index_bytes[offset + flags_offset : offset + flags_offset + 2], "big"
        )
        offset += flags_offset + 2
        if flags & 0x4000:
            if version < 3 or offset + 2 > content_end:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            offset += 2
        if version == 4:
            while True:
                if offset >= content_end:
                    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
                value = index_bytes[offset]
                offset += 1
                if not value & 0x80:
                    break
        terminator = index_bytes.find(b"\0", offset, content_end)
        if terminator < 0:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        offset = terminator + 1
        if version in (2, 3):
            offset = start + ((offset - start + 7) & ~7)
    while offset < content_end:
        if offset + 8 > content_end:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        signature = index_bytes[offset : offset + 4]
        size = int.from_bytes(index_bytes[offset + 4 : offset + 8], "big")
        offset += 8
        if size > content_end - offset:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        if signature == b"link":
            return True
        offset += size
    if offset != content_end:  # pragma: no cover - loop arithmetic invariant
        raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
    return False


def frozen_index_entries(
    root: str,
    *,
    deadline: float,
    max_inventory_bytes: int,
    max_paths: int,
    index_bytes: bytes | None = None,
    git_output_fn: GitOutput,
    bounded_git_fn: BoundedGit = run_git_bounded,
    popen: object = subprocess.Popen,
    mkstemp: Callable[..., tuple[int, str]] = tempfile.mkstemp,
    unlink: Callable[[str], None] = os.unlink,
) -> dict[bytes, bytes]:
    """Read stage-zero entries from the live or an exact frozen index."""
    args = ["ls-files", "--stage", "-z"]
    if index_bytes is None:
        raw = git_output_fn(root, args, deadline=deadline, limit=max_inventory_bytes)
    else:
        if not index_bytes:
            return {}
        with private_index_file(
            root, index_bytes, mkstemp=mkstemp, unlink=unlink
        ) as temporary_index:
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.upper().startswith("GIT_")
            }
            env.update({"GIT_INDEX_FILE": temporary_index, "GIT_OPTIONAL_LOCKS": "0"})
            raw = bounded_git_fn(
                root,
                args,
                deadline=deadline,
                limit=max_inventory_bytes,
                env=env,
                popen=popen,
            )
    return parse_stage_zero_entries(raw, max_paths=max_paths)
