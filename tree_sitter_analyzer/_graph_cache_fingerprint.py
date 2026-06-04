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
from collections.abc import Iterable
from typing import NamedTuple

from .constants import EXCLUDE_DIRS

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
