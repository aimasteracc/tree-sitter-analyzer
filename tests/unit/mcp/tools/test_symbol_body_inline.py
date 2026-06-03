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
