"""Private frozen-index materialization and stage-zero parsing."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .git_subprocess import run_git_bounded
from .source_oracle import SourceOracleError

GitOutput = Callable[..., bytes]
BoundedGit = Callable[..., bytes]


@contextmanager
def private_index_file(
    root: str,
    index_bytes: bytes,
    *,
    mkstemp: Callable[..., tuple[int, str]] = tempfile.mkstemp,
    unlink: Callable[[str], None] = os.unlink,
) -> Iterator[str]:
    """Materialize exact index bytes outside ``root`` with mode 0600."""
    descriptor, path = mkstemp(prefix="tsa-index-")
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
            raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH")
        yield path
    finally:
        try:
            unlink(path)
        except FileNotFoundError:
            pass


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
