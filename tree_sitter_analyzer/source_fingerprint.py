"""Fingerprint of the installed tree-sitter-analyzer source (#1675).

Caches of values that are pure functions of TSA's own code (the MCP tool
definitions, the edge resolutions of a built call graph) are keyed by it, so a
code change can never serve a value computed by other code.

The fingerprint covers the package version, the interpreter version, and the
relative path, byte size and mtime of every ``.py`` file under the package.
``os.scandir`` returns the stat data with the directory listing on Windows, so
no file is opened; a dev checkout's edits change size or mtime and therefore
the key. The result is memoized per process: the source does not change under
a running server in any way the caches could tolerate anyway.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from pathlib import Path

_FORMAT = 1
_LOCK = threading.Lock()
_MEMO: dict[str, str] = {}


def package_dir() -> Path:
    """The installed ``tree_sitter_analyzer`` package directory."""
    return Path(__file__).resolve().parent


def source_fingerprint(root: Path | None = None) -> str:
    """Hex fingerprint of the package source under ``root`` (default: installed)."""
    directory = root or package_dir()
    key = str(directory)
    if root is None:
        with _LOCK:
            cached = _MEMO.get(key)
        if cached is not None:
            return cached
    from . import __version__

    hasher = hashlib.blake2b(digest_size=20)
    hasher.update(f"{_FORMAT}|{__version__}|{sys.version}\n".encode())
    for line in sorted(_entries(directory)):
        hasher.update(line.encode("utf-8") + b"\n")
    fingerprint = hasher.hexdigest()
    if root is None:
        with _LOCK:
            _MEMO[key] = fingerprint
    return fingerprint


def _entries(root: Path) -> list[str]:
    entries: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as scan:
            for entry in scan:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name != "__pycache__":
                        stack.append(Path(entry.path))
                elif entry.name.endswith(".py"):
                    info = entry.stat(follow_symlinks=False)
                    rel = Path(entry.path).relative_to(root).as_posix()
                    entries.append(f"{rel}|{info.st_size}|{info.st_mtime_ns}")
    return entries
