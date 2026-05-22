"""SQLite-backed persistent cache for ``HealthScore`` results.

The cache makes ``HealthScorer.score_project`` fast on warm runs:
first run scores every file (the slow path), subsequent runs reuse
cached scores for files whose ``(mtime_ns, size_bytes)`` fingerprint is
unchanged. This is the same staleness model used by ``ASTCache``.

Cache location: ``<project_root>/.ast-cache/health_scores.db``

The cache is best-effort:
- If SQLite is unavailable or the directory cannot be created, scoring
  proceeds without caching (no warning, no failure).
- Stale rows are silently overwritten by ``store``.
- ``invalidate_changed`` clears entries whose fingerprint no longer matches
  (called from ``IncrementalSync`` when files change).

The cache deliberately stores no project-aggregate state — it is a pure
per-file score store. Aggregates (grade distribution, etc.) are rebuilt
in-memory each run, which keeps the schema trivial and migration-free.

agent-ux: this was the #1 pain on tsa-landing dogfood — full project
health was 130s, warm cache target <2s.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_scores (
    file_path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    total REAL NOT NULL,
    grade TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
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


class HealthScoreCache:
    """Per-file persistent cache for :class:`HealthScore` instances.

    The cache must remain crash-safe (we use SQLite's default journaling
    via WAL) and must not raise on a corrupted or missing DB — callers
    treat any cache failure as a miss and proceed to score normally.
    """

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        self._project_root = project_root
        self._db_path = db_path or self._default_db_path(project_root)
        self._conn: sqlite3.Connection | None = None
        self._enabled = self._init_db()

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
            return True
        except (OSError, sqlite3.Error) as exc:
            logger.debug("HealthScoreCache disabled: %s", exc)
            self._conn = None
            return False

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
                "SELECT mtime_ns, size_bytes, total, grade, dimensions_json "
                "FROM health_scores WHERE file_path = ?",
                (file_path,),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None

        cached_mtime, cached_size, total, grade, dim_json = row
        if cached_mtime != fp.mtime_ns or cached_size != fp.size_bytes:
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

        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO health_scores "
                "(file_path, mtime_ns, size_bytes, total, grade, dimensions_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    file_path,
                    fp.mtime_ns,
                    fp.size_bytes,
                    float(getattr(score, "total", 0.0)),
                    str(getattr(score, "grade", "F")),
                    dim_json,
                ),
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


def score_to_dict(score: Any) -> dict[str, Any]:
    """Best-effort serialize a HealthScore into the cache row schema."""
    try:
        return asdict(score)
    except TypeError:
        return {
            "file_path": getattr(score, "file_path", ""),
            "total": getattr(score, "total", 0.0),
            "grade": getattr(score, "grade", "F"),
            "dimensions": getattr(score, "dimensions", {}),
        }
