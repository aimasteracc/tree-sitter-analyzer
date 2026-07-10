"""Tests for REQ-E-016: corpus-directory exclusion in walk_and_partition."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.cache.indexer import (
    _DEFAULT_EXCLUDE_PATTERNS,
    _walk_source_files,
    walk_and_partition,
)
from tree_sitter_analyzer.project_graph import _language_from_ext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockCache:
    """Minimal stand-in for ASTCache — walk_and_partition only needs project_root."""

    def __init__(self, root: str) -> None:
        self.project_root = root


def _make_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the minimal ast_index schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index ("
        "  file_path TEXT PRIMARY KEY,"
        "  content_hash TEXT,"
        "  mtime_ns INTEGER,"
        "  file_size INTEGER,"
        "  extractor_version INTEGER"
        ")"
    )
    conn.commit()
    return conn


def _make_error_entry(rel_path: str, reason: str) -> dict:
    return {"file": rel_path, "status": "error", "reason": reason}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCorpusExclusion:
    def test_corpus_file_excluded_from_candidates(self, tmp_path):
        """Files under tests/golden/corpus_* must NOT appear in candidates."""
        corpus_dir = tmp_path / "tests" / "golden"
        corpus_dir.mkdir(parents=True)
        (corpus_dir / "corpus_swift.swift").write_text("// swift source\n")

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("x = 1\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        _, candidates, _ = walk_and_partition(
            cache,
            conn,
            max_files=10_000,
            force=True,
            activation_enabled=False,
            walk_fn=_walk_source_files,
            language_fn=_language_from_ext,
            extractor_version=1,
            make_error_entry=_make_error_entry,
            exclude_patterns=_DEFAULT_EXCLUDE_PATTERNS,
        )

        candidate_names = {os.path.basename(p) for p, _ in candidates}
        assert "corpus_swift.swift" not in candidate_names, (
            "corpus_swift.swift should be excluded by _DEFAULT_EXCLUDE_PATTERNS"
        )

    def test_non_corpus_source_file_included(self, tmp_path):
        """Normal source files must NOT be excluded."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("x = 1\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        _, candidates, _ = walk_and_partition(
            cache,
            conn,
            max_files=10_000,
            force=True,
            activation_enabled=False,
            walk_fn=_walk_source_files,
            language_fn=_language_from_ext,
            extractor_version=1,
            make_error_entry=_make_error_entry,
            exclude_patterns=_DEFAULT_EXCLUDE_PATTERNS,
        )

        candidate_names = {os.path.basename(p) for p, _ in candidates}
        assert "main.py" in candidate_names, (
            "main.py must be included; it does not match corpus exclusion patterns"
        )

    def test_exclusion_skipped_stat_incremented(self, tmp_path):
        """Excluded files must increment stats['skipped']."""
        corpus_dir = tmp_path / "tests" / "golden"
        corpus_dir.mkdir(parents=True)
        (corpus_dir / "corpus_go.go").write_text("package main\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        stats, _, _ = walk_and_partition(
            cache,
            conn,
            max_files=10_000,
            force=True,
            activation_enabled=False,
            walk_fn=_walk_source_files,
            language_fn=_language_from_ext,
            extractor_version=1,
            make_error_entry=_make_error_entry,
            exclude_patterns=_DEFAULT_EXCLUDE_PATTERNS,
        )

        assert stats["skipped"] >= 1, (
            "At least one file must be counted as skipped due to corpus exclusion"
        )

    def test_no_exclusion_when_patterns_is_none(self, tmp_path):
        """When exclude_patterns=None the corpus file is NOT excluded."""
        corpus_dir = tmp_path / "tests" / "golden"
        corpus_dir.mkdir(parents=True)
        (corpus_dir / "corpus_swift.swift").write_text("// swift source\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        _, candidates, _ = walk_and_partition(
            cache,
            conn,
            max_files=10_000,
            force=True,
            activation_enabled=False,
            walk_fn=_walk_source_files,
            language_fn=_language_from_ext,
            extractor_version=1,
            make_error_entry=_make_error_entry,
            exclude_patterns=None,
        )

        candidate_names = {os.path.basename(p) for p, _ in candidates}
        assert "corpus_swift.swift" in candidate_names, (
            "Without exclude_patterns the corpus file must reach the candidate list"
        )
