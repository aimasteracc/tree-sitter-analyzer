"""Bounded explicit-file evidence for CLI constraint execution."""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

EXPLICIT_CONFIG_BYTE_LIMIT = 1024 * 1024
ExplicitConfigIdentity = tuple[int, int, int, int, int, int, int]
ExplicitConfigEvidence = tuple[bytes, ExplicitConfigIdentity]

# ``st_ctime`` means different things per platform, and only one of them is a
# mutation signal:
#   POSIX   -> inode change time. Bumped by every metadata/content mutation, so
#              it genuinely strengthens the TOCTOU identity.
#   Windows -> file *creation* time. Never bumped by mutating a file, so it adds
#              zero detection power (replacement is already covered by
#              st_dev/st_ino), and `os.stat(path)` and `os.fstat(fd)` do not
#              agree on it: the directory entry and the handle are populated
#              from different sources during creation. Measured 2026-08-19 on
#              Windows 11 / CPython 3.13: creating a file then comparing
#              path-stat to handle-fstat disagreed on st_ctime_ns in 27 of 300
#              trials (9%) with every other field identical.
# Including it on Windows therefore made ``explicit_config_evidence`` fail
# closed on files nobody touched, so `--constraint-file --read-only` reported
# CONSTRAINT_CONFIG_CHANGED at random (~9% per read). Project it only where it
# carries information.
_CTIME_IS_MUTATION_SIGNAL = sys.platform != "win32"


def _identity(info: os.stat_result) -> ExplicitConfigIdentity:
    """Project mutation identity without read-induced access timestamps."""
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns) if _CTIME_IS_MUTATION_SIGNAL else 0,
        int(getattr(info, "st_file_attributes", 0)),
    )


def explicit_config_evidence(
    config_path: Path, deadline: float
) -> ExplicitConfigEvidence:
    """Read stable explicit configuration bytes under a one-MiB deadline budget."""
    before = config_path.stat(follow_symlinks=False)
    before_identity = _identity(before)
    if not stat.S_ISREG(before.st_mode):
        raise OSError("constraint file is not a regular file")
    data = bytearray()
    with config_path.open("rb", buffering=0) as stream:
        opened_identity = _identity(os.fstat(stream.fileno()))
        if opened_identity != before_identity:
            raise OSError("constraint file changed during read")
        while True:
            if time.monotonic() >= deadline:
                raise RuntimeError("CONSTRAINT_CONFIG_DEADLINE")
            chunk = stream.read(
                min(64 * 1024, EXPLICIT_CONFIG_BYTE_LIMIT - len(data) + 1)
            )
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > EXPLICIT_CONFIG_BYTE_LIMIT:
                raise RuntimeError("CONSTRAINT_CONFIG_CAPACITY")
        if _identity(os.fstat(stream.fileno())) != opened_identity:
            raise OSError("constraint file changed during read")
    if _identity(config_path.stat(follow_symlinks=False)) != opened_identity:
        raise OSError("constraint file changed during read")
    return bytes(data), opened_identity
