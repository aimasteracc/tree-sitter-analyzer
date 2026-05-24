"""Tiny SQLite-backed cache for per-file metadata (line counts, etc.).

This cache exists because several agent-facing tools — get_project_summary,
file_health, and others — each independently re-open every source file just
to count newlines. On a 4600-file project that's 4600 fopens per agent call.

The fingerprint is the same one HealthScoreCache uses
``(file_path, mtime_ns, size_bytes)`` so the agent can trust that a cached
line count is still valid if the file hasn't been touched.

Like :class:`HealthScoreCache`, this is a strict best-effort cache: any
sqlite or filesystem failure flips ``enabled`` off and the caller falls
back to the un-cached path. Agents never see a noisy error from it.

agent-ux: pain #2 — overview was 3.8s on every call, dominated by 4600
``open()`` calls just to count newlines.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_meta (
    file_path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    cached_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);
"""


class FileMetaCache:
    """Small SQLite cache for cheap per-file metadata.

    Only line counts today. Schema is deliberately narrow — if a future
    consumer wants more fields, add columns rather than reusing one of the
    existing integer slots.
    """

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        self._project_root = project_root
        self._db_path = db_path or self._default_db_path(project_root)
        self._conn: sqlite3.Connection | None = None
        self._enabled = self._init_db()

    @staticmethod
    def _default_db_path(project_root: str) -> str:
        return str(Path(project_root) / ".ast-cache" / "file_meta.db")

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
            logger.debug("FileMetaCache disabled: %s", exc)
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

    # ---- line-count helpers --------------------------------------------

    def get_line_count(
        self, file_path: str, *, mtime_ns: int, size_bytes: int
    ) -> int | None:
        """Return cached line count iff fingerprint matches; otherwise None.

        The caller passes mtime/size explicitly to save a redundant stat —
        most overview-style tools already stat the file for size info.
        """
        if not self.enabled or self._conn is None:
            return None
        try:
            row = self._conn.execute(
                "SELECT mtime_ns, size_bytes, line_count "
                "FROM file_meta WHERE file_path = ?",
                (file_path,),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        cached_mtime, cached_size, line_count = row
        if cached_mtime != mtime_ns or cached_size != size_bytes:
            return None
        return int(line_count)

    def store_line_count(
        self,
        file_path: str,
        *,
        mtime_ns: int,
        size_bytes: int,
        line_count: int,
    ) -> None:
        if not self.enabled or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO file_meta "
                "(file_path, mtime_ns, size_bytes, line_count) "
                "VALUES (?, ?, ?, ?)",
                (file_path, mtime_ns, size_bytes, line_count),
            )
        except sqlite3.Error as exc:
            logger.debug("FileMetaCache store failed: %s", exc)

    def count_lines(self, file_path: str) -> int:
        """High-level entry point: stat + look up + (read on miss) + store.

        Returns 0 on any I/O error. Designed to be a drop-in replacement
        for the ad-hoc ``_count_lines`` helpers scattered through the codebase.
        """
        try:
            st = os.stat(file_path)
        except OSError:
            return 0
        cached = self.get_line_count(
            file_path, mtime_ns=st.st_mtime_ns, size_bytes=st.st_size
        )
        if cached is not None:
            return cached
        try:
            with open(file_path, encoding="utf-8", errors="replace") as fh:
                lines = sum(1 for _ in fh)
        except OSError:
            return 0
        self.store_line_count(
            file_path,
            mtime_ns=st.st_mtime_ns,
            size_bytes=st.st_size,
            line_count=lines,
        )
        return lines
