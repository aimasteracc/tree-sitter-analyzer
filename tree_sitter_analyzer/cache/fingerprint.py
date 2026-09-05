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

import hashlib
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from ..constants import EXCLUDE_DIRS, GRAPH_SOURCE_EXTS
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
#
# Sourced from the shared constant so this list can never drift from
# ``project_graph``'s ``supported_exts`` again: an extension the graph indexes
# but the fingerprint ignores means edits to those files never invalidate the
# graph cache. That is exactly how ``.mjs``/``.cjs``/``.mts``/``.cts`` served
# stale dependency and blast-radius answers.
_SOURCE_EXTS: tuple[str, ...] = GRAPH_SOURCE_EXTS


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
        # timeout=10 与 ast_cache.py 的主连接保持一致：多进程共用缓存库时，
        # 无超时的连接遇到写锁会立刻抛 database is locked 而不是等待重试
        conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
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


class SourceTreeDigest(NamedTuple):
    """Order-independent digest of every supported source file's *identity*.

    Why this exists alongside :class:`GraphFingerprint` (review P1-1 / P1-2):
    ``(file_count, max_mtime_ns)`` is a sound invalidation signal for a graph
    rebuilt from content, but it is NOT sound as a memoisation key for an
    answer, because three ordinary operations leave both components unchanged:

    * ``os.rename`` — changes no file's mtime and not the count, only the
      *directory* mtime, which is never stat'd. A rename made a cached
      ``edit action=safe`` report ``verdict=CAUTION, downstream_count=1`` for a
      path that no longer existed, where the live code raises ``File not
      found``. That is a normal mid-refactor ``git mv``.
    * an mtime-preserving replacement (``tar -x``, ``cp -p``, ``rsync
      --times``).
    * any single file bearing a **future** mtime, which pins ``max_mtime_ns``
      ahead of the wall clock and blinds the whole tree until time catches up.

    This digest folds every file's ``(relative path, mtime_ns, size)`` into one
    hash, so a rename changes the path set, a replacement changes the size, and
    a future mtime is confined to its own record instead of dominating a
    maximum.

    It also defaults to the full :data:`EXT_TO_LANG` domain (30 extensions)
    rather than ``GRAPH_SOURCE_EXTS`` (19). Under the narrower set a project
    written in any of ``.cs .kt .lua .php .rb .scala .swift .swiftinterface
    .sh .bash .zsh`` produced a *constant* stamp, so nothing could ever
    invalidate it.

    ``file_count == 0`` is a degenerate observation, not a valid state: a caller
    keying a cache on this MUST fail closed rather than treat it as a stamp.

    **Timestamp granularity.** ``mtime_ns`` has nanosecond *units* but not
    nanosecond *resolution*: measured on Windows, rewriting a file with
    same-size content left ``st_mtime_ns`` byte-identical in **15 of 20**
    trials, and two back-to-back writes reported a delta of exactly 0 ns. So a
    same-size edit — ``x = 1`` -> ``x = 2``, flipping a boolean, an equal-length
    rename — is invisible to a ``(path, mtime, size)`` triple whenever both
    writes land in one filesystem tick. That is an ordinary agent edit, not a
    forgery, so :func:`compute_source_tree_digest` additionally folds in the
    **content hash of the :data:`_CONTENT_HASHED_NEWEST` most-recently-modified
    files**, whose timestamps are the ones that cannot be trusted. Old files
    stay cheap; only the handful just touched are read.

    ``unstable_file_count`` is non-zero when more files than
    :data:`_MAX_SAME_TICK_FILES` share the single newest mtime — a fresh
    checkout stamps every file identically, so there is no small "recently
    touched" set to hash and doing it for all of them would cost more than the
    answer being cached. The digest then declares itself untrustworthy and the
    caller fails closed.
    """

    file_count: int
    digest: str
    unstable_file_count: int = 0

    def is_empty(self) -> bool:
        """Return True when no supported source file was observed."""
        return self.file_count == 0

    def is_trustworthy(self) -> bool:
        """Return True when this digest may be used as a cache key.

        False when nothing was observed, or when too many recently-modified
        files had to be left un-hashed to bound the cost.
        """
        return not self.is_empty() and self.unstable_file_count == 0


def _collect_one_directory(
    path: str,
    prefix_length: int,
    exts: tuple[str, ...],
    stack: list[str],
    records: list[tuple[str, int, int]],
) -> None:
    """Append one ``scandir`` level's file records; push subdirs onto ``stack``.

    Mirrors :func:`_process_entry`'s exclusion rules exactly, so this digest and
    the graph fingerprint describe the same tree.
    """
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                _collect_one_entry(entry, prefix_length, exts, stack, records)
    except OSError:  # nosec B112 — directory vanished mid-walk
        pass


