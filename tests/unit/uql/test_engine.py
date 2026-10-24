"""RFC-0041 §3: per-stage completeness and its propagation to the total."""

from __future__ import annotations

import asyncio

from tests.unit.uql._fake_backends import FakeBackends, callers_payload, sym
from tree_sitter_analyzer.uql import coverage as C
from tree_sitter_analyzer.uql.engine import run
from tree_sitter_analyzer.uql.errors import INDEX_UNAVAILABLE, Err, Ok
from tree_sitter_analyzer.uql.parser import parse_query


def _run(text: str, backends: FakeBackends):
    parsed = parse_query(text)
    assert isinstance(parsed, Ok), parsed
    result = asyncio.run(run(parsed.value, backends))
    assert isinstance(result, Ok), result
    return result.value


def _stages(execution) -> list[tuple[str, int, str]]:
    return [(s.op, s.count, s.effective.status) for s in execution.stages]


def _backends(**callers) -> FakeBackends:
    return FakeBackends({"target": [sym("target")]}, callers)


def test_all_stages_complete_gives_complete_total() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3)))
    ex = _run("symbol('target').callers()", fb)
    assert (_stages(ex), ex.total) == (
        [("symbol", 1, "complete"), ("callers", 1, "complete")],
        C.COMPLETE_COVERAGE,
    )


def test_producer_reasons_are_consumed_verbatim() -> None:
    fb = _backends(
        target=callers_payload(
            ("a", "src/b.py", 3),
            completeness="incomplete",
            reasons=("UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND"),
        )
    )
    ex = _run("symbol('target').callers()", fb)
    assert ex.stages[1].own == C.Coverage(
        "incomplete", ("UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND")
    )


def test_one_unknown_input_makes_stage_and_total_unknown() -> None:
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3), ("b", "src/c.py", 4)),
        a=callers_payload(),
        b=callers_payload(completeness="unknown", reasons=("NON_CALL_REFERENCES",)),
    )
    ex = _run("symbol('target').callers().callers()", fb)
    assert (ex.stages[2].effective.status, ex.total.status) == ("unknown", "unknown")


def test_downstream_complete_stage_inherits_upstream_gap() -> None:
    fb = _backends(
        target=callers_payload(
            ("a", "src/b.py", 3),
            completeness="incomplete",
            reasons=("UNRESOLVED_INBOUND",),
        ),
    )
    ex = _run("symbol('target').callers().tests()", fb)
    assert (ex.stages[2].own, ex.stages[2].effective) == (
        C.COMPLETE_COVERAGE,
        C.Coverage("incomplete", (C.UPSTREAM_INCOMPLETE,)),
    )


def test_missing_producer_completeness_is_unknown_not_complete() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3), completeness=None))
    ex = _run("symbol('target').callers()", fb)
    assert ex.stages[1].own == C.Coverage("unknown", (C.PRODUCER_COVERAGE_MISSING,))


def test_failed_producer_call_is_unknown_relation_error() -> None:
    fb = _backends(target={"success": False, "error": "boom"})
    ex = _run("symbol('target').callers()", fb)
    assert ex.stages[1].own == C.Coverage("unknown", (C.RELATION_ERROR,))


def test_listed_fewer_than_counted_is_relation_limit() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3), caller_count=9))
    ex = _run("symbol('target').callers()", fb)
    assert ex.stages[1].own == C.Coverage("incomplete", (C.RELATION_LIMIT,))


def test_source_gate_failure_makes_source_non_complete() -> None:
    fb = FakeBackends(
        {"target": [sym("target")]}, gate=C.gap("incomplete", "UNINDEXED_SOURCE_FILES")
    )
    ex = _run("symbol('target')", fb)
    assert ex.total == C.Coverage("incomplete", ("UNINDEXED_SOURCE_FILES",))


def test_unproven_selector_predicate_is_unknown() -> None:
    fb = FakeBackends(selection=[sym("a")])
    ex = _run(".function:calls(#target)", fb)
    assert (ex.total.status, ex.stages[0].own.reasons) == (
        "unknown",
        (C.SELECTOR_PREDICATE_UNPROVEN,),
    )


def test_exhaustive_selector_is_complete() -> None:
    fb = FakeBackends(selection=[sym("a")])
    assert _run(".function:in(src/)", fb).total == C.COMPLETE_COVERAGE


def test_index_not_ready_is_typed_error() -> None:
    parsed = parse_query("symbol('x')")
    assert isinstance(parsed, Ok)
    result = asyncio.run(run(parsed.value, FakeBackends(state="empty")))
    assert isinstance(result, Err) and result.error.code == INDEX_UNAVAILABLE


