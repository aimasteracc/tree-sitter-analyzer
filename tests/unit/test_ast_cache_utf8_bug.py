"""Regression test for the UTF-8 byte-offset bug in ``_node_text``.

The bug: tree-sitter returns ``start_byte`` / ``end_byte`` as UTF-8 BYTE
offsets. Slicing ``source`` (a Python ``str``) with those byte values is
correct only for pure-ASCII files; the moment a file contains any
multi-byte glyph (e.g. ``≤`` = 3 bytes), every symbol indexed AFTER
that glyph gets its name shifted by N characters per multi-byte char.

We caught this in a cross-tool comparison: rg found ``HealthScorer`` in
12 files, our FTS5 index returned 8 — including missing the file that
DEFINED the class. Probing the DB showed garbage names like
``'health score'`` and ``'> HealthSc'`` instead of the real symbol names.

This test:
1. Creates a Python file that contains a multi-byte glyph BEFORE a
   class definition.
2. Indexes it via :class:`ASTCache`.
3. Asserts the class name comes back intact, not truncated.

If anyone reverts the fix in ``_node_text``, this test fails loudly.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache, _node_text


@pytest.fixture
def utf8_project():
    """A project with a multi-byte glyph (``≤``) before a class def."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "thresholds.py").write_text(
        # The leading constant contains '≤' (U+2264, 3 bytes UTF-8).
        # If the byte/char offset bug returns, every symbol after this
        # point gets its name shifted by 2 characters per multi-byte glyph.
        # Add many to amplify the shift.
        "THRESHOLD_LABEL = 'difficulty ≤ medium ≤ hard ≤ extreme'\n"
        "\n"
        "class CorrectName:\n"
        "    def correct_method(self, x):\n"
        "        return x + 1\n"
        "\n"
        "class AnotherCorrectName:\n"
        "    pass\n",
        encoding="utf-8",
    )
    yield tmp


def test_indexed_class_name_is_not_byte_shifted(utf8_project: Path) -> None:
    cache = ASTCache(str(utf8_project))
    cache.index_file(str(utf8_project / "thresholds.py"))

    conn = sqlite3.connect(cache.db_path)
    rows = conn.execute(
        "SELECT name, kind FROM ast_symbol_rows "
        "WHERE kind IN ('class','function','method') ORDER BY line"
    ).fetchall()
    cache.close()
    conn.close()

    names = [r[0] for r in rows]
    # The exact names must come through — no shift, no truncation.
    assert "CorrectName" in names, f"expected CorrectName in {names}"
    assert "AnotherCorrectName" in names, f"expected AnotherCorrectName in {names}"
    assert "correct_method" in names, f"expected correct_method in {names}"
    # And NONE of the garbage we'd see if the bug were back.
    for n in names:
        assert "≤" not in n, f"unexpected glyph in symbol name {n!r}"
        # The bug used to produce names starting with mid-word fragments;
        # all the names we set are single tokens with no spaces.
        assert " " not in n, f"symbol name {n!r} contains a space — byte-offset shift?"


def test_node_text_helper_handles_bytes_attr() -> None:
    """``_node_text`` should prefer ``node.text`` (bytes) when present."""

    class FakeNode:
        # tree-sitter's real Node exposes .text as bytes.
        text = b"HealthScorer"
        start_byte = 0
        end_byte = 12

    assert _node_text(FakeNode(), "ignored str") == "HealthScorer"


def test_node_text_helper_falls_back_to_bytes_slice() -> None:
    """When ``node.text`` is unavailable, the helper must slice on bytes
    (not on the str). Pure-ASCII case is the easy half."""

    class FakeNode:
        text = None
        start_byte = 0
        end_byte = 5

    assert _node_text(FakeNode(), "hello world") == "hello"


def test_node_text_helper_handles_multibyte_source() -> None:
    """The fallback slice must use byte indices on the encoded source.

    Source string: 'X≤Y' is 3 CHARS but 5 BYTES (X=1, ≤=3, Y=1).
    Asking for bytes[2:5] should yield '\\x88Y' from the second/third
    byte of ≤ plus Y. We don't care about the exact slice — we care
    that the helper doesn't blow up and doesn't silently shift.
    """

    class FakeNode:
        text = None
        start_byte = 0
        end_byte = 4  # first 4 bytes = 'X' + first 3 bytes of '≤'

    src = "X≤Y"  # 5 bytes
    out = _node_text(FakeNode(), src)
    # The decoded result should start with 'X' and recover '≤' fully because
    # bytes 0..4 contain X + the full 3-byte UTF-8 sequence for ≤.
    assert out.startswith("X≤"), f"got {out!r}"
