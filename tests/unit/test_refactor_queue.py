#!/usr/bin/env python3
"""Tests for ``tree_sitter_analyzer.refactor_queue`` — RFC-0027 §L8 item 2.

The refactor-priority formula lived only in
``.claude/skills/tsa-refactor-queue/SKILL.md`` — a formula in a prompt has no
regression protection. These tests pin it in code with exact values.

Float pins use ``round(value, 9)``: the expression contains ``math.log``, whose
last bit is libm-dependent, so a bare ``==`` on the full float would be a
platform coin-flip rather than a contract. Nine decimals is an exact pin on a
platform-stable quantity, not a loose bound.
"""

from __future__ import annotations

import math

import pytest

from tree_sitter_analyzer.refactor_queue import (
    DEAD_RATIO_FLOOR,
    RefactorQueueRow,
    rank_refactor_queue,
    refactor_priority,
)


class TestFormula:
    """``(1 - health/100) * log(1 + churn) * (dead/total + 0.1)``."""

    def test_dead_ratio_floor_is_zero_point_one(self) -> None:
        assert DEAD_RATIO_FLOOR == 0.1

    def test_priority_for_the_skill_worked_example(self) -> None:
        # SKILL.md's worked example row 1: api.py, health 42, churn 18, 4/67 dead.
        value = refactor_priority(
            health_score=42.0, churn_30d=18, dead_symbols=4, total_symbols=67
        )
        assert round(value, 9) == 0.272734154

    def test_priority_matches_the_reference_expression(self) -> None:
        expected = (1 - 55.0 / 100) * math.log(1 + 7) * (3 / 20 + 0.1)
        value = refactor_priority(
            health_score=55.0, churn_30d=7, dead_symbols=3, total_symbols=20
        )
        assert round(value, 9) == round(expected, 9)

    def test_zero_churn_gives_zero_priority(self) -> None:
        # log(1 + 0) == 0 — an untouched file is never queued, whatever its grade.
        value = refactor_priority(
            health_score=0.0, churn_30d=0, dead_symbols=10, total_symbols=10
        )
        assert value == 0.0

    def test_perfect_health_gives_zero_priority(self) -> None:
        value = refactor_priority(
            health_score=100.0, churn_30d=50, dead_symbols=10, total_symbols=10
        )
        assert value == 0.0

    def test_no_dead_symbols_still_ranks_via_the_floor(self) -> None:
        value = refactor_priority(
            health_score=50.0, churn_30d=1, dead_symbols=0, total_symbols=40
        )
        assert round(value, 9) == round(0.5 * math.log(2) * 0.1, 9)

    def test_zero_total_symbols_uses_the_floor_alone(self) -> None:
        value = refactor_priority(
            health_score=50.0, churn_30d=1, dead_symbols=0, total_symbols=0
        )
        assert round(value, 9) == round(0.5 * math.log(2) * 0.1, 9)

    def test_negative_churn_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="churn_30d"):
            refactor_priority(
                health_score=50.0, churn_30d=-1, dead_symbols=0, total_symbols=1
            )

    def test_health_score_above_100_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="health_score"):
            refactor_priority(
                health_score=101.0, churn_30d=1, dead_symbols=0, total_symbols=1
            )


class TestRanking:
    def _rows(self) -> list[RefactorQueueRow]:
        return [
            RefactorQueueRow(
                file_path="a.py",
                grade="F",
                health_score=40.0,
                weakest_dimension="complexity",
                churn_30d=20,
                dead_symbols=5,
                total_symbols=50,
            ),
            RefactorQueueRow(
                file_path="b.py",
                grade="D",
                health_score=65.0,
                weakest_dimension="size",
                churn_30d=2,
                dead_symbols=0,
                total_symbols=10,
            ),
            RefactorQueueRow(
                file_path="c.py",
                grade="C",
                health_score=75.0,
                weakest_dimension="duplication",
                churn_30d=40,
                dead_symbols=8,
                total_symbols=20,
            ),
        ]

    def test_rank_orders_by_priority_descending(self) -> None:
        ranked = rank_refactor_queue(self._rows(), top_n=3)
        # c.py outranks the F-grade a.py: 40x churn and a 40% dead ratio beat a
        # worse grade with a 10% dead ratio. Priorities: c 0.464196508,
        # a 0.365342693, b 0.038451430.
        assert [r["file_path"] for r in ranked] == ["c.py", "a.py", "b.py"]

    def test_rank_assigns_one_based_rank(self) -> None:
        ranked = rank_refactor_queue(self._rows(), top_n=3)
        assert [r["rank"] for r in ranked] == [1, 2, 3]

    def test_top_n_truncates(self) -> None:
        ranked = rank_refactor_queue(self._rows(), top_n=2)
        assert len(ranked) == 2

    def test_row_carries_the_computed_priority(self) -> None:
        ranked = rank_refactor_queue(self._rows(), top_n=1)
        assert round(ranked[0]["priority"], 9) == 0.464196508

    def test_ties_break_on_file_path_for_determinism(self) -> None:
        same = RefactorQueueRow(
            file_path="z.py",
            grade="F",
            health_score=40.0,
            weakest_dimension="complexity",
            churn_30d=20,
            dead_symbols=5,
            total_symbols=50,
        )
        other = RefactorQueueRow(
            file_path="a.py",
            grade="F",
            health_score=40.0,
            weakest_dimension="complexity",
            churn_30d=20,
            dead_symbols=5,
            total_symbols=50,
        )
        ranked = rank_refactor_queue([same, other], top_n=2)
        assert [r["file_path"] for r in ranked] == ["a.py", "z.py"]

    def test_action_is_delete_dead_when_dead_ratio_dominates(self) -> None:
        row = RefactorQueueRow(
            file_path="d.py",
            grade="F",
            health_score=40.0,
            weakest_dimension="complexity",
            churn_30d=5,
            dead_symbols=9,
            total_symbols=10,
        )
        ranked = rank_refactor_queue([row], top_n=1)
        assert ranked[0]["action"] == "delete dead"

    def test_action_is_split_when_complexity_is_weakest(self) -> None:
        row = RefactorQueueRow(
            file_path="e.py",
            grade="F",
            health_score=40.0,
            weakest_dimension="complexity",
            churn_30d=5,
            dead_symbols=0,
            total_symbols=10,
        )
        ranked = rank_refactor_queue([row], top_n=1)
        assert ranked[0]["action"] == "split"

    def test_action_is_extract_when_duplication_is_weakest(self) -> None:
        row = RefactorQueueRow(
            file_path="f.py",
            grade="D",
            health_score=60.0,
            weakest_dimension="duplication",
            churn_30d=5,
            dead_symbols=0,
            total_symbols=10,
        )
        ranked = rank_refactor_queue([row], top_n=1)
        assert ranked[0]["action"] == "extract"

    def test_empty_input_gives_empty_queue(self) -> None:
        assert rank_refactor_queue([], top_n=5) == []
