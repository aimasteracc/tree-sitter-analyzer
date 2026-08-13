"""Bounded explicit-file evidence for CLI constraint execution."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

EXPLICIT_CONFIG_BYTE_LIMIT = 1024 * 1024


def explicit_config_evidence(
    config_path: Path, deadline: float
) -> tuple[bytes, os.stat_result]:
    """Read stable explicit configuration bytes under a one-MiB deadline budget."""
    before = config_path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise OSError("constraint file is not a regular file")
    data = bytearray()
    with config_path.open("rb", buffering=0) as stream:
        opened = os.fstat(stream.fileno())
        if opened != before:
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
        if os.fstat(stream.fileno()) != opened:
            raise OSError("constraint file changed during read")
    if config_path.stat(follow_symlinks=False) != opened:
        raise OSError("constraint file changed during read")
    return bytes(data), opened
