"""Tests for REQ-E-020: plugin-extension skip WARNING in walk_and_partition."""

from __future__ import annotations

import logging
import sqlite3

import pytest

import tree_sitter_analyzer.cache.indexer as _indexer_mod
from tree_sitter_analyzer.cache.indexer import walk_and_partition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockCache:
    """Minimal stand-in for ASTCache."""

    def __init__(self, root: str) -> None:
        self.project_root = root


def _make_conn() -> sqlite3.Connection:
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

class TestPluginSkipWarning:
    def setup_method(self):
        """Clear the de-duplication set before each test for isolation."""
        _indexer_mod._warned_extensions.clear()

    def test_css_skip_emits_warning(self, tmp_path, caplog):
        """A .css file skipped because language_fn returns None must produce a WARNING."""
        css_file = tmp_path / "style.css"
        css_file.write_text("body { color: red; }\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        def _walk_css(root: str):
            yield str(css_file)

        def _lang_none(path: str):
            return None  # simulate: .css not in EXT_TO_LANG

        with caplog.at_level(logging.WARNING, logger="tree_sitter_analyzer.cache.indexer"):
            walk_and_partition(
                cache,
                conn,
                max_files=10_000,
                force=True,
                activation_enabled=False,
                walk_fn=_walk_css,
                language_fn=_lang_none,
                extractor_version=1,
                make_error_entry=_make_error_entry,
            )

        warning_messages = [
            r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any(".css" in msg for msg in warning_messages), (
            f"Expected a WARNING mentioning .css; got: {warning_messages}"
        )

    def test_warning_emitted_only_once_per_extension(self, tmp_path, caplog):
        """The warning for a given extension must be emitted at most once."""
        css1 = tmp_path / "a.css"
        css2 = tmp_path / "b.css"
        css1.write_text("a {}\n")
        css2.write_text("b {}\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        def _walk_both(root: str):
            yield str(css1)
            yield str(css2)

        def _lang_none(path: str):
            return None

        with caplog.at_level(logging.WARNING, logger="tree_sitter_analyzer.cache.indexer"):
            walk_and_partition(
                cache,
                conn,
                max_files=10_000,
                force=True,
                activation_enabled=False,
                walk_fn=_walk_both,
                language_fn=_lang_none,
                extractor_version=1,
                make_error_entry=_make_error_entry,
            )

        css_warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and ".css" in r.getMessage()
        ]
        assert len(css_warnings) == 1, (
            f"Expected exactly 1 .css WARNING; got {len(css_warnings)}: {css_warnings}"
        )

    def test_unknown_extension_does_not_warn(self, tmp_path, caplog):
        """Extensions not in _PLUGIN_EXTS must NOT produce a WARNING."""
        foo_file = tmp_path / "data.foo"
        foo_file.write_text("data\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        def _walk_foo(root: str):
            yield str(foo_file)

        def _lang_none(path: str):
            return None

        with caplog.at_level(logging.WARNING, logger="tree_sitter_analyzer.cache.indexer"):
            walk_and_partition(
                cache,
                conn,
                max_files=10_000,
                force=True,
                activation_enabled=False,
                walk_fn=_walk_foo,
                language_fn=_lang_none,
                extractor_version=1,
                make_error_entry=_make_error_entry,
            )

        warning_messages = [
            r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert not any(".foo" in msg for msg in warning_messages), (
            f"Unexpected .foo WARNING emitted: {warning_messages}"
        )

    def test_file_still_skipped_after_warning(self, tmp_path, caplog):
        """The .css file must remain excluded from candidates even after the warning."""
        css_file = tmp_path / "style.css"
        css_file.write_text("body {}\n")

        cache = _MockCache(str(tmp_path))
        conn = _make_conn()

        def _walk_css(root: str):
            yield str(css_file)

        def _lang_none(path: str):
            return None

        with caplog.at_level(logging.WARNING, logger="tree_sitter_analyzer.cache.indexer"):
            stats, candidates, _ = walk_and_partition(
                cache,
                conn,
                max_files=10_000,
                force=True,
                activation_enabled=False,
                walk_fn=_walk_css,
                language_fn=_lang_none,
                extractor_version=1,
                make_error_entry=_make_error_entry,
            )

        assert candidates == [], f"Expected no candidates; got {candidates}"
        assert stats["skipped"] == 1
