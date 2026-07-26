"""SQLite-backed persistent cache for ``HealthScore`` results.

The cache makes ``HealthScorer.score_project`` fast on warm runs: the first
run scores every file, while subsequent runs reuse scores whose source and
external scoring context are unchanged.

Cache location: ``<project_root>/.ast-cache/health_scores.db``

The cache is best-effort:
- If SQLite is unavailable or the directory cannot be created, scoring
  proceeds without caching (no warning, no failure).
- Stale rows are silently overwritten by ``store``.
- Legacy schemas are migrated in place and their context-free rows miss once.
- ``invalidate_changed`` clears entries whose fingerprint no longer matches
  (called from ``IncrementalSync`` when files change).

The cache deliberately stores no project-aggregate state — it is a pure
per-file score store. Aggregates (grade distribution, etc.) are rebuilt
in-memory each run.

agent-ux: this was the #1 pain on tsa-landing dogfood — full project
health was 130s, warm cache target <2s.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import stat
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_CONTEXT_VERSION = "health-score-v3"
_CONTEXT_COLUMN = "context_fingerprint"
_MAX_GIT_METADATA_BYTES = 64 * 1024
_MAX_SYMBOLIC_REF_DEPTH = 16
_SECONDS_PER_DAY = 24 * 60 * 60
_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_scores (
    file_path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    total REAL NOT NULL,
    grade TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    context_fingerprint TEXT NOT NULL,
    cached_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_health_scores_mtime ON health_scores(mtime_ns);
"""


@dataclass(frozen=True)
class _Fingerprint:
    """File-system fingerprint used to detect staleness without re-reading."""

    mtime_ns: int
    size_bytes: int

    @classmethod
    def from_path(cls, path: str) -> _Fingerprint | None:
        try:
            st = os.stat(path)
        except OSError:
            return None
        return cls(mtime_ns=st.st_mtime_ns, size_bytes=st.st_size)