def _collect_one_entry(
    entry: os.DirEntry[str],
    prefix_length: int,
    exts: tuple[str, ...],
    stack: list[str],
    records: list[tuple[str, int, int]],
) -> None:
    """Sort one entry into the recurse stack or the record list.

    The relative path is a slice, not ``os.path.relpath``: the walk starts at
    ``root`` so every ``entry.path`` is already prefixed by it, and relpath's
    parsing cost per file dominated the whole digest (53 ms -> 25 ms on a
    2,382-file tree).
    """
    try:
        if entry.is_dir(follow_symlinks=False):
            if entry.name not in _EXCLUDE_DIRS and not entry.name.startswith("."):
                stack.append(entry.path)
            return
        if entry.name.startswith(".") or not entry.name.endswith(exts):
            return
        stat = entry.stat()
        relative = entry.path[prefix_length:].replace(os.sep, "/")
        records.append((relative, stat.st_mtime_ns, stat.st_size))
    except OSError:  # nosec B110 — file vanished / unreadable mid-walk
        pass


#: How many of the most-recently-modified files also contribute a content hash.
#:
#: Deliberately a *rank* and not a time window. A window (``now - mtime < W``)
#: makes the digest depend on the clock: a file's record silently changes shape
#: as it ages out of the window, so an unchanged tree produces two different
#: digests moments apart and the cache takes a spurious miss. Measured: one
#: 4.8 s recompute inside a warm reservoir that should have been all hits.
#:
#: A rank is a pure function of the tree, so an unchanged tree always digests
#: identically, and the just-edited file — the only one at real risk of a
#: same-tick double write — is by construction in the set.
_CONTENT_HASHED_NEWEST = 16

#: Cost/soundness bound. If more files than this share the single newest mtime,
#: we cannot tell which of them is the risky one (a fresh checkout stamps every
#: file identically), and hashing them all would cost more than the answer being
#: cached. The digest then declares itself untrustworthy and the caller fails
#: closed.
_MAX_SAME_TICK_FILES = _CONTENT_HASHED_NEWEST

#: Never read more than this from one file when hashing content. A prefix is
#: enough to separate two same-size edits in practice, and it bounds the cost of
#: a multi-megabyte generated source file.
_CONTENT_HASH_PREFIX_BYTES = 65536


def _content_digest(path: str) -> str:
    """Hash a bounded prefix of ``path``, or a marker when unreadable."""
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read(_CONTENT_HASH_PREFIX_BYTES)).hexdigest()
    except OSError:
        return "unreadable"


def _hash_newest_records(
    root: str, records: list[tuple[str, int, int]]
) -> tuple[int, dict[str, str]]:
    """Return ``(unstable_count, {relpath: content_digest})`` for the newest files.

    Ranked by ``(mtime_ns, path)`` descending, so the selection depends only on
    the tree and never on the wall clock.
    """
    if not records:
        return 0, {}
    by_recency = sorted(
        records, key=lambda record: (record[1], record[0]), reverse=True
    )
    newest_mtime = by_recency[0][1]
    same_tick = sum(1 for record in by_recency if record[1] == newest_mtime)
    if same_tick > _MAX_SAME_TICK_FILES:
        return same_tick, {}
    contents = {
        relative: _content_digest(os.path.join(root, relative))
        for relative, _mtime_ns, _size in by_recency[:_CONTENT_HASHED_NEWEST]
    }
    return 0, contents


def compute_source_tree_digest(
    project_root: str,
    *,
    extensions: Iterable[str] | None = None,
) -> SourceTreeDigest:
    """Digest ``(relative path, mtime_ns, size)`` for every supported source file.

    Records are sorted before hashing, so the digest does not depend on
    ``os.scandir`` ordering and is stable across processes and platforms.

    The :data:`_CONTENT_HASHED_NEWEST` most-recently-modified files additionally
    contribute a content hash, because a timestamp cannot distinguish two
    same-size writes inside one filesystem tick (see :class:`SourceTreeDigest`).
    The selection is by *rank*, not by a clock window, so an unchanged tree
    always digests identically.
    """
    exts = tuple(extensions) if extensions else tuple(EXT_TO_LANG)
    root = os.path.realpath(project_root)
    prefix_length = len(root) + 1
    records: list[tuple[str, int, int]] = []
    stack: list[str] = [root]
    while stack:
        _collect_one_directory(stack.pop(), prefix_length, exts, stack, records)

    records.sort()
    unstable, contents = _hash_newest_records(root, records)

    hasher = hashlib.sha256()
    for relative, mtime_ns, size in records:
        hasher.update(os.fsencode(relative))
        hasher.update(f"\0{mtime_ns}\0{size}".encode("ascii"))
        content = contents.get(relative)
        if content is not None:
            hasher.update(f"\0{content}".encode("ascii"))
        hasher.update(b"\n")
    return SourceTreeDigest(
        file_count=len(records),
        digest=hasher.hexdigest(),
        unstable_file_count=unstable,
    )
