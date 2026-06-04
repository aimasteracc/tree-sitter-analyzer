"""Deterministic tests for the shared symbol-body inlining helper (P2).

P2 generalises the call_path "coordinates -> content + deterrent" upgrade to
the agent-high-frequency tools: nav navigate / nav callers / nav callees /
search symbol.  These tests assert the *shared helper* behaviour directly:

  - records that already carry an end_line are inlined verbatim;
  - records missing end_line resolve their span via the AST-index def-index;
  - per-body and total caps truncate long bodies and flag full_at;
  - cap tiers differ by use-case (definition 80, neighbour 40, summary 30).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools import symbol_body_inline as sbi

_SRC_BIG = "def big():\n" + "".join(f"    x{i} = {i}\n" for i in range(120))
_SRC_SMALL = 'def small():\n    return "SMALL_MARKER"\n'


def _build_cache(tmp_path: Path) -> MagicMock:
    (tmp_path / "big.py").write_text(_SRC_BIG)
    (tmp_path / "small.py").write_text(_SRC_SMALL)

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE ast_index ("
        " file_path TEXT PRIMARY KEY, symbols_json TEXT, language TEXT)"
    )
    symbols = {
        "big.py": [{"name": "big", "kind": "function", "line": 1, "end_line": 121}],
        "small.py": [{"name": "small", "kind": "function", "line": 1, "end_line": 2}],
    }
    for fp, syms in symbols.items():
        db.execute(
            "INSERT INTO ast_index (file_path, symbols_json, language) VALUES (?,?,?)",
            (fp, json.dumps({"symbols": syms}), "python"),
        )
    db.commit()

    cache = MagicMock()
    cache.get_conn.return_value = db
    cache._get_conn.return_value = db
    return cache


# ---------------------------------------------------------------------------
# inline_symbol_body — single definition, full 80-line tier
# ---------------------------------------------------------------------------


def test_inline_symbol_body_verbatim_with_end_line(tmp_path):
    cache = _build_cache(tmp_path)
    record = {"name": "small", "file": "small.py", "line": 1, "end_line": 2}
    block = sbi.inline_symbol_body(str(tmp_path), cache, record)
    assert block is not None
    assert "SMALL_MARKER" in block["content"]
    assert "def small" in block["content"]
    assert block.get("truncated") is not True


def test_inline_symbol_body_truncates_over_cap(tmp_path):
    cache = _build_cache(tmp_path)
    # 121-line body exceeds the 80-line definition tier.
    record = {"name": "big", "file": "big.py", "line": 1, "end_line": 121}
    block = sbi.inline_symbol_body(str(tmp_path), cache, record)
    assert block is not None
    assert block.get("truncated") is True
    assert "full_at" in block
    assert block["full_at"] == "big.py:1"
    assert len(block["content"].splitlines()) <= sbi.MAX_DEFINITION_LINES


def test_inline_symbol_body_resolves_missing_end_line(tmp_path):
    cache = _build_cache(tmp_path)
    # No end_line on the record — helper must resolve span via def-index.
    record = {"name": "small", "file": "small.py", "line": 1}
    block = sbi.inline_symbol_body(str(tmp_path), cache, record)
    assert block is not None
    assert "SMALL_MARKER" in block["content"]


# ---------------------------------------------------------------------------
# inline_neighbor_bodies — top-N callers/callees, 40-line tier, total cap
# ---------------------------------------------------------------------------


def test_inline_neighbor_bodies_attaches_body_to_each(tmp_path):
    cache = _build_cache(tmp_path)
    neighbors = [
        {"name": "small", "file": "small.py", "line": 1},
        {"name": "big", "file": "big.py", "line": 1},
    ]
    enriched = sbi.inline_neighbor_bodies(str(tmp_path), cache, neighbors)
    assert len(enriched) == 2
    small = next(n for n in enriched if n["name"] == "small")
    assert "body" in small
    assert "SMALL_MARKER" in small["body"]["content"]


def test_inline_neighbor_body_does_not_cross_languages(tmp_path):
    """A Python callee with no Python def must not inline a foreign-language body.

    Regression: ``sorted()`` (a Python builtin call, no Python definition) has a
    call-site ``file`` but no matching def there, so ``_resolve_def`` fell back to
    ``candidates[0]`` — grabbing a Swift ``func sorted`` body and inlining it
    under the Python callee. The record carries ``language='python'``; a
    cross-language body must be suppressed (callee stays body-less).
    """
    (tmp_path / "corpus.swift").write_text("func sorted() -> Int {\n    return 1\n}\n")
    cache = _build_cache(tmp_path)
    cache.get_conn.return_value.execute(
        "INSERT INTO ast_index (file_path, symbols_json, language) VALUES (?,?,?)",
        (
            "corpus.swift",
            json.dumps(
                {
                    "symbols": [
                        {"name": "sorted", "kind": "function", "line": 1, "end_line": 3}
                    ]
                }
            ),
            "swift",
        ),
    )
    cache.get_conn.return_value.commit()
    # Python callee record: a ``sorted()`` call from a Python file, no end_line.
    neighbors = [
        {"name": "sorted", "file": "small.py", "line": 1, "language": "python"}
    ]
    enriched = sbi.inline_neighbor_bodies(str(tmp_path), cache, neighbors)
    assert "body" not in enriched[0], (
        f"cross-language body inlined: {enriched[0].get('body')}"
    )


def test_inline_neighbor_body_skipped_for_unknown_callee(tmp_path):
    """An unresolved callee gets no inlined body (it would be a bare-name guess).

    A callee the resolver left ``unknown`` (builtin / dynamic / truly unknown)
    has no real definition; the def-index fallback could only attach a
    same-named symbol from elsewhere. Such records stay coordinate-only — both
    correct and leaner. Resolved callees are unaffected.
    """
    cache = _build_cache(tmp_path)
    neighbors = [
        # Resolved callee → keeps its body.
        {
            "name": "small",
            "file": "small.py",
            "line": 1,
            "callee_resolution": "local",
            "callee_resolved_file": "small.py",
        },
        # Unresolved callee that happens to share the name of a real def.
        {
            "name": "small",
            "file": "small.py",
            "line": 1,
            "callee_resolution": "unknown",
            "callee_resolved_file": "",
        },
    ]
    enriched = sbi.inline_neighbor_bodies(str(tmp_path), cache, neighbors)
    assert "body" in enriched[0]
    assert "body" not in enriched[1], (
        f"unknown callee should stay body-less: {enriched[1].get('body')}"
    )


def test_inline_neighbor_bodies_caps_at_top_n(tmp_path):
    cache = _build_cache(tmp_path)
    neighbors = [{"name": "small", "file": "small.py", "line": 1} for _ in range(50)]
    enriched = sbi.inline_neighbor_bodies(str(tmp_path), cache, neighbors)
    bodied = [n for n in enriched if "body" in n]
    # Only the first MAX_NEIGHBOR_BODIES get a body; the rest stay coordinate-only.
    assert len(bodied) <= sbi.MAX_NEIGHBOR_BODIES


def test_inline_neighbor_body_uses_40_line_tier(tmp_path):
    cache = _build_cache(tmp_path)
    neighbors = [{"name": "big", "file": "big.py", "line": 1, "end_line": 121}]
    enriched = sbi.inline_neighbor_bodies(str(tmp_path), cache, neighbors)
    body = enriched[0]["body"]
    assert body.get("truncated") is True
    assert len(body["content"].splitlines()) <= sbi.MAX_NEIGHBOR_LINES


# ---------------------------------------------------------------------------
# inline_search_summaries — top matches, 30-line tier
# ---------------------------------------------------------------------------


def test_inline_search_summaries_attaches_body(tmp_path):
    cache = _build_cache(tmp_path)
    results = [
        {"name": "small", "file": "small.py", "line": 1, "end_line": 2},
    ]
    enriched = sbi.inline_search_summaries(str(tmp_path), cache, results)
    assert "body" in enriched[0]
    assert "SMALL_MARKER" in enriched[0]["body"]["content"]


def test_inline_search_summaries_uses_30_line_tier(tmp_path):
    cache = _build_cache(tmp_path)
    results = [{"name": "big", "file": "big.py", "line": 1, "end_line": 121}]
    enriched = sbi.inline_search_summaries(str(tmp_path), cache, results)
    body = enriched[0]["body"]
    assert body.get("truncated") is True
    assert len(body["content"].splitlines()) <= sbi.MAX_SUMMARY_LINES
