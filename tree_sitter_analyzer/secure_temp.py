"""Secure creation primitives for private temporary files."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable

_LSTAT = os.lstat


def set_private_mode(descriptor: int, path: str) -> None:
    """Set owner-only mode using the descriptor when the platform supports it."""
    fchmod = getattr(os, "fchmod", None)
    if fchmod is not None:
        fchmod(descriptor, 0o600)
    else:
        os.chmod(path, 0o600)


def create_private_temp(
    *,
    prefix: str,
    directory: str,
    mkstemp: Callable[..., tuple[int, str]] = tempfile.mkstemp,
    unlink: Callable[[str], None] = os.unlink,
    require_empty: bool = True,
) -> tuple[int, str]:
    """Create and validate a private regular temp, cleaning every failed attempt."""
    descriptor, path = mkstemp(prefix=prefix, dir=directory)
    try:
        set_private_mode(descriptor, path)
        info = _LSTAT(path)
        if not stat.S_ISREG(info.st_mode) or (require_empty and info.st_size != 0):
            raise OSError("invalid private temporary file")
        return descriptor, path
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        raise
