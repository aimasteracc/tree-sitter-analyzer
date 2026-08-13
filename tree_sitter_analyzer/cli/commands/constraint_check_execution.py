"""Bounded explicit-file evidence for CLI constraint execution."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

EXPLICIT_CONFIG_BYTE_LIMIT = 1024 * 1024
ExplicitConfigIdentity = tuple[int, int, int, int, int, int, int]
ExplicitConfigEvidence = tuple[bytes, ExplicitConfigIdentity]


def _identity(info: os.stat_result) -> ExplicitConfigIdentity:
    """Project mutation identity without read-induced access timestamps."""
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
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
