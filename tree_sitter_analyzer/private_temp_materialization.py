"""Capacity-reserved private temporary file materialization."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable

from .secure_temp import set_private_mode
from .source_oracle import SourceOracleError
from .temp_cleanup import cleanup_path

Reservation = Callable[[int, int], None]


def _failed(path: str, size: int, created: bool, rollback: Reservation) -> None:
    try:
        if created:
            cleanup_path(path, directory=False)
    finally:
        rollback(size, 1)


def write_private(
    path: str, data: bytes, reserve: Reservation, rollback: Reservation
) -> None:
    size = len(data)
    reserve(size, 1)
    created = False
    try:
        with open(path, "xb") as stream:
            created = True
            set_private_mode(stream.fileno(), path)
            if stream.write(data) != size:
                raise OSError("short temporary write")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        _failed(path, size, created, rollback)
        raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR") from exc


def copy_private(
    source: str, destination: str, reserve: Reservation, rollback: Reservation
) -> None:
    try:
        size = os.lstat(source).st_size
    except OSError as exc:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR") from exc
    reserve(size, 1)
    created = False
    try:
        with (
            open(source, "rb") as source_stream,
            open(destination, "xb") as destination_stream,
        ):
            created = True
            set_private_mode(destination_stream.fileno(), destination)
            shutil.copyfileobj(source_stream, destination_stream)
            destination_stream.flush()
            os.fsync(destination_stream.fileno())
    except OSError as exc:
        _failed(destination, size, created, rollback)
        raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR") from exc
