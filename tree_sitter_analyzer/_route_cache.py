# mypy: disable-error-code="no-any-return"
"""SQLite-backed per-file cache of detected routes — content-hash keyed.

PERF-1: makes RouteDetector.detect_all() warm-pass effectively free
(no parsing, single SELECT per file).

Split out of route_detector.py to keep that module under the project's
500-line file-size cap.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROUTE_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS route_cache (
    file_path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    routes_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_route_cache_hash
    ON route_cache(content_hash);
"""


class RouteCache:
    """SQLite-backed cache for per-file route detection.

    Keyed by ``file_path`` with ``content_hash`` as the freshness check.
    A hit reuses stored routes without re-parsing; a miss re-parses and
    refreshes the row. Thread-local connection so the same instance is
    safe to share across threads.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self._conn() as conn:
            conn.executescript(_ROUTE_CACHE_SCHEMA)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @staticmethod
    def _hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def freshness_key(self, file_path: str) -> tuple[str, int] | None:
        """Return ``(content_hash, mtime_ns)`` for the file, or ``None`` on read error."""
        try:
            stat = os.stat(file_path)
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError:
            return None
        return self._hash(content), int(stat.st_mtime_ns)

    def get(self, file_path: str, content_hash: str) -> list[dict[str, Any]] | None:
        row = self._conn().execute(
            "SELECT routes_json FROM route_cache WHERE file_path = ? AND content_hash = ?",
            (file_path, content_hash),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["routes_json"])
        return payload if isinstance(payload, list) else None

    def get_by_stat(
        self, file_path: str, mtime_ns: int
    ) -> list[dict[str, Any]] | None:
        """Fast path: trust the OS mtime as the freshness signal, skipping
        the file read + SHA-256 hash on the warm path. Returns None on a
        mtime miss or absent row — caller then falls back to ``get()`` with
        the full content hash.
        """
        row = self._conn().execute(
            "SELECT routes_json FROM route_cache WHERE file_path = ? AND mtime_ns = ?",
            (file_path, mtime_ns),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["routes_json"])
        return payload if isinstance(payload, list) else None

    def stat_mtime(self, file_path: str) -> int | None:
        """Return the file's mtime_ns or None if it cannot be stat'd."""
        try:
            return int(os.stat(file_path).st_mtime_ns)
        except OSError:
            return None

    def bulk_get_by_stat(
        self, paths_with_mtimes: list[tuple[str, int]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Return ``{file_path: routes}`` for every (path, mtime) pair whose
        mtime matches the stored row. A single SQL query instead of N — this
        is the warm-pass dominator on large projects.
        """
        if not paths_with_mtimes:
            return {}
        # We can't bind two-column IN clauses portably; instead we pre-fetch
        # the candidate rows by path and filter mtime in Python. SQLite handles
        # up to 999 parameters per query, so we chunk if needed.
        result: dict[str, list[dict[str, Any]]] = {}
        wanted = dict(paths_with_mtimes)
        conn = self._conn()
        chunk_size = 800
        items = list(wanted.items())
        for start in range(0, len(items), chunk_size):
            chunk = items[start : start + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT file_path, mtime_ns, routes_json FROM route_cache "
                f"WHERE file_path IN ({placeholders})",
                [p for p, _ in chunk],
            ).fetchall()
            for row in rows:
                path = row["file_path"]
                if int(row["mtime_ns"]) != wanted[path]:
                    continue
                try:
                    payload = json.loads(row["routes_json"])
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, list):
                    result[path] = payload
        return result

    def bulk_put(
        self,
        records: list[tuple[str, str, int, list[dict[str, Any]]]],
    ) -> None:
        """Insert/update many cache rows in one transaction."""
        if not records:
            return
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (path, ch, mt, json.dumps(routes, ensure_ascii=False), now)
            for path, ch, mt, routes in records
        ]
        conn = self._conn()
        conn.execute("BEGIN")
        try:
            conn.executemany(
                """INSERT OR REPLACE INTO route_cache
                   (file_path, content_hash, mtime_ns, routes_json, indexed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def put(
        self,
        file_path: str,
        content_hash: str,
        mtime_ns: int,
        routes: list[dict[str, Any]],
    ) -> None:
        self._conn().execute(
            """INSERT OR REPLACE INTO route_cache
               (file_path, content_hash, mtime_ns, routes_json, indexed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                file_path,
                content_hash,
                mtime_ns,
                json.dumps(routes, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def stats(self) -> dict[str, Any]:
        row = self._conn().execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(length(routes_json)), 0) AS bytes "
            "FROM route_cache"
        ).fetchone()
        return {"file_count": int(row["n"]), "total_bytes": int(row["bytes"])}
