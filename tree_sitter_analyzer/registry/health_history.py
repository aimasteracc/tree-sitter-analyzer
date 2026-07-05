"""SQLite-backed time-series log of file health scores.

Companion to :class:`HealthScoreCache` — both share the same SQLite DB at
``<project_root>/.ast-cache/health_scores.db`` but operate on different
tables:

- ``health_scores``  (legacy, owned by :class:`HealthScoreCache`)
    Latest-value-per-file fingerprint cache. One row per file.
- ``health_score_history``  (this module)
    Append-only audit log. Many rows per file, one per recompute event.

The split keeps the cache tiny and fast (single-row reads) while letting
this module answer "what was this file's grade last time we looked?"
without the cost of full history reads.

The schema is idempotent (``CREATE TABLE IF NOT EXISTS`` + matching
``CREATE INDEX IF NOT EXISTS``) so opening the DB never destroys the
legacy table.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    computed_at REAL NOT NULL,
    grade TEXT NOT NULL,
    total REAL NOT NULL,
    dimensions_json TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT 'watch'
);
CREATE INDEX IF NOT EXISTS idx_hsh_path_time
    ON health_score_history(file_path, computed_at DESC);
"""


def _default_db_path(project_root: str) -> str:
    cache_dir = Path(project_root) / ".ast-cache"
    return str(cache_dir / "health_scores.db")


class HealthHistory:
    """Append-only history of per-file health scores.

    The store is best-effort: SQLite or filesystem failures are logged
    at DEBUG level and the operations become silent no-ops. Callers
    should not rely on ``append`` for correctness of anything other
    than the history itself.
    """

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        self._project_root = project_root
        self._db_path = db_path or _default_db_path(project_root)
        self._conn: sqlite3.Connection | None = None
        self._enabled = self._init_db()

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
            logger.debug("HealthHistory disabled: %s", exc)
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

    # ---- append --------------------------------------------------------

    def append(
        self,
        file_path: str,
        score: float,
        grade: str,
        *,
        dimensions: dict[str, Any] | None = None,
        trigger: str = "watch",
        computed_at: float | None = None,
    ) -> None:
        """Append a new history row.

        ``dimensions`` defaults to an empty dict. ``computed_at`` defaults
        to ``time.time()``. ``trigger`` is a free-form label
        (``"watch"`` / ``"cli"`` / ``"mcp"``) so cross-source noise can
        be filtered downstream.
        """
        if not self.enabled or self._conn is None:
            return

        dims = dimensions if dimensions is not None else {}
        try:
            dim_json = json.dumps(dims, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError):
            dim_json = "{}"

        ts = computed_at if computed_at is not None else time.time()

        try:
            self._conn.execute(
                "INSERT INTO health_score_history "
                "(file_path, computed_at, grade, total, dimensions_json, trigger) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    file_path,
                    float(ts),
                    str(grade),
                    float(score),
                    dim_json,
                    str(trigger),
                ),
            )
        except sqlite3.Error as exc:
            logger.debug("HealthHistory append failed: %s", exc)

    # ---- read ----------------------------------------------------------

    def last(self, file_path: str) -> tuple[str, float] | None:
        """Return ``(grade, score)`` for the most recent row, or ``None``."""
        if not self.enabled or self._conn is None:
            return None
        try:
            row = self._conn.execute(
                "SELECT grade, total FROM health_score_history "
                "WHERE file_path = ? "
                "ORDER BY computed_at DESC LIMIT 1",
                (file_path,),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return (str(row[0]), float(row[1]))

    # ---- maintenance ---------------------------------------------------

    def prune(self, file_path: str, keep_n: int) -> int:
        """Delete all rows for ``file_path`` except the latest ``keep_n``.

        Returns the number of rows deleted. If fewer than ``keep_n`` rows
        exist, deletes nothing and returns 0.
        """
        if not self.enabled or self._conn is None:
            return 0
        if keep_n < 0:
            keep_n = 0
        try:
            cur = self._conn.execute(
                "DELETE FROM health_score_history "
                "WHERE file_path = ? "
                "AND id NOT IN ("
                "    SELECT id FROM health_score_history "
                "    WHERE file_path = ? "
                "    ORDER BY computed_at DESC LIMIT ?"
                ")",
                (file_path, file_path, int(keep_n)),
            )
            return int(cur.rowcount or 0)
        except sqlite3.Error as exc:
            logger.debug("HealthHistory prune failed: %s", exc)
            return 0
