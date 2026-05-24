#!/usr/bin/env python3
"""Decision journal storage (r37fG phase 1a).

SQLite-backed persistent log of architectural decisions. The MCP tool layer
(``decision_journal_tool.py``, phase 1b) wraps this with the canonical
envelope; this module contains pure storage + validation logic so it can be
unit-tested without an MCP client.

Why this exists
---------------
Agents that touch a codebase tomorrow don't remember the decisions that
shaped the codebase today. Without a journal, every refactor litigates
"why isn't this a generator?" from scratch. With one, the agent can
``search`` for a decision before proposing a change — and the calling
LLM is bound (via the tool's VERDICT INTEGRITY paragraph) to surface
the recorded verdict verbatim.

Design constants
----------------
* IDs are uuid4 hex (32 chars, stdlib only — no new dep on `ulid`).
* Timestamps are ISO-8601 UTC with seconds precision.
* Free-text fields are capped at ``_MAX_TEXT_CHARS`` to prevent
  accidental dumps of multi-MB stack traces.
* ``alternatives`` list is capped at ``_MAX_ALTERNATIVES`` because past a
  dozen the journal stops being a decision record and becomes a wiki.
* Storage path is ``<project_root>/.ast-cache/decision_journal.db`` —
  co-located with ``routes.db`` and the ast index so all session state
  lives in one directory the user can ``rm -rf`` to reset.
"""

from __future__ import annotations

import json
import sqlite3  # nosec B404 - parameterised queries only
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DB_FILENAME = "decision_journal.db"
_CACHE_DIR = ".ast-cache"

_MAX_TEXT_CHARS = 4096
_MAX_ALTERNATIVES = 16
_MAX_TAGS = 32
_MAX_RELATED_SYMBOLS = 64
_MAX_SCOPE_PATHS = 64
_DEFAULT_SEARCH_LIMIT = 20
_MAX_SEARCH_LIMIT = 100

