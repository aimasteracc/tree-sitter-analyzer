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
# inline_symbol_bodies — definition list, full 80-line tier, shared caps
# ---------------------------------------------------------------------------


def _only_body(records, cache, root):
    enriched = sbi.inline_symbol_bodies(str(root), cache, records)
    assert len(enriched) == len(records)
    return enriched[0]


def test_inline_symbol_bodies_verbatim_with_end_line(tmp_path):
    cache = _build_cache(tmp_path)
    record = {"name": "small", "file": "small.py", "line": 1, "end_line": 2}
    enriched = _only_body([record], cache, tmp_path)
    block = enriched["body"]
    assert "SMALL_MARKER" in block["content"]
    assert "def small" in block["content"]
    assert block.get("truncated") is not True


def test_inline_symbol_bodies_truncates_over_cap(tmp_path):
    cache = _build_cache(tmp_path)
    # 121-line body exceeds the 80-line definition tier.
    record = {"name": "big", "file": "big.py", "line": 1, "end_line": 121}
    enriched = _only_body([record], cache, tmp_path)
    block = enriched["body"]
    assert block.get("truncated") is True
    assert "full_at" in block
    assert block["full_at"] == "big.py:1"
    assert len(block["content"].splitlines()) <= sbi.MAX_DEFINITION_LINES


def test_inline_symbol_bodies_resolves_missing_end_line(tmp_path):
    cache = _build_cache(tmp_path)
    # No end_line on the record — helper must resolve span via def-index.
    record = {"name": "small", "file": "small.py", "line": 1}
    enriched = _only_body([record], cache, tmp_path)
    assert "SMALL_MARKER" in enriched["body"]["content"]


def test_definition_bodies_share_one_total_budget(tmp_path):
    """The total-line budget must bind across the whole definition list.

    Regression: the navigate tier called the single-record helper once per
    definition, so each call rebuilt ``MAX_TOTAL_DEFINITION_LINES`` and the cap
    never applied to anything. A fifty-definition navigation inlined fifty full
    bodies — measured at 186,958 chars for one common method name.
    """
    cache = _build_cache(tmp_path)
    # Every record points at the same 121-line body, so each one that inlines
    # consumes the full per-body allowance. A fresh budget per record would
    # therefore yield one 80-line body per record.
    records = [
        {"name": "big", "file": "big.py", "line": 1, "end_line": 121}
        for _ in range(sbi.MAX_DEFINITION_BODIES + 4)
    ]
    enriched = sbi.inline_symbol_bodies(str(tmp_path), cache, records)

    bodies = [r for r in enriched if "body" in r]
    total_lines = sum(len(r["body"]["content"].splitlines()) for r in bodies)
    assert total_lines <= sbi.MAX_TOTAL_DEFINITION_LINES, (
        f"shared budget did not bind: {total_lines} lines across "
        f"{len(bodies)} bodies (cap {sbi.MAX_TOTAL_DEFINITION_LINES})"
    )
    assert len(bodies) <= sbi.MAX_DEFINITION_BODIES
    # Records past the cap keep their coordinates; only the head is bodied.
    assert all("body" not in r for r in enriched[len(bodies) :])
    assert [r["name"] for r in enriched] == ["big"] * len(records)


def test_definition_body_budget_is_per_call_not_per_process(tmp_path):
    """The shared budget must not leak between responses."""
    cache = _build_cache(tmp_path)
    records = [{"name": "small", "file": "small.py", "line": 1, "end_line": 2}]
    first = sbi.inline_symbol_bodies(str(tmp_path), cache, records)
    second = sbi.inline_symbol_bodies(str(tmp_path), cache, records)
    assert "body" in first[0]
    assert "body" in second[0], "a prior call consumed this call's budget"


def test_definition_bodies_do_not_mutate_the_input(tmp_path):
    cache = _build_cache(tmp_path)
    records = [{"name": "small", "file": "small.py", "line": 1, "end_line": 2}]
    sbi.inline_symbol_bodies(str(tmp_path), cache, records)
    assert records == [{"name": "small", "file": "small.py", "line": 1, "end_line": 2}]


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


def test_unreadable_definition_keeps_coordinates(tmp_path):
    """A record whose body cannot be read passes through unchanged."""
    cache = _build_cache(tmp_path)
    record = {"name": "ghost", "file": "absent.py", "line": 1}
    enriched = sbi.inline_symbol_bodies(str(tmp_path), cache, [record])
    assert "body" not in enriched[0]
    assert enriched[0] == record


def test_one_unreadable_record_does_not_stop_the_next(tmp_path):
    """An unreadable record must not consume the list's body allowance."""
    cache = _build_cache(tmp_path)
    records = [
        {"name": "ghost", "file": "absent.py", "line": 1},
        {"name": "small", "file": "small.py", "line": 1, "end_line": 2},
    ]
    enriched = sbi.inline_symbol_bodies(str(tmp_path), cache, records)
    assert "body" not in enriched[0]
    assert "SMALL_MARKER" in enriched[1]["body"]["content"]
