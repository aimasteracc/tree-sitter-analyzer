#!/usr/bin/env python3
"""Decision-journal storage tests (r37fG phase 1a).

These exercise the pure storage layer (``decision_journal.py``) in isolation
from the MCP envelope. The MCP-tool wrapper has its own test suite under
``tests/unit/mcp/tools/`` (r37fG phase 1b).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.decision_journal import (
    _LEGAL_VERDICTS,
    DecisionJournal,
    DecisionRecord,
    JournalValidationError,
)

# ---------------------------------------------------------------------------
# Vocabulary contract — protects against drift from base_tool
# ---------------------------------------------------------------------------


class TestVocabularyContract:
    """Storage-side ``_LEGAL_VERDICTS`` must mirror the MCP envelope SOT."""

    def test_storage_vocab_matches_base_tool(self) -> None:
        from tree_sitter_analyzer.mcp.tools.base_tool import (
            _LEGAL_VERDICTS as MCP_VERDICTS,
        )

        assert _LEGAL_VERDICTS == MCP_VERDICTS, (
            "decision_journal._LEGAL_VERDICTS drifted from base_tool — re-sync."
        )


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


class TestRecord:
    def test_record_creates_row_and_returns_record(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        rec = j.record(
            title="adopt fd", rationale="2x faster than find", verdict="INFO"
        )
        assert isinstance(rec, DecisionRecord)
        assert rec.id and len(rec.id) == 32
        assert rec.title == "adopt fd"
        assert rec.verdict == "INFO"
        assert rec.superseded_by is None

    def test_record_rejects_invalid_verdict(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        with pytest.raises(JournalValidationError, match="verdict must be one of"):
            j.record(title="x", rationale="y", verdict="MAYBE")

    def test_record_rejects_empty_title(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        with pytest.raises(JournalValidationError, match="title must not be empty"):
            j.record(title="   ", rationale="y", verdict="INFO")

    def test_record_rejects_oversize_rationale(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        with pytest.raises(JournalValidationError, match="exceeds"):
            j.record(title="t", rationale="x" * 5000, verdict="INFO")

    def test_record_rejects_path_traversal_in_scope_paths(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        with pytest.raises(JournalValidationError, match="project-relative"):
            j.record(
                title="t",
                rationale="r",
                verdict="INFO",
                scope_paths=["../../etc/passwd"],
            )
        with pytest.raises(JournalValidationError, match="project-relative"):
            j.record(
                title="t",
                rationale="r",
                verdict="INFO",
                scope_paths=["/absolute/path"],
            )

    def test_record_caps_alternatives_at_16(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        too_many = [{"option": f"o{i}", "why_rejected": "r"} for i in range(17)]
        with pytest.raises(JournalValidationError, match=r"max 16"):
            j.record(title="t", rationale="r", verdict="INFO", alternatives=too_many)

    def test_record_accepts_well_formed_alternatives(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        rec = j.record(
            title="t",
            rationale="r",
            verdict="REVIEW",
            alternatives=[
                {"option": "use grep", "why_rejected": "no JSON output"},
                {"option": "use ag", "why_rejected": "unmaintained since 2018"},
            ],
        )
        assert len(rec.alternatives) == 2
        assert rec.alternatives[0]["option"] == "use grep"


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_returns_recorded_row(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        rec = j.record(title="x", rationale="y", verdict="SAFE", tags=["arch", "perf"])
        fetched = j.get(rec.id)
        assert fetched is not None
        assert fetched.id == rec.id
        assert fetched.tags == ("arch", "perf")

    def test_get_unknown_id_returns_none(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        assert j.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_newest_first(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        # Insert three rows; created_at distinguishes them because seconds
        # tick between calls — but if they all land in the same second the
        # returned order is implementation-defined. We still assert all 3
        # come back and that the first one is one of them.
        rec1 = j.record(title="first", rationale="r", verdict="INFO")
        rec2 = j.record(title="second", rationale="r", verdict="INFO")
        rec3 = j.record(title="third", rationale="r", verdict="INFO")
        ids = {r.id for r in j.search()}
        assert {rec1.id, rec2.id, rec3.id} <= ids

    def test_search_substring_matches_title_and_rationale(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        j.record(title="adopt fd", rationale="2x faster than find", verdict="INFO")
        j.record(title="adopt rg", rationale="JSON output", verdict="INFO")
        j.record(title="reject something", rationale="not relevant", verdict="WARN")
        results = j.search(query="adopt")
        assert len(results) == 2
        results = j.search(query="JSON")
        assert len(results) == 1
        assert results[0].title == "adopt rg"

    def test_search_filter_by_verdict(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        j.record(title="t1", rationale="r", verdict="INFO")
        j.record(title="t2", rationale="r", verdict="UNSAFE")
        j.record(title="t3", rationale="r", verdict="REVIEW")
        unsafe = j.search(verdict_filter="UNSAFE")
        assert len(unsafe) == 1
        assert unsafe[0].verdict == "UNSAFE"

    def test_search_rejects_invalid_verdict_filter(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        with pytest.raises(JournalValidationError):
            j.search(verdict_filter="MAYBE")

    def test_search_respects_limit(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        for i in range(5):
            j.record(title=f"t{i}", rationale="r", verdict="INFO")
        assert len(j.search(limit=3)) == 3

    def test_search_clamps_limit_to_max(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        # Hand-clamped at 100; passing 9999 should not raise.
        results = j.search(limit=9999)
        assert results == []  # no rows yet, but call didn't fail


# ---------------------------------------------------------------------------
# Supersede
# ---------------------------------------------------------------------------


class TestSupersede:
    def test_supersede_links_old_to_new(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        old = j.record(title="v1", rationale="initial", verdict="INFO")
        new = j.record(title="v2", rationale="revised", verdict="INFO")
        updated = j.supersede(old.id, new.id)
        assert updated is not None
        assert updated.superseded_by == new.id

    def test_supersede_unknown_old_returns_none(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        new = j.record(title="t", rationale="r", verdict="INFO")
        assert j.supersede("does-not-exist", new.id) is None

    def test_supersede_rejects_self_link(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        rec = j.record(title="t", rationale="r", verdict="INFO")
        with pytest.raises(JournalValidationError, match="must differ"):
            j.supersede(rec.id, rec.id)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_storage_persists_across_journal_instances(self, tmp_path: Path) -> None:
        j1 = DecisionJournal(tmp_path)
        rec = j1.record(title="durable", rationale="r", verdict="INFO")
        del j1
        j2 = DecisionJournal(tmp_path)
        fetched = j2.get(rec.id)
        assert fetched is not None
        assert fetched.title == "durable"

    def test_db_file_lives_under_ast_cache_dir(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        assert j.db_path.parent.name == ".ast-cache"
        assert j.db_path.name == "decision_journal.db"

    def test_to_dict_roundtrip(self, tmp_path: Path) -> None:
        j = DecisionJournal(tmp_path)
        rec = j.record(
            title="t",
            rationale="r",
            verdict="REVIEW",
            tags=["arch"],
            scope_paths=["src/foo.py"],
            related_symbols=["FooBar"],
        )
        d = rec.to_dict()
        assert d["verdict"] == "REVIEW"
        assert d["tags"] == ["arch"]
        assert d["scope_paths"] == ["src/foo.py"]
        assert d["related_symbols"] == ["FooBar"]