def _metadata_signature(path: Path) -> str:
    """Return a bounded stat signature without following or reading metadata."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return f"{path.absolute()}:missing"
    except OSError:
        return f"{path.absolute()}:unreadable"

    file_type = "regular" if stat.S_ISREG(metadata.st_mode) else "special"
    return ":".join(
        (
            str(path.absolute()),
            file_type,
            str(metadata.st_mode),
            str(metadata.st_dev),
            str(metadata.st_ino),
            str(metadata.st_size),
            str(metadata.st_mtime_ns),
            str(metadata.st_ctime_ns),
        )
    )


def _coverage_metadata_signature(path: Path) -> str:
    """Fingerprint a coverage candidate and a regular symlink target."""
    signature = _metadata_signature(path)
    try:
        link_metadata = path.lstat()
    except OSError:
        return signature
    if not stat.S_ISLNK(link_metadata.st_mode):
        return signature
    try:
        target_metadata = path.stat()
    except OSError:
        return f"{signature}:target-unavailable"
    if not stat.S_ISREG(target_metadata.st_mode):
        return f"{signature}:target-special"
    return ":".join(
        (
            signature,
            "target-regular",
            str(target_metadata.st_mode),
            str(target_metadata.st_dev),
            str(target_metadata.st_ino),
            str(target_metadata.st_size),
            str(target_metadata.st_mtime_ns),
            str(target_metadata.st_ctime_ns),
        )
    )


def _read_small_regular_text(path: Path) -> str | None:
    """Read bounded Git metadata without following links or special files."""
    try:
        path_metadata = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(path_metadata.st_mode):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None
        if metadata.st_size > _MAX_GIT_METADATA_BYTES:
            return None
        content = os.read(descriptor, _MAX_GIT_METADATA_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(descriptor)
    if len(content) > _MAX_GIT_METADATA_BYTES:
        return None
    return content.decode("utf-8", errors="replace").strip()


def _coverage_context_parts() -> list[str]:
    """Fingerprint every report candidate used by ``HealthScorer``."""
    search_dirs = [Path.cwd(), *Path.cwd().parents[:3]]
    return [
        _coverage_metadata_signature(search_dir / file_name)
        for search_dir in search_dirs
        for file_name in ("coverage.json", ".coverage")
    ]


def _find_git_dir(project_root: Path) -> Path | None:
    """Resolve a repository or worktree git directory without spawning git."""
    try:
        resolved_root = project_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    for root in (resolved_root, *resolved_root.parents):
        marker = root / ".git"
        try:
            marker_stat = marker.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return None
        if stat.S_ISDIR(marker_stat.st_mode):
            return marker
        if not stat.S_ISREG(marker_stat.st_mode):
            return None
        pointer = _read_small_regular_text(marker)
        if pointer is None:
            return None
        try:
            prefix, value = pointer.split(":", 1)
        except ValueError:
            return None
        if prefix != "gitdir":
            return None
        try:
            return (root / value.strip()).resolve(strict=True)
        except (OSError, RuntimeError):
            return None
    return None


def _git_context_parts(git_dir: Path | None) -> list[str]:
    """Fingerprint HEAD, its loose ref, and packed refs for hotspot scoring."""
    if git_dir is None:
        return ["git:missing"]
    common_dir = git_dir
    common_marker = git_dir / "commondir"
    common_value = _read_small_regular_text(common_marker)
    if common_value:
        try:
            common_dir = (git_dir / common_value).resolve(strict=True)
        except (OSError, RuntimeError):
            return ["git:missing"]

    head = git_dir / "HEAD"
    parts = [
        _metadata_signature(head),
        _metadata_signature(common_dir / "packed-refs"),
        _metadata_signature(common_dir / "shallow"),
    ]
    head_value = _read_small_regular_text(head)
    if head_value is None:
        return parts
    parts.extend(_symbolic_ref_context_parts(common_dir, head_value))
    return parts


def _symbolic_ref_context_parts(common_dir: Path, value: str) -> list[str]:
    """Fingerprint a bounded, non-following chain of loose symbolic refs."""
    parts: list[str] = []
    seen: set[str] = set()
    current = value
    for _ in range(_MAX_SYMBOLIC_REF_DEPTH):
        if not current.startswith("ref: "):
            return parts
        ref_name = current.removeprefix("ref: ").strip()
        ref_path = Path(ref_name)
        if (
            not ref_name.startswith("refs/")
            or ref_path.is_absolute()
            or ".." in ref_path.parts
        ):
            return [*parts, "git:invalid-symbolic-ref"]
        if ref_name in seen:
            return [*parts, "git:symbolic-ref-loop"]
        seen.add(ref_name)
        loose_ref = common_dir / ref_path
        parts.append(_metadata_signature(loose_ref))
        next_value = _read_small_regular_text(loose_ref)
        if next_value is None:
            return parts
        current = next_value
    return [*parts, "git:symbolic-ref-depth"]


def _day_bucket(timestamp: float | None = None) -> int:
    """Return a UTC day bucket that bounds the moving hotspot window."""
    current = time.time() if timestamp is None else timestamp
    return int(current // _SECONDS_PER_DAY)


def _base_score_context_digest(weights: Mapping[str, float] | None) -> str:
    """Hash project-wide non-source inputs that can change a score."""
    serialized_weights = json.dumps(
        sorted((weights or {}).items()),
        separators=(",", ":"),
    )
    parts = [
        _CACHE_CONTEXT_VERSION,
        f"cwd:{Path.cwd().resolve()}",
        f"day:{_day_bucket()}",
        f"weights:{serialized_weights}",
        *_coverage_context_parts(),
    ]
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


class HealthScoreCache:
    """Per-file persistent cache for :class:`HealthScore` instances.

    The cache must remain crash-safe (we use SQLite's default journaling
    via WAL) and must not raise on a corrupted or missing DB — callers
    treat any cache failure as a miss and proceed to score normally.
    """

    def __init__(
        self,
        project_root: str,
        db_path: str | None = None,
        *,
        weights: Mapping[str, float] | None = None,
    ) -> None:
        self._project_root = project_root
        self._db_path = db_path or self._default_db_path(project_root)
        self._base_context_digest = _base_score_context_digest(weights)
        self._git_context_cache: dict[Path | None, str] = {}
        self._conn: sqlite3.Connection | None = None
        self._enabled = self._init_db()

    def _context_for_file(self, file_path: str) -> str:
        """Combine project context with the repository governing one file."""
        try:
            source_parent = Path(file_path).resolve(strict=True).parent
        except (OSError, RuntimeError):
            source_parent = Path(file_path).absolute().parent
        git_dir = _find_git_dir(source_parent)
        git_digest = self._git_context_cache.get(git_dir)
        if git_digest is None:
            git_parts = _git_context_parts(git_dir)
            git_digest = hashlib.sha256("\0".join(git_parts).encode()).hexdigest()
            self._git_context_cache[git_dir] = git_digest
        return hashlib.sha256(
            f"{self._base_context_digest}\0{git_digest}".encode()
        ).hexdigest()

    @staticmethod
    def _default_db_path(project_root: str) -> str:
        cache_dir = Path(project_root) / ".ast-cache"
        return str(cache_dir / "health_scores.db")

    def _init_db(self) -> bool:
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._ensure_context_column()
            return True
        except (OSError, sqlite3.Error) as exc:
            logger.debug("HealthScoreCache disabled: %s", exc)
            self._conn = None
            return False

    def _ensure_context_column(self) -> None:
        """Migrate context-free cache databases without losing the table."""
        if self._conn is None:
            return
        columns = {
            str(row[1])
            for row in self._conn.execute("PRAGMA table_info(health_scores)")
        }
        if _CONTEXT_COLUMN in columns:
            return
        try:
            self._conn.execute(
                "ALTER TABLE health_scores "
                "ADD COLUMN context_fingerprint TEXT NOT NULL DEFAULT ''"
            )
        except sqlite3.OperationalError:
            migrated_columns = {
                str(row[1])
                for row in self._conn.execute("PRAGMA table_info(health_scores)")
            }
            if _CONTEXT_COLUMN not in migrated_columns:
                raise

    @property
    def enabled(self) -> bool:
        return self._enabled and self._conn is not None

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                self._enabled = False

    # ---- read path -----------------------------------------------------

    def lookup(self, file_path: str) -> dict[str, Any] | None:
        """Return cached score dict iff the on-disk fingerprint still matches.

        Returns ``None`` on miss, stale entry, or any cache error.
        The returned dict matches :meth:`HealthScore.to_dict` so callers can
        rebuild a :class:`HealthScore` directly via dataclass construction.
        """
        if not self.enabled or self._conn is None:
            return None

        fp = _Fingerprint.from_path(file_path)
        if fp is None:
            return None

        try:
            row = self._conn.execute(
                "SELECT mtime_ns, size_bytes, total, grade, dimensions_json, "
                "context_fingerprint "
                "FROM health_scores WHERE file_path = ?",
                (file_path,),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None

        cached_mtime, cached_size, total, grade, dim_json, context = row
        if cached_mtime != fp.mtime_ns or cached_size != fp.size_bytes:
            return None
        if context != self._context_for_file(file_path):
            return None

        try:
            dimensions = json.loads(dim_json)
        except (TypeError, ValueError):
            return None

        return {
            "file_path": file_path,
            "total": total,
            "grade": grade,
            "dimensions": dimensions,
        }

    # ---- write path ----------------------------------------------------

    def store(self, score: Any) -> None:
        """Persist a :class:`HealthScore` keyed by current fingerprint.

        ``score`` is a duck-typed HealthScore (has ``file_path``, ``total``,
        ``grade``, ``dimensions``). The caller is responsible for invoking
        this only on successful scores; failed/empty scores are skipped.
        """
        if not self.enabled or self._conn is None:
            return

        file_path = getattr(score, "file_path", None)
        if not file_path:
            return
        fp = _Fingerprint.from_path(file_path)
        if fp is None:
            return

        dimensions = getattr(score, "dimensions", {}) or {}
        try:
            dim_json = json.dumps(dimensions, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError):
            return

        values = (
            file_path,
            fp.mtime_ns,
            fp.size_bytes,
            float(getattr(score, "total", 0.0)),
            str(getattr(score, "grade", "F")),
            dim_json,
            self._context_for_file(file_path),
        )
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO health_scores "
                "(file_path, mtime_ns, size_bytes, total, grade, dimensions_json, "
                "context_fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?)",
                values,
            )
        except sqlite3.Error as exc:
            logger.debug("HealthScoreCache store failed: %s", exc)

    # ---- maintenance ---------------------------------------------------

    def invalidate(self, file_path: str) -> bool:
        """Remove an explicit entry; returns True iff a row was deleted."""
        if not self.enabled or self._conn is None:
            return False
        try:
            cur = self._conn.execute(
                "DELETE FROM health_scores WHERE file_path = ?", (file_path,)
            )
            return cur.rowcount > 0
        except sqlite3.Error:
            return False

    def stats(self) -> dict[str, Any]:
        if not self.enabled or self._conn is None:
            return {"enabled": False, "entries": 0}
        try:
            row = self._conn.execute(
                "SELECT COUNT(*), MAX(cached_at) FROM health_scores"
            ).fetchone()
        except sqlite3.Error:
            return {"enabled": True, "entries": 0}
        return {
            "enabled": True,
            "entries": int(row[0] or 0),
            "last_cached_at": row[1],
            "db_path": self._db_path,
        }
