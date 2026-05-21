"""Allowlist for writes into the ``.tree-sitter-cache/`` directory.

M13 (round-26 dogfood): a previous session left an orphan source file
(``.tree-sitter-cache/fresh_dog.py``) inside the cache directory. The
directory is meant for *tool-owned metadata only* (the persistent
project index, file-hash snapshot, critical-node list, TOON summary).
Arbitrary source files have no business living there — they confuse
``project-overview``, blow up dependency analysis, and pollute search
indexes that scan everything under the project root.

This module centralizes the allowlist so every cache writer goes
through one chokepoint:

- :func:`assert_cache_path` validates a *fully-resolved* destination
  against the allowed name / extension set and raises ``ValueError``
  for anything outside it. Use this at the top of a writer.
- :func:`is_allowed_cache_path` is the boolean version for callers
  that prefer a soft check (e.g. logging a warning before falling back
  to a safe location).

The allowlist is intentionally narrow — current tool needs only:

* ``project-index.json`` / ``file_hashes.json`` / ``critical_nodes.json``
  (top-level metadata files)
* ``summary.toon`` (compressed project digest)
* anything under ``index/`` or ``metrics/`` subdirectories
* any ``.db`` file (SQLite caches like ``critical_nodes.db``)

If a future feature needs a new file type, add it here with a comment
explaining the use case. *Never* widen the allowlist to ``*`` — that
defeats the whole point of the check.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR_NAME = ".tree-sitter-cache"

# Files writable directly under ``.tree-sitter-cache/``. Add new
# entries with a one-line comment explaining why.
_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "project-index.json",  # ProjectIndexManager persistent index
        "file_hashes.json",  # incremental rebuild fingerprint
        "critical_nodes.json",  # ModificationGuardTool node list
        "summary.toon",  # compressed digest for agent contexts
    }
)

# File *extensions* writable anywhere under ``.tree-sitter-cache/``.
# Keep this list as small as possible — every additional extension
# weakens the orphan-source-file guard the M13 fix exists to provide.
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".db",  # SQLite caches
        ".json",  # metadata files (in subdirs)
        ".toon",  # compressed digests (in subdirs)
    }
)

# Subdirectories that may contain any allowed-extension file.
_ALLOWED_SUBDIRS: frozenset[str] = frozenset(
    {
        "index",  # tool index shards
        "metrics",  # collected metrics snapshots
    }
)


class CachePathError(ValueError):
    """Raised when a write target falls outside the cache allowlist.

    Inherits from ``ValueError`` so the central error sanitizer in
    ``mcp/utils/error_sanitizer.py`` keeps classifying it as a
    validation failure (not an internal bug).
    """


def is_allowed_cache_path(path: Path | str, project_root: Path | str) -> bool:
    """Return True if ``path`` is allowed inside the cache directory.

    The check is lenient: any path *outside* ``.tree-sitter-cache/`` is
    considered allowed (this helper is only the policy for cache-dir
    writes — callers elsewhere should use their own validators).
    """
    p = (
        Path(path).resolve()
        if Path(path).is_absolute()
        else (Path(project_root).resolve() / Path(path)).resolve()
    )
    root = Path(project_root).resolve()
    try:
        rel = p.relative_to(root / CACHE_DIR_NAME)
    except ValueError:
        # Not inside the cache dir — outside this module's policy.
        return True

    name = rel.name
    parts = rel.parts

    # Direct allowlist hit.
    if name in _ALLOWED_FILES and len(parts) == 1:
        return True

    # Subdir allowlist + extension allowlist.
    if len(parts) >= 2 and parts[0] in _ALLOWED_SUBDIRS:
        ext = os.path.splitext(name)[1].lower()
        if ext in _ALLOWED_EXTENSIONS:
            return True

    # Top-level extensions are allowed only for ``.db`` (sqlite caches
    # the tool may put at the root). All other extensions must live
    # inside an allowlisted subdir.
    if len(parts) == 1 and os.path.splitext(name)[1].lower() == ".db":
        return True

    return False


def assert_cache_path(path: Path | str, project_root: Path | str) -> Path:
    """Resolve ``path`` under ``project_root`` and assert it is allowed.

    Returns the resolved :class:`~pathlib.Path` for callers that want
    to use the canonical form. Raises :class:`CachePathError` (a
    ``ValueError``) if the path falls outside the allowlist.
    """
    resolved = (
        Path(path).resolve()
        if Path(path).is_absolute()
        else (Path(project_root).resolve() / Path(path)).resolve()
    )
    if not is_allowed_cache_path(resolved, project_root):
        logger.warning(
            "Refused to write %s — not in %s allowlist", resolved, CACHE_DIR_NAME
        )
        raise CachePathError(
            f"Path {resolved} is not in the {CACHE_DIR_NAME} allowlist. "
            "Cache directory accepts only tool-owned metadata "
            "(project-index.json, file_hashes.json, critical_nodes.json, "
            "summary.toon, *.db, or files under index/ or metrics/)."
        )
    return resolved
