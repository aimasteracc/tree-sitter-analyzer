"""RED tests for HealthHistory persistence layer.

Target module (does NOT exist yet):
    tree_sitter_analyzer._health_history.HealthHistory

Contract under test:
    HealthHistory(project_root: str, db_path: str | None = None)
        .append(file: str, score: float, grade: str, *, dimensions: dict | None = None,
                trigger: str = "watch", computed_at: float | None = None) -> None
        .last(file: str) -> tuple[str, float] | None   # (grade, score)
        .prune(file: str, keep_n: int) -> int          # rows deleted

Storage: SQLite at <project_root>/.ast-cache/health_scores.db
Table:   health_score_history (see SPEC).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

# Importing the target module is itself a RED test: it must ImportError today.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _import_history():
    """Lazy import to ensure each test gets a clean failure on missing module."""
    from tree_sitter_analyzer.registry.health_history import (
        HealthHistory,  # noqa: WPS433
    )

    return HealthHistory


@pytest.fixture
def project_root(tmp_path: Path) -> str:
    (tmp_path / ".ast-cache").mkdir(parents=True, exist_ok=True)
    return str(tmp_path)


@pytest.fixture
def history(project_root: str):
    HealthHistory = _import_history()
    h = HealthHistory(project_root)
    yield h
    close = getattr(h, "close", None)
    if callable(close):
        close()


# -------------------------------------------------------------------- append/last


def test_append_then_last_returns_appended(history) -> None:
    """append(file, score, grade) → last(file) returns (grade, score)."""
    history.append("/repo/main.py", score=82.5, grade="B")

    result = history.last("/repo/main.py")

    assert result is not None, "last() must return a non-None value after append"
    grade, score = result
    assert grade == "B"
    assert score == pytest.approx(82.5)


def test_last_returns_none_for_unknown_file(history) -> None:
    """A file that was never appended returns None — no implicit zero row."""
    assert history.last("/repo/never_seen.py") is None


def test_last_returns_most_recent_row_when_multiple(history) -> None:
    """Multiple appends for one file → last() returns the latest by computed_at."""
    base = time.time()
    history.append("/repo/a.py", score=90.0, grade="A", computed_at=base)
    history.append("/repo/a.py", score=70.0, grade="C", computed_at=base + 1.0)
    history.append("/repo/a.py", score=55.0, grade="D", computed_at=base + 2.0)

    grade, score = history.last("/repo/a.py")
    assert grade == "D"
    assert score == pytest.approx(55.0)


# -------------------------------------------------------------------- prune


def test_prune_keeps_last_n(history, project_root: str) -> None:
    """append 60 rows → prune(file, keep=10) → exactly 10 rows, the latest by time."""
    base = time.time()
    for i in range(60):
        history.append(
            "/repo/big.py",
            score=float(i),
            grade="C",
            computed_at=base + i,
        )

    history.prune("/repo/big.py", keep_n=10)

    # Inspect raw table — the contract is that COUNT(*) == 10 for this file
    # and the kept rows are the most recent by computed_at.
    db_path = Path(project_root) / ".ast-cache" / "health_scores.db"
    assert db_path.exists(), "history DB must live at .ast-cache/health_scores.db"

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM health_score_history WHERE file_path = ?",
            ("/repo/big.py",),
        ).fetchone()[0]
        assert count == 10, f"expected 10 rows after prune, got {count}"

        # The kept rows are the latest 10 — totals 50..59.
        kept_totals = sorted(
            row[0]
            for row in conn.execute(
                "SELECT total FROM health_score_history WHERE file_path = ?",
                ("/repo/big.py",),
            )
        )
        assert kept_totals == [float(i) for i in range(50, 60)]
    finally:
        conn.close()


def test_prune_does_not_touch_other_files(history) -> None:
    """prune(fileA, keep=1) must NOT delete rows for fileB."""
    base = time.time()
    for i in range(5):
        history.append("/repo/a.py", score=float(i), grade="C", computed_at=base + i)
    for i in range(5):
        history.append("/repo/b.py", score=float(i), grade="B", computed_at=base + i)

    history.prune("/repo/a.py", keep_n=1)

    # fileB rows must be untouched: 5 rows appended, 0 pruned.
    last_b = history.last("/repo/b.py")
    assert last_b is not None
    assert last_b[1] == 4.0  # last score appended for fileB


def test_prune_keep_n_larger_than_rows_is_noop(history) -> None:
    """If keep_n > existing rows, prune deletes nothing and does not raise."""
    history.append("/repo/small.py", score=88.0, grade="B")
    deleted = history.prune("/repo/small.py", keep_n=100)
    assert deleted == 0
    assert history.last("/repo/small.py") is not None


# -------------------------------------------------------------------- schema migration


def test_history_schema_migration_idempotent(project_root: str) -> None:
    """Opening HealthHistory twice on the same project must not raise."""
    HealthHistory = _import_history()

    first = HealthHistory(project_root)
    first.append("/repo/x.py", score=50.0, grade="D")
    close_first = getattr(first, "close", None)
    if callable(close_first):
        close_first()

    # Re-open: schema migration must be a no-op, and prior rows must survive.
    second = HealthHistory(project_root)
    try:
        result = second.last("/repo/x.py")
        assert result == ("D", pytest.approx(50.0))
    finally:
        close_second = getattr(second, "close", None)
        if callable(close_second):
            close_second()


def test_history_coexists_with_existing_health_scores_table(project_root: str) -> None:
    """If health_scores.db already exists (from HealthScoreCache),
    HealthHistory must not corrupt it — both tables coexist."""
    # Pre-seed the DB with the legacy table the way HealthScoreCache would.
    db_path = Path(project_root) / ".ast-cache" / "health_scores.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS health_scores (
                file_path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                total REAL NOT NULL,
                grade TEXT NOT NULL,
                dimensions_json TEXT NOT NULL,
                cached_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
            );
            """
        )
        conn.execute(
            "INSERT INTO health_scores "
            "(file_path, mtime_ns, size_bytes, total, grade, dimensions_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("/repo/legacy.py", 1, 100, 75.0, "C", "{}"),
        )
        conn.commit()
    finally:
        conn.close()

    HealthHistory = _import_history()
    h = HealthHistory(project_root)
    try:
        h.append("/repo/new.py", score=88.0, grade="B")
        assert h.last("/repo/new.py") == ("B", pytest.approx(88.0))
    finally:
        close = getattr(h, "close", None)
        if callable(close):
            close()

    # Legacy table must still be readable.
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT total, grade FROM health_scores WHERE file_path = ?",
            ("/repo/legacy.py",),
        ).fetchone()
        assert row == (75.0, "C")
    finally:
        conn.close()


# -------------------------------------------------------------------- trigger column


def test_append_records_trigger_source(history, project_root: str) -> None:
    """Each appended row records its trigger ('watch' | 'cli' | 'mcp')."""
    history.append("/repo/a.py", score=70.0, grade="C", trigger="watch")
    history.append("/repo/a.py", score=70.0, grade="C", trigger="cli")
    history.append("/repo/a.py", score=70.0, grade="C", trigger="mcp")

    db_path = Path(project_root) / ".ast-cache" / "health_scores.db"
    conn = sqlite3.connect(str(db_path))
    try:
        triggers = sorted(
            row[0]
            for row in conn.execute(
                "SELECT trigger FROM health_score_history WHERE file_path = ?",
                ("/repo/a.py",),
            )
        )
        assert triggers == ["cli", "mcp", "watch"]
    finally:
        conn.close()
