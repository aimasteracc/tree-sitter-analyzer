#!/usr/bin/env python3
"""Tests for ``RefactorQueueTool`` — ``health action=refactor_queue`` (RFC-0027 §L8).

The formula itself is pinned in ``tests/unit/test_refactor_queue.py``. This file
pins the *tool*: its schema, its read-only annotations, and — the point of the
exercise — that it reports ``CHURN_UNAVAILABLE`` instead of fabricating the
zeros that ``log(1 + 0)`` would silently turn into a queue of nonsense.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.refactor_queue_tool import (
    CHURN_UNAVAILABLE,
    STATUS_OK,
    RefactorQueueTool,
)


def _run(tool: RefactorQueueTool, args: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(tool.execute(args))


def _seed_index(root: Path, churn: dict[str, int], symbols: dict[str, int]) -> None:
    """Write the two AST-cache tables the tool reads, and nothing else."""
    cache = root / ".ast-cache"
    cache.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache / "index.db"))
    try:
        conn.execute(
            "CREATE TABLE ast_symbol_activation (file_path TEXT, mod_count_30d INTEGER)"
        )
        conn.execute("CREATE TABLE ast_symbol_rows (file_path TEXT)")
        for path, count in churn.items():
            conn.execute(
                "INSERT INTO ast_symbol_activation VALUES (?, ?)", (path, count)
            )
        for path, count in symbols.items():
            for _ in range(count):
                conn.execute("INSERT INTO ast_symbol_rows VALUES (?)", (path,))
        conn.commit()
    finally:
        conn.close()


class TestSchema:
    def test_tool_name(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        assert tool.get_tool_definition()["name"] == "refactor_queue"

    def test_top_n_default_is_five(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        schema = tool.get_tool_schema()
        assert schema["properties"]["top_n"]["default"] == 5

    def test_output_format_default_is_toon(self) -> None:
        # CLAUDE.md §1 — locked: MCP defaults to TOON.
        tool = RefactorQueueTool(project_root=".")
        schema = tool.get_tool_schema()
        assert schema["properties"]["output_format"]["default"] == "toon"

    def test_declares_read_only_hint(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        assert tool.get_tool_definition()["annotations"]["readOnlyHint"] is True

    def test_declares_not_destructive(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        assert tool.get_tool_definition()["annotations"]["destructiveHint"] is False

    def test_declares_idempotent(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        assert tool.get_tool_definition()["annotations"]["idempotentHint"] is True

    def test_declares_closed_world(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        assert tool.get_tool_definition()["annotations"]["openWorldHint"] is False


class TestValidation:
    def test_top_n_zero_is_rejected(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        with pytest.raises(ValueError, match="top_n"):
            tool.validate_arguments({"top_n": 0})

    def test_top_n_above_the_cap_is_rejected(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        with pytest.raises(ValueError, match="top_n"):
            tool.validate_arguments({"top_n": 51})

    def test_non_integer_top_n_is_rejected(self) -> None:
        tool = RefactorQueueTool(project_root=".")
        with pytest.raises(ValueError, match="top_n"):
            tool.validate_arguments({"top_n": "5"})


class TestChurnUnavailable:
    def test_missing_index_reports_churn_unavailable(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(tmp_path))
        result = _run(tool, {"output_format": "json"})
        assert result["status"] == CHURN_UNAVAILABLE

    def test_missing_index_returns_an_empty_queue(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(tmp_path))
        result = _run(tool, {"output_format": "json"})
        assert result["queue"] == []

    def test_missing_index_verdict_is_warn(self, tmp_path: Path) -> None:
        # A queue that cannot be ranked is not an INFO-level answer.
        tool = RefactorQueueTool(project_root=str(tmp_path))
        result = _run(tool, {"output_format": "json"})
        assert result["verdict"] == "WARN"

    def test_all_zero_churn_reports_churn_unavailable(self, tmp_path: Path) -> None:
        # An activation table full of zeros is "no signal", not "no churn":
        # log(1 + 0) == 0 would flatten every priority to 0.0.
        _seed_index(tmp_path, churn={"a.py": 0}, symbols={"a.py": 3})
        tool = RefactorQueueTool(project_root=str(tmp_path))
        result = _run(tool, {"output_format": "json"})
        assert result["status"] == CHURN_UNAVAILABLE


class TestRankedQueue:
    def _project(self, tmp_path: Path) -> Path:
        (tmp_path / "hot.py").write_text(
            "def a():\n    " + "x = 1\n    " * 40 + "return x\n", encoding="utf-8"
        )
        (tmp_path / "cold.py").write_text("def b():\n    return 2\n", encoding="utf-8")
        _seed_index(
            tmp_path,
            churn={"hot.py": 30, "cold.py": 0},
            symbols={"hot.py": 10, "cold.py": 2},
        )
        return tmp_path

    def test_status_is_ok_when_churn_is_present(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(self._project(tmp_path)))
        result = _run(tool, {"output_format": "json"})
        assert result["status"] == STATUS_OK

    def test_only_churny_files_are_queued(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(self._project(tmp_path)))
        result = _run(tool, {"output_format": "json"})
        assert [row["file_path"] for row in result["queue"]] == ["hot.py"]

    def test_the_formula_is_published_with_the_answer(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(self._project(tmp_path)))
        result = _run(tool, {"output_format": "json"})
        assert result["formula"] == (
            "(1 - health_score/100) * log(1 + churn_30d) * "
            "(dead_symbols/total_symbols + 0.1)"
        )

    def test_row_reports_the_churn_it_ranked_on(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(self._project(tmp_path)))
        result = _run(tool, {"output_format": "json"})
        assert result["queue"][0]["churn_30d"] == 30

    def test_row_reports_the_indexed_symbol_total(self, tmp_path: Path) -> None:
        tool = RefactorQueueTool(project_root=str(self._project(tmp_path)))
        result = _run(tool, {"output_format": "json"})
        assert result["queue"][0]["total_symbols"] == 10

    def test_top_n_caps_the_returned_rows(self, tmp_path: Path) -> None:
        root = self._project(tmp_path)
        (root / "second.py").write_text("def c():\n    return 3\n", encoding="utf-8")
        _seed_index(
            tmp_path / "unused", churn={}, symbols={}
        )  # keep the helper's mkdir side effect out of root
        conn = sqlite3.connect(str(root / ".ast-cache" / "index.db"))
        try:
            conn.execute(
                "INSERT INTO ast_symbol_activation VALUES (?, ?)", ("second.py", 5)
            )
            conn.execute("INSERT INTO ast_symbol_rows VALUES (?)", ("second.py",))
            conn.commit()
        finally:
            conn.close()
        tool = RefactorQueueTool(project_root=str(root))
        result = _run(tool, {"top_n": 1, "output_format": "json"})
        assert len(result["queue"]) == 1


class TestReadOnlyInPractice:
    def test_execute_adds_no_file_under_the_project(self, tmp_path: Path) -> None:
        """The read-only annotation, measured: three reads, zero new paths."""
        (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        _seed_index(tmp_path, churn={"a.py": 4}, symbols={"a.py": 2})

        def snapshot() -> dict[str, tuple[int, int]]:
            return {
                p.relative_to(tmp_path).as_posix(): (
                    p.stat().st_mtime_ns,
                    p.stat().st_size,
                )
                for p in sorted(tmp_path.rglob("*"))
                if p.is_file()
            }

        before = snapshot()
        _run(RefactorQueueTool(project_root=str(tmp_path)), {"output_format": "json"})
        assert sorted(snapshot()) == sorted(before)
