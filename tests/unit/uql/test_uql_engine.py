"""RFC-0041 §3：逐阶段的完整性及其向总体完整性的传播。"""

from __future__ import annotations

import asyncio

import pytest

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


def test_same_file_callees_are_listed() -> None:
    # #1814：同文件被调方（`callee_resolution: "local"`）已解析到定义，曾被当作未解析丢弃。
    fb = FakeBackends(
        {"target": [sym("target")]},
        callees={
            "target": {
                "success": True,
                "callees": [
                    {
                        "name": "helper",
                        "callee_resolution": "local",
                        "callee_resolved_file": "src/a.py",
                    },
                    {
                        "name": "x",
                        "callee_resolution": "project",
                        "callee_resolved_file": "src/x.py",
                    },
                ],
            }
        },
    )
    ex = _run("symbol('target').callees()", fb)
    rows = sorted((r.file, r.name) for r in ex.groups[1].rows)
    assert (rows, ex.stages[1].own) == (
        [("src/a.py", "helper"), ("src/x.py", "x")],
        C.Coverage("unknown", (C.CALLEES_COVERAGE_UNREPORTED,)),
    )


def test_a_local_callee_without_a_resolved_file_is_unresolved() -> None:
    # #1814：没有解析文件的 local（`self.x` 推测）不是已解析的定义。
    fb = FakeBackends(
        {"target": [sym("target")]},
        callees={
            "target": {
                "success": True,
                "callees": [{"name": "x", "callee_resolution": "local"}],
            }
        },
    )
    ex = _run("symbol('target').callees()", fb)
    assert (ex.groups[1].rows, ex.stages[1].own) == (
        [],
        C.Coverage("incomplete", (C.CALLEE_UNRESOLVED,)),
    )


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


def test_ambiguous_method_is_requested_class_qualified() -> None:
    # #1801 上的 Codex P2：同一文件中两个同名方法，在只选中其中一个类时
    # 不得以二者的并集作答。
    fb = FakeBackends(
        {"run": [sym("run", "src/a.py", 3, **{"class": "A"})]}, counts={"run": 2}
    )
    _run("symbol('A.run').callers()", fb)
    assert fb.calls == [("callers", "A.run", "src/a.py")]


def test_callee_rows_keep_the_producer_language() -> None:
    # #1801 上的 Codex P2：language=None 曾导致 filter(language=...) 丢弃 callees。
    fb = FakeBackends(
        {"t": [sym("t")]},
        callees={
            "t": {
                "success": True,
                "callees": [
                    {
                        "name": "x",
                        "language": "python",
                        "callee_resolution": "project",
                        "callee_resolved_file": "src/x.py",
                    }
                ],
            }
        },
    )
    ex = _run("symbol('t').callees().filter(language='python')", fb)
    assert [r.name for r in ex.groups[1].rows] == ["x"]


def test_untested_shares_one_producer_budget(monkeypatch) -> None:
    # #1801 上的 Codex P2：逐行调用 tests() 曾重置 400 次调用的预算。
    import tree_sitter_analyzer.uql.relations as relations

    monkeypatch.setattr(relations, "NODE_BUDGET", 2)
    rows = [(f"f{i}", "src/b.py", i + 1) for i in range(4)]
    fb = _backends(target=callers_payload(*rows))
    ex = _run("symbol('target').callers().untested()", fb)
    unknown = [r.name for r in ex.groups[1].rows if r.membership == "unknown"]
    assert (unknown, ex.stages[2].own.status) == (["f2", "f3"], "unknown")


def test_invalid_filter_regex_is_a_typed_error_with_partial_facts() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3)))
    parsed = parse_query("symbol('target').callers().filter(regex='(')")
    assert isinstance(parsed, Ok)
    result = asyncio.run(run(parsed.value, fb))
    assert isinstance(result, Err)
    assert (result.error.code, result.error.stage_index, result.error.partial) == (
        "UQL_INVALID_ARGUMENT",
        2,
        {"stages_completed": 2, "groups": {"symbol": 1, "callers": 1}},
    )


def test_take_keeps_the_first_rows() -> None:
    rows = [(f"c{i}", "src/b.py", i + 1) for i in range(4)]
    ex = _run(
        "symbol('target').callers().take(2)", _backends(target=callers_payload(*rows))
    )
    assert [r.name for r in ex.groups[1].rows] == ["c0", "c1"]


