"""RFC-0041 §3：Coverage 值对象的不变量与生产者契约消费。"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.uql import coverage as C


def test_unknown_status_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid completeness status"):
        C.Coverage("partial", ("X",))


def test_complete_coverage_cannot_carry_reasons() -> None:
    with pytest.raises(ValueError, match="cannot carry reasons"):
        C.Coverage("complete", ("X",))


def test_non_complete_coverage_must_name_a_reason() -> None:
    with pytest.raises(ValueError, match="must name a reason"):
        C.Coverage("unknown")


def test_combining_nothing_examined_is_unknown() -> None:
    # 没有检查任何输入不是 complete 的证据。
    assert C.combine([]) == C.Coverage("unknown", (C.PRODUCER_COVERAGE_MISSING,))


def test_combine_keeps_worst_status_and_ordered_reasons() -> None:
    merged = C.combine(
        [C.gap("incomplete", "A"), C.gap("unknown", "B"), C.gap("incomplete", "A")]
    )
    assert merged == C.Coverage("unknown", ("A", "B"))


def test_producer_gap_without_reasons_names_missing_coverage() -> None:
    coverage = C.from_producer({"success": True, "completeness": "incomplete"})
    assert coverage == C.Coverage("incomplete", (C.PRODUCER_COVERAGE_MISSING,))


def test_non_mapping_producer_payload_is_relation_error() -> None:
    assert C.from_producer(None) == C.Coverage("unknown", (C.RELATION_ERROR,))


def test_upstream_unknown_marks_downstream_unknown() -> None:
    effective = C.with_upstream(C.COMPLETE_COVERAGE, C.gap("unknown", "X"))
    assert effective == C.Coverage("unknown", (C.UPSTREAM_UNKNOWN,))