# Mirrors base_tool._LEGAL_VERDICTS. We re-declare here so this module has
# zero MCP dependency — base_tool is the SOT for the MCP envelope, this
# module is the SOT for the storage layer; the test suite asserts the two
# stay in sync.
_LEGAL_VERDICTS: frozenset[str] = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"}
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decision (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    title           TEXT NOT NULL,
    rationale       TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    scope_paths     TEXT NOT NULL DEFAULT '[]',
    alternatives    TEXT NOT NULL DEFAULT '[]',
    related_symbols TEXT NOT NULL DEFAULT '[]',
    tags            TEXT NOT NULL DEFAULT '[]',
    superseded_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_decision_created ON decision(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_verdict ON decision(verdict);
"""


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionRecord:
    """Immutable in-memory view of a journal row."""

    id: str
    created_at: str
    title: str
    rationale: str
    verdict: str
    scope_paths: tuple[str, ...] = field(default=())
    alternatives: tuple[dict[str, str], ...] = field(default=())
    related_symbols: tuple[str, ...] = field(default=())
    tags: tuple[str, ...] = field(default=())
    superseded_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for JSON / TOON envelopes.

        ``asdict()`` preserves tuple types for tuple-typed fields, but JSON
        serialisers and the canonical envelope contract expect Python
        lists. Coerce here so callers get the wire-shape they expect.
        """
        d = asdict(self)
        for k in ("scope_paths", "alternatives", "related_symbols", "tags"):
            if isinstance(d.get(k), tuple):
                d[k] = list(d[k])
        return d


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class JournalValidationError(ValueError):
    """Raised by ``record`` / ``supersede`` for boundary violations."""


def _require_str(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise JournalValidationError(f"{field_name} must be a string")
    if not allow_empty and not value.strip():
        raise JournalValidationError(f"{field_name} must not be empty")
    if len(value) > _MAX_TEXT_CHARS:
        raise JournalValidationError(
            f"{field_name} exceeds {_MAX_TEXT_CHARS}-char limit"
        )
    return value


def _require_verdict(value: Any) -> str:
    if not isinstance(value, str) or value not in _LEGAL_VERDICTS:
        raise JournalValidationError(
            f"verdict must be one of {sorted(_LEGAL_VERDICTS)}, got {value!r}"
        )
    return value


def _validate_path_list(paths: Any, field_name: str, max_items: int) -> list[str]:
    if paths is None:
        return []
    if not isinstance(paths, (list, tuple)):
        raise JournalValidationError(f"{field_name} must be a list")
    if len(paths) > max_items:
        raise JournalValidationError(
            f"{field_name} has {len(paths)} entries (max {max_items})"
        )
    cleaned: list[str] = []
    for p in paths:
        if not isinstance(p, str):
            raise JournalValidationError(f"{field_name} entries must be strings")
        # Block obvious path-traversal — scope_paths are project-relative
        # markers, not absolute paths, and the journal is informational
        # rather than security-sensitive, but a "scope" with "../" is a
        # smell either way.
        if ".." in Path(p).parts or p.startswith("/"):
            raise JournalValidationError(
                f"{field_name} entries must be project-relative (got {p!r})"
            )
        cleaned.append(p)
    return cleaned


def _validate_alternatives(items: Any) -> list[dict[str, str]]:
    if items is None:
        return []
    if not isinstance(items, (list, tuple)):
        raise JournalValidationError("alternatives must be a list")
    if len(items) > _MAX_ALTERNATIVES:
        raise JournalValidationError(
            f"alternatives has {len(items)} entries (max {_MAX_ALTERNATIVES})"
        )
    cleaned: list[dict[str, str]] = []
    for entry in items:
        if not isinstance(entry, dict):
            raise JournalValidationError(
                "alternatives entries must be dicts with 'option' + 'why_rejected'"
            )
        option = entry.get("option", "")
        why = entry.get("why_rejected", "")
        cleaned.append(
            {
                "option": _require_str(option, "alternatives.option"),
                "why_rejected": _require_str(why, "alternatives.why_rejected"),
            }
        )
    return cleaned


def _validate_string_list(items: Any, field_name: str, max_items: int) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, (list, tuple)):
        raise JournalValidationError(f"{field_name} must be a list")
    if len(items) > max_items:
        raise JournalValidationError(
            f"{field_name} has {len(items)} entries (max {max_items})"
        )
    cleaned: list[str] = []
    for s in items:
        if not isinstance(s, str):
            raise JournalValidationError(f"{field_name} entries must be strings")
        cleaned.append(_require_str(s, f"{field_name}[]"))
    return cleaned


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with seconds precision (test-friendly)."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return uuid.uuid4().hex


class DecisionJournal:
    """SQLite-backed decision journal."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root).resolve()
        cache_dir = self._project_root / _CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = cache_dir / _DB_FILENAME
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        title: str,
        rationale: str,
        verdict: str,
        scope_paths: list[str] | None = None,
        alternatives: list[dict[str, str]] | None = None,
        related_symbols: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> DecisionRecord:
        """Insert a new decision and return its record."""
        title_v = _require_str(title, "title")
        rationale_v = _require_str(rationale, "rationale")
        verdict_v = _require_verdict(verdict)
        scope_v = _validate_path_list(scope_paths, "scope_paths", _MAX_SCOPE_PATHS)
        alts_v = _validate_alternatives(alternatives)
        symbols_v = _validate_string_list(
            related_symbols, "related_symbols", _MAX_RELATED_SYMBOLS
        )
        tags_v = _validate_string_list(tags, "tags", _MAX_TAGS)
        rec_id = _new_id()
        created_at = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO decision (id, created_at, title, rationale, "
                "verdict, scope_paths, alternatives, related_symbols, tags) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    rec_id,
                    created_at,
                    title_v,
                    rationale_v,
                    verdict_v,
                    json.dumps(scope_v),
                    json.dumps(alts_v),
                    json.dumps(symbols_v),
                    json.dumps(tags_v),
                ),
            )
        return DecisionRecord(
            id=rec_id,
            created_at=created_at,
            title=title_v,
            rationale=rationale_v,
            verdict=verdict_v,
            scope_paths=tuple(scope_v),
            alternatives=tuple(alts_v),
            related_symbols=tuple(symbols_v),
            tags=tuple(tags_v),
            superseded_by=None,
        )

    def get(self, decision_id: str) -> DecisionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM decision WHERE id = ?", (decision_id,)
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def search(
        self,
        *,
        query: str | None = None,
        verdict_filter: str | None = None,
        path_scope: str | None = None,
        limit: int = _DEFAULT_SEARCH_LIMIT,
    ) -> list[DecisionRecord]:
        if limit < 1:
            raise JournalValidationError("limit must be >= 1")
        if limit > _MAX_SEARCH_LIMIT:
            limit = _MAX_SEARCH_LIMIT
        sql = "SELECT * FROM decision WHERE 1=1"
        params: list[Any] = []
        if verdict_filter is not None:
            _require_verdict(verdict_filter)
            sql += " AND verdict = ?"
            params.append(verdict_filter)
        if query:
            like = f"%{query}%"
            sql += " AND (title LIKE ? OR rationale LIKE ? OR tags LIKE ?)"
            params.extend([like, like, like])
        if path_scope:
            sql += " AND scope_paths LIKE ?"
            params.append(f"%{path_scope}%")
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(r) for r in rows]

    def supersede(self, old_id: str, new_id: str) -> DecisionRecord | None:
        """Mark ``old_id`` as superseded by ``new_id``. Returns updated row."""
        if old_id == new_id:
            raise JournalValidationError("old_id and new_id must differ")
        with self._connect() as conn:
            # Ensure both exist first so we don't half-update.
            old_row = conn.execute(
                "SELECT id FROM decision WHERE id = ?", (old_id,)
            ).fetchone()
            new_row = conn.execute(
                "SELECT id FROM decision WHERE id = ?", (new_id,)
            ).fetchone()
            if old_row is None or new_row is None:
                return None
            conn.execute(
                "UPDATE decision SET superseded_by = ? WHERE id = ?",
                (new_id, old_id),
            )
            updated = conn.execute(
                "SELECT * FROM decision WHERE id = ?", (old_id,)
            ).fetchone()
        return _row_to_record(updated)


def _row_to_record(row: sqlite3.Row) -> DecisionRecord:
    return DecisionRecord(
        id=row["id"],
        created_at=row["created_at"],
        title=row["title"],
        rationale=row["rationale"],
        verdict=row["verdict"],
        scope_paths=tuple(json.loads(row["scope_paths"])),
        alternatives=tuple(json.loads(row["alternatives"])),
        related_symbols=tuple(json.loads(row["related_symbols"])),
        tags=tuple(json.loads(row["tags"])),
        superseded_by=row["superseded_by"],
    )