@pytest.mark.parametrize(
    ("by", "expected"),
    [
        ("line", ["c1", "c2", "c0"]),
        ("file", ["c0", "c2", "c1"]),
        ("name", ["c2", "c1", "c0"]),
    ],
)
def test_sort_orders_rows_descending(by: str, expected: list[str]) -> None:
    rows = [("c0", "src/c.py", 1), ("c1", "src/a.py", 3), ("c2", "src/b.py", 2)]
    fb = _backends(target=callers_payload(*rows))
    ex = _run(f"symbol('target').callers().sort(by='{by}', desc=true)", fb)
    assert [r.name for r in ex.groups[1].rows] == expected


def test_repeated_relation_groups_get_numbered_names() -> None:
    fb = _backends(target=callers_payload(("a", "src/b.py", 3)), a=callers_payload())
    ex = _run("symbol('target').callers().callers()", fb)
    assert [g.name for g in ex.groups] == ["symbol", "callers", "callers#2"]


def test_module_scope_rows_are_not_expanded() -> None:
    fb = _backends(target=callers_payload(("<module>", "src/b.py", 1)))
    _run("symbol('target').callers().callers()", fb)
    assert fb.calls == [("callers", "target", None)]


def test_callers_bfs_stops_at_node_budget(monkeypatch) -> None:
    import tree_sitter_analyzer.uql.relations as relations

    monkeypatch.setattr(relations, "NODE_BUDGET", 1)
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3)),
        a=callers_payload(("b", "src/c.py", 4)),
    )
    ex = _run("symbol('target').callers(depth=2)", fb)
    assert ex.stages[1].own == C.Coverage("incomplete", (C.RELATION_NODE_BUDGET,))


def test_failed_callees_call_is_relation_error() -> None:
    fb = FakeBackends({"t": [sym("t")]}, callees={"t": {"success": False}})
    ex = _run("symbol('t').callees()", fb)
    assert ex.stages[1].own == C.Coverage("unknown", (C.RELATION_ERROR,))


def test_duplicate_frontier_rows_are_not_counted_as_all_definitions() -> None:
    # Codex P2 on #1802: two branches reaching shared.py:helper must not look
    # like "every definition of helper" and drop the file scope.
    fb = _backends(
        target=callers_payload(("left", "src/l.py", 1), ("right", "src/r.py", 1)),
        left=callers_payload(("helper", "src/shared.py", 5)),
        right=callers_payload(("helper", "src/shared.py", 5)),
    )
    fb.counts = {"helper": 2}
    _run("symbol('target').callers(depth=3)", fb)
    assert ("callers", "helper", "src/shared.py") in fb.calls


def test_relation_rows_get_kinds_from_indexed_definitions() -> None:
    # Codex P2 on #1802: filter(kind=...) used to drop every relation row.
    fb = _backends(
        target=callers_payload(("a", "src/b.py", 3), ("<module>", "src/c.py", 1))
    )
    fb.kinds = {("src/b.py", 3, "a"): "function"}
    ex = _run("symbol('target').callers().filter(kind='function')", fb)
    assert [(r.name, r.kind) for r in ex.groups[1].rows] == [("a", "function")]


def test_module_scope_rows_are_kind_module() -> None:
    fb = _backends(target=callers_payload(("<module>", "src/c.py", 1)))
    ex = _run("symbol('target').callers()", fb)
    assert [r.kind for r in ex.groups[1].rows] == ["module"]


def test_callees_stage_respects_the_node_budget(monkeypatch) -> None:
    # Codex P2 on #1802: callees() issued one producer call per selected row.
    import tree_sitter_analyzer.uql.relations as relations

    monkeypatch.setattr(relations, "NODE_BUDGET", 1)
    fb = FakeBackends({"t": [sym("t", "src/a.py", 1), sym("t", "src/b.py", 2)]})
    ex = _run("symbol('t').callees()", fb)
    assert (
        [c for c in fb.calls if c[0] == "callees"],
        C.RELATION_NODE_BUDGET in ex.stages[1].own.reasons,
    ) == ([("callees", "t", None)], True)