def test_tests_relation_walks_one_test_helper() -> None:
    fb = _backends(
        target=callers_payload(
            ("test_direct", "tests/test_a.py", 5), ("_helper", "tests/test_a.py", 9)
        ),
        _helper=callers_payload(("test_via_helper", "tests/test_a.py", 20)),
    )
    ex = _run("symbol('target').tests()", fb)
    assert sorted(r.name for r in ex.groups[1].rows) == [
        "test_direct",
        "test_via_helper",
    ]


def test_nested_test_helper_is_flagged_not_dropped_silently() -> None:
    fb = _backends(
        target=callers_payload(("_helper", "tests/test_a.py", 9)),
        _helper=callers_payload(("_outer", "tests/test_a.py", 30)),
    )
    ex = _run("symbol('target').tests()", fb)
    assert ex.stages[1].own == C.Coverage("incomplete", (C.TEST_HELPER_DEPTH,))


def test_untested_keeps_undecided_rows_flagged_unknown() -> None:
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3), ("c", "src/c.py", 4)),
        a=callers_payload(completeness="unknown", reasons=("NON_CALL_REFERENCES",)),
        c=callers_payload(("test_c", "tests/test_c.py", 1)),
    )
    ex = _run("symbol('target').callers().untested()", fb)
    rows = [(r.name, r.membership) for r in ex.groups[1].rows]
    assert (rows, ex.stages[2].own) == (
        [("a", "unknown")],
        C.Coverage("unknown", (C.MEMBERSHIP_UNKNOWN,)),
    )


def test_untested_with_complete_coverage_is_complete() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3)))
    ex = _run("symbol('target').callers().untested()", fb)
    assert ([r.name for r in ex.groups[1].rows], ex.total) == (
        ["a"],
        C.COMPLETE_COVERAGE,
    )


def test_callers_depth_bound_is_not_a_gap() -> None:
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3)),
        a=callers_payload(("b", "src/c.py", 4)),
    )
    ex = _run("symbol('target').callers(depth=1)", fb)
    assert ex.total == C.COMPLETE_COVERAGE


def test_impact_frontier_at_depth_cap_is_depth_limit() -> None:
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3)),
        a=callers_payload(("b", "src/c.py", 4)),
    )
    ex = _run("symbol('target').impact(depth=1)", fb)
    assert ex.stages[1].own == C.Coverage("incomplete", (C.RELATION_DEPTH_LIMIT,))


def test_impact_exhausted_closure_is_complete_and_tags_tests() -> None:
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3)),
        a=callers_payload(("test_a", "tests/test_b.py", 4)),
    )
    ex = _run("symbol('target').impact()", fb)
    roles = sorted((r.name, r.role) for r in ex.groups[1].rows)
    assert (roles, ex.total) == (
        [("a", "caller"), ("test_a", "test")],
        C.COMPLETE_COVERAGE,
    )


def test_callees_are_never_complete() -> None:
    fb = FakeBackends(
        {"target": [sym("target")]},
        callees={
            "target": {
                "success": True,
                "callees": [
                    {
                        "name": "x",
                        "callee_resolution": "project",
                        "callee_resolved_file": "src/x.py",
                    }
                ],
            }
        },
    )
    ex = _run("symbol('target').callees()", fb)
    assert ex.stages[1].own == C.Coverage("unknown", (C.CALLEES_COVERAGE_UNREPORTED,))


def test_unresolved_callees_make_a_lower_bound() -> None:
    fb = FakeBackends(
        {"target": [sym("target")]},
        callees={"target": {"success": True, "callees": [{"name": "len"}]}},
    )
    ex = _run("symbol('target').callees()", fb)
    assert ex.stages[1].own == C.Coverage("incomplete", (C.CALLEE_UNRESOLVED,))


def test_each_node_is_asked_once_per_query() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3)))
    _run("symbol('target').callers().tests()", fb)
    assert fb.calls.count(("callers", "target", None)) == 1


def test_filter_refinement_keeps_coverage_and_narrows_rows() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3), ("b", "lib/c.py", 4)))
    ex = _run("symbol('target').callers().filter(path='src/')", fb)
    assert ([r.name for r in ex.groups[1].rows], ex.total) == (
        ["a"],
        C.COMPLETE_COVERAGE,
    )


def test_every_definition_of_a_name_is_one_union_request() -> None:
    defs = [sym("run", "src/a.py", 1), sym("run", "src/b.py", 5)]
    fb = FakeBackends({"run": defs}, counts={"run": 2})
    _run("symbol('run').callers()", fb)
    assert fb.calls == [("callers", "run", None)]


def test_subset_of_definitions_keeps_per_file_requests() -> None:
    fb = FakeBackends({"run": [sym("run", "src/a.py", 1)]}, counts={"run": 2})
    _run("symbol('run').callers()", fb)
    assert fb.calls == [("callers", "run", "src/a.py")]
