"""Fail-closed bounded cleanup for private frozen-capture artifacts."""

from __future__ import annotations

import os
import shutil
import stat
import time
from collections.abc import Callable

from .source_oracle import SourceOracleError

_UNLINK = os.unlink
_RMTREE = shutil.rmtree
_CHMOD = os.chmod
_SLEEP = time.sleep
_RETRIES = 3
_RETRY_DELAY = 0.02


def _make_writable(path: str, *, directory: bool) -> None:
    targets = [path]
    if directory:
        try:
            for base, dirs, files in os.walk(path):
                targets.extend(os.path.join(base, name) for name in dirs + files)
        except OSError:
            pass
    for target in reversed(targets):
        try:
            _CHMOD(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except OSError:
            pass


def cleanup_path(
    path: str,
    *,
    directory: bool = False,
    unlink: Callable[[str], None] | None = None,
) -> None:
    """Remove one artifact with chmod-and-retry, or raise a stable failure."""
    remove: Callable[[str], None]
    if directory:
        remove = _RMTREE
    elif unlink is not None:
        remove = unlink
    else:
        remove = _UNLINK
    for attempt in range(_RETRIES):  # pragma: no branch - body always returns or raises
        try:
            remove(path)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            if attempt + 1 == _RETRIES:
                raise SourceOracleError("DIFF_SNAPSHOT_CLEANUP_FAILED") from exc
            _make_writable(path, directory=directory)
            _SLEEP(_RETRY_DELAY)
