"""Shared fingerprint helper for graph-tool cache invalidation (H4 fix).

CallGraph, DependencyGraph, and SymbolLineage instance caches in
``CodeGraphCallTool``, ``DependencyAnalysisTool``, and ``SymbolLineageTool``
need to invalidate when project source files change in place. The class-level
``DependencyGraph._global_cache`` is keyed off the project-root directory
``mtime``, which only changes when files are added or removed — modifying
a file's content silently returns a stale graph.

This module provides a cheap fingerprint over the project's source files.
On a ~1300-file repo it completes in ~10ms (vs. seconds to rebuild a graph),
so we can safely call it on every tool invocation.

The fingerprint is the tuple ``(file_count, max_mtime_ns)``:

- ``file_count`` flips on add/remove
- ``max_mtime_ns`` flips on any modify-in-place

Both are stable across processes (no in-memory state).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from ..constants import EXCLUDE_DIRS
from ..languages.lang_extension_map import EXT_TO_LANG

# Use the shared exclude set so the fingerprint scope matches the graph walkers
# being invalidated — and, critically, so fingerprinting (which runs BEFORE the
# graph build) also skips build-artifact trees (target/obj/packages/...). Codex
# P2 on #286: previously this had its own list without build dirs, so dependency
# fingerprinting still descended huge build trees and the hang persisted on
# graph/dependency paths. EXCLUDE_DIRS already includes .ast-cache/.tree-sitter-cache.
_EXCLUDE_DIRS: frozenset[str] = EXCLUDE_DIRS

# Source file extensions handled by call_graph + project_graph + most plugins.
# We cast a wide net so the same fingerprint can serve every graph kind.
_SOURCE_EXTS: tuple[str, ...] = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".hxx",
)


class GraphFingerprint(NamedTuple):
    """Cheap stable fingerprint for graph-cache invalidation.

    Two fingerprints compare equal iff the source tree is byte-identical
    in count and last-modify time. False positives (e.g. ``touch`` with no
    content change) are acceptable — we trigger a rebuild that produces
    the same graph, which is wasteful but safe.

    ``mtime_ns`` is used instead of float ``mtime`` to avoid filesystem
    rounding-quantum collisions on systems with millisecond-granular
    timestamps.
    """

    file_count: int
    max_mtime_ns: int

    def is_empty(self) -> bool:
        """Return True when no source files were observed (degenerate)."""
        return self.file_count == 0


def compute_graph_fingerprint(
    project_root: str,
    *,
    extensions: Iterable[str] | None = None,
) -> GraphFingerprint:
    """Fingerprint the project source tree under ``project_root``.

    Walks the tree with ``os.scandir`` (faster than ``rglob``), skipping the
    same excluded directories the graph builders skip. Only files with
    relevant extensions contribute.

    Cost: ~10ms on a 1300-file repo. Safe to call on every tool invocation.

    Parameters
    ----------
    project_root:
        Absolute path to the project's source root.
    extensions:
        Iterable of dotted extensions to fingerprint. Defaults to
        ``_SOURCE_EXTS`` — the union of all supported graph languages.

    Returns
    -------
    GraphFingerprint
        ``(file_count, max_mtime_ns)``. Empty/unreadable trees return
        ``GraphFingerprint(0, 0)``.
    """
    exts = tuple(extensions) if extensions else _SOURCE_EXTS
    file_count = 0
    max_mtime_ns = 0

    stack: list[str] = [project_root]
    while stack:
        path = stack.pop()
        file_count, max_mtime_ns = _walk_one_directory(
            path, exts, stack, file_count, max_mtime_ns
        )

    return GraphFingerprint(file_count=file_count, max_mtime_ns=max_mtime_ns)


def _walk_one_directory(
    path: str,
    exts: tuple[str, ...],
    stack: list[str],
    file_count: int,
    max_mtime_ns: int,
) -> tuple[int, int]:
    """Iterate one ``scandir`` entry list; recurse into subdirs via the stack.

    r37bq (dogfood): extracted from ``compute_graph_fingerprint`` to drop
    nesting from 8 to 4. The OSError branches stay silent (the
    fingerprint is best-effort).
    """
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                file_count, max_mtime_ns = _process_entry(
                    entry, exts, stack, file_count, max_mtime_ns
                )
    except OSError:  # nosec B112 — directory disappeared mid-walk
        pass
    return file_count, max_mtime_ns


def _process_entry(
    entry: os.DirEntry[str],
    exts: tuple[str, ...],
    stack: list[str],
    file_count: int,
    max_mtime_ns: int,
) -> tuple[int, int]:
    """Sort a single entry into recurse-stack or fingerprint accumulator."""
    try:
        if entry.is_dir(follow_symlinks=False):
            if entry.name not in _EXCLUDE_DIRS and not entry.name.startswith("."):
                stack.append(entry.path)
            return file_count, max_mtime_ns
        if not entry.name.startswith(".") and entry.name.endswith(exts):
            stat = entry.stat()
            file_count += 1
            if stat.st_mtime_ns > max_mtime_ns:
                max_mtime_ns = stat.st_mtime_ns
    except OSError:  # nosec B112 — file disappeared / unreadable mid-walk
        # Skip files we can't stat; they don't break the fingerprint.
        pass
    return file_count, max_mtime_ns


def is_ast_index_stale(project_root: str) -> bool:
    """Authoritative, language-complete staleness check for the AST index.

    Queries the ast_index table for every indexed file's recorded mtime_ns
    and compares it against the current on-disk mtime. Returns True if ANY
    indexed file has been modified since it was indexed — regardless of
    language extension. This supersedes the _SOURCE_EXTS-limited
    compute_graph_fingerprint approach for #703.

    Returns False (not stale / unknown) when the index does not exist or
    cannot be read — callers fall back to their existing staleness signal.
    """
    db_path = Path(project_root) / ".ast-cache" / "index.db"
    if not db_path.is_file():
        return False
    root = Path(project_root)
    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        try:
            rows = conn.execute("SELECT file_path, mtime_ns FROM ast_index").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return False

    if not rows:
        return False

    indexed_paths: set[str] = set()
    for file_path, recorded_mtime_ns in rows:
        abs_path, rel_path = _indexed_abs_and_rel_path(root, str(file_path))
        indexed_paths.add(rel_path)
        try:
            current_mtime_ns = abs_path.stat().st_mtime_ns
        except OSError:
            return True
        if current_mtime_ns > recorded_mtime_ns:
            return True
    # #978 Fix 2 (perf): the os.walk below runs on every call (e.g. per lineage
    # execute()) to detect newly-added, not-yet-indexed source files. It is only
    # reached when no indexed file was modified (the cheap mtime loop above
    # short-circuits first), and it itself short-circuits on the first unindexed
    # path. Cross-call memoisation was considered and rejected: it would let a
    # file added between two same-call invocations slip through, trading a
    # correctness guarantee for a micro-optimisation. Left as a single correct
    # walk per call — correctness over premature optimisation.
    for rel_path in _walk_supported_source_paths(root):
        if rel_path not in indexed_paths:
            return True
    return False


def _indexed_abs_and_rel_path(root: Path, file_path: str) -> tuple[Path, str]:
    path = Path(file_path)
    abs_path = path if path.is_absolute() else root / path
    try:
        rel_path = abs_path.relative_to(root).as_posix()
    except ValueError:
        rel_path = path.as_posix()
    return abs_path, rel_path


def _walk_supported_source_paths(root: Path) -> Iterable[str]:
    """Yield project-relative paths accepted by the AST indexer."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            if fname.startswith("."):
                continue
            ext = Path(fname).suffix.lower()
            if ext in EXT_TO_LANG:
                yield (Path(dirpath) / fname).relative_to(root).as_posix()
