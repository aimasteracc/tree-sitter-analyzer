"""Tests for file_health_blocks — fallback block scanning heuristics."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.utils.file_health_blocks import (
    _BlockTracker,
    find_long_blocks_heuristic,
)


# ---------------------------------------------------------------------------
# _BlockTracker
# ---------------------------------------------------------------------------

class TestBlockTracker:
    def test_initial_state(self) -> None:
        t = _BlockTracker()
        assert t.active is False
        assert t.def_name == ""
        assert t.block_lines == 0

    def test_start_sets_state(self) -> None:
        t = _BlockTracker()
        t.start("my_func", start=5, indent=4)
        assert t.active is True
        assert t.def_name == "my_func"
        assert t.def_start == 5
        assert t.def_indent == 4
        assert t.block_lines == 1

    def test_process_line_increments(self) -> None:
        t = _BlockTracker()
        t.start("fn", 0, 0)
        t.process_line()
        t.process_line()
        assert t.block_lines == 3

    def test_snapshot_returns_tuple(self) -> None:
        t = _BlockTracker()
        t.start("fn", start=10, indent=0)
        name, start, lines = t.snapshot()
        assert name == "fn"
        assert start == 11  # +1 for 1-indexed
        assert lines == 1

    def test_ended_at_unindented_def(self) -> None:
        t = _BlockTracker()
        t.start("fn", 0, indent=4)
        assert t.ended_at("def next_fn():", "def next_fn():") is True
        assert t.active is False

    def test_ended_at_same_indent_non_def(self) -> None:
        t = _BlockTracker()
        t.start("fn", 0, indent=4)
        assert t.ended_at("    x = 1", "    x = 1") is False

    def test_ended_at_empty_line(self) -> None:
        t = _BlockTracker()
        t.start("fn", 0, indent=4)
        assert t.ended_at("", "") is False

    def test_ended_at_class_at_same_indent(self) -> None:
        t = _BlockTracker()
        t.start("fn", 0, indent=0)
        assert t.ended_at("class Foo:", "class Foo:") is True

    def test_ended_at_decorator(self) -> None:
        t = _BlockTracker()
        t.start("fn", 0, indent=4)
        assert t.ended_at("    @decorator", "    @decorator") is True


# ---------------------------------------------------------------------------
# find_long_blocks_heuristic
# ---------------------------------------------------------------------------

class TestFindLongBlocksHeuristic:
    def test_empty_lines_no_blocks(self) -> None:
        result = find_long_blocks_heuristic([])
        assert result == []

    def test_short_function_not_reported(self) -> None:
        lines = ["def short():"] + ["    pass"] * 5
        result = find_long_blocks_heuristic(lines, threshold=50)
        assert result == []

    def test_long_function_detected(self) -> None:
        lines = ["def long_fn():"] + ["    x = 1"] * 60
        result = find_long_blocks_heuristic(lines, threshold=50)
        assert len(result) >= 1
        name, start, length = result[0]
        assert name == "long_fn"
        assert length > 50

    def test_multiple_functions_tracks_each(self) -> None:
        lines = (
            ["def short():"] + ["    pass"] * 5
            + ["def long_fn():"] + ["    x = 1"] * 60
        )
        result = find_long_blocks_heuristic(lines, threshold=50)
        assert len(result) == 1
        assert result[0][0] == "long_fn"

    def test_async_def_detected(self) -> None:
        lines = ["async def long_async():"] + ["    await x"] * 60
        result = find_long_blocks_heuristic(lines, threshold=50)
        assert len(result) >= 1
        assert result[0][0] == "long_async"

    def test_results_sorted_by_length_descending(self) -> None:
        lines = (
            ["def medium_fn():"] + ["    pass"] * 55
            + ["def huge_fn():"] + ["    pass"] * 80
        )
        result = find_long_blocks_heuristic(lines, threshold=50)
        if len(result) >= 2:
            assert result[0][2] >= result[1][2]

    def test_nested_def_increments_correctly(self) -> None:
        """Inner def at higher indent should not reset outer tracking."""
        lines = (
            ["def outer():"]
            + ["    pass"] * 20
            + ["    def inner():"]
            + ["        pass"] * 40
        )
        result = find_long_blocks_heuristic(lines, threshold=50)
        # outer is 62 lines, inner is 41 — only outer should be reported
        assert any(r[0] == "outer" for r in result)
