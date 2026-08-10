"""Bounded qualitative index-lag signal for status compatibility.

This read-only mtime comparison is informational only.  Authoritative snapshot
freshness and completeness never depend on it.
"""

from __future__ import annotations

import os

_LAG_WALK_FILE_CAP = 5000
_LAG_SOURCE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs")
_LAG_SKIP_DIRS = frozenset(
    {
        ".ast-cache",
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


def compute_qualitative_lag(project_root: str, cache_path: str) -> float | None:
    """Compare newest bounded source mtime with the cache mtime, read-only."""
    try:
        db_mtime = os.path.getmtime(cache_path)
    except OSError:
        return None
    newest = _newest_source_mtime(project_root)
    return None if newest is None else max(0.0, newest - db_mtime)


def _newest_source_mtime(project_root: str) -> float | None:
    if not os.path.isdir(project_root):
        return None
    newest: float | None = None
    seen = 0
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [directory for directory in dirs if directory not in _LAG_SKIP_DIRS]
        for filename in files:
            if not filename.endswith(_LAG_SOURCE_EXTS):
                continue
            seen += 1
            if seen > _LAG_WALK_FILE_CAP:
                return newest
            try:
                modified = os.path.getmtime(os.path.join(root, filename))
            except OSError:
                continue
            if newest is None or modified > newest:
                newest = modified
    return newest
