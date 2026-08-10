"""Process-local source generation oracle shared by frozen primitives.

This is the small P0.2 foundation only.  P0.1 will attach the same opaque
primitive-owned token to index snapshots; callers must not interpret it.
"""

from __future__ import annotations

import hashlib
import subprocess  # nosec B404
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

_LOCK = threading.RLock()
_T = TypeVar("_T")


def _git(root: str, args: list[str]) -> bytes:
    try:
        result = subprocess.run(  # nosec B603
            ["git", *args], cwd=root, capture_output=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return b""
    return result.stdout if result.returncode == 0 else b""


def _generation_unlocked(project_root: str | None) -> str:
    root = str(Path(project_root or ".").resolve())
    digest = hashlib.sha256(b"tsa-source-generation-v1\0")
    digest.update(_git(root, ["rev-parse", "HEAD"]))
    digest.update(_git(root, ["diff", "--cached", "--binary", "--no-ext-diff"]))
    digest.update(_git(root, ["diff", "--binary", "--no-ext-diff"]))
    untracked = _git(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    for raw_path in sorted(p for p in untracked.split(b"\0") if p):
        digest.update(b"U\0" + raw_path + b"\0")
        try:
            digest.update(
                (Path(root) / raw_path.decode("utf-8", "surrogateescape")).read_bytes()
            )
        except OSError:
            digest.update(b"<unavailable>")
    return "sg_" + digest.hexdigest()


def source_generation(project_root: str | None) -> str:
    """Return an opaque token for the repository source state."""
    with _LOCK:
        return _generation_unlocked(project_root)


def capture_consistent(
    project_root: str | None, capture: Callable[[], _T]
) -> tuple[str | None, _T]:
    """Capture an artifact and prove the source did not change around the read."""
    with _LOCK:
        before = _generation_unlocked(project_root)
        value = capture()
        after = _generation_unlocked(project_root)
    return (before if before == after else None), value
