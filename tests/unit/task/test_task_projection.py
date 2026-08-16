"""RFC-0022 plan-steps projection contract (Phase A).

Exact pins for the table-driven plan_steps projection (RFC-0022 §Complete
V1 route decision table): one step per successful exact fragment, fixed
group order, within-group sort by ``(path|nulls-first, symbol|nulls-first,
locator)``, 1-based ordinals, and ``evidence_ids`` containing only that
fragment's ID. Failed/malformed/NO_CONFIG fragments emit no step.
"""

from __future__ import annotations

from tree_sitter_analyzer.task.projection import StepFragment, project_plan_steps


def _fragment(
    route: str,
    path: str | None = None,
    symbol: str | None = None,
    locator: str | None = None,
    evidence_id: str | None = "evidence:e1",
) -> StepFragment:
    return StepFragment(
        route=route,
        path=path,
        symbol=symbol,
        locator=locator,
        evidence_id=evidence_id,
    )


def test_steps_emit_in_fixed_group_order() -> None:
    steps = project_plan_steps(
        [
            _fragment("edit.classify", path="c.py", locator="c.py"),
            _fragment("nav.context", path="a.py", symbol="sym", locator="a.py"),
            _fragment("edit.safe", path="b.py", locator="b.py"),
            _fragment("edit.impact", path="d.py", locator="d.py"),
            _fragment("edit.constraints", path="e.py", locator="e.py"),
            _fragment("edit.ast_diff", path="f.py", locator="f.py"),
        ]
    )
    assert [step["kind"] for step in steps] == [
        "inspect_context",
        "check_file_safety",
        "review_changed_file",
        "check_constraint",
        "review_structure",
        "review_classification",
    ]
    assert [step["ordinal"] for step in steps] == [1, 2, 3, 4, 5, 6]


def test_steps_sort_within_group_by_path() -> None:
    steps = project_plan_steps(
        [
            _fragment("edit.safe", path="z.py", locator="z.py"),
            _fragment("edit.safe", path="a.py", locator="a.py"),
            _fragment("edit.safe", path="m.py", locator="m.py"),
        ]
    )
    assert [step["path"] for step in steps] == ["a.py", "m.py", "z.py"]
    assert [step["ordinal"] for step in steps] == [1, 2, 3]


def test_null_paths_sort_first_within_group() -> None:
    steps = project_plan_steps(
        [
            _fragment("edit.impact", path="b.py", locator="b.py"),
            _fragment("edit.impact", path=None, locator=None),
            _fragment("edit.impact", path="a.py", locator="a.py"),
        ]
    )
    assert [step["path"] for step in steps] == [None, "a.py", "b.py"]


def test_null_symbols_sort_first_within_same_path() -> None:
    steps = project_plan_steps(
        [
            _fragment("nav.context", path="a.py", symbol="zeta", locator="a.py"),
            _fragment("nav.context", path="a.py", symbol=None, locator="a.py"),
        ]
    )
    assert [step["symbol"] for step in steps] == [None, "zeta"]


def test_steps_copy_fields_never_infer() -> None:
    step = project_plan_steps([_fragment("edit.safe", path="a.py", locator="a.py")])[0]
    assert step == {
        "ordinal": 1,
        "kind": "check_file_safety",
        "path": "a.py",
        "symbol": None,
        "evidence_ids": ["evidence:e1"],
    }


def test_evidence_ids_contain_only_that_fragment_id() -> None:
    steps = project_plan_steps(
        [
            _fragment(
                "edit.safe", path="a.py", locator="a.py", evidence_id="evidence:aa"
            ),
            _fragment(
                "edit.safe", path="b.py", locator="b.py", evidence_id="evidence:bb"
            ),
        ]
    )
    assert [step["evidence_ids"] for step in steps] == [
        ["evidence:aa"],
        ["evidence:bb"],
    ]


def test_fragments_without_evidence_emit_no_step() -> None:
    steps = project_plan_steps(
        [
            _fragment("edit.safe", path="a.py", locator="a.py", evidence_id=None),
            _fragment("edit.safe", path="b.py", locator="b.py"),
        ]
    )
    assert [step["path"] for step in steps] == ["b.py"]


def test_empty_fragments_produce_empty_steps() -> None:
    assert project_plan_steps([]) == []


def test_plan_steps_never_reorder_across_groups() -> None:
    steps = project_plan_steps(
        [
            _fragment("edit.classify", path="z.py", locator="z.py"),
            _fragment("nav.context", path="m.py", symbol="s", locator="m.py"),
        ]
    )
    assert [step["kind"] for step in steps] == [
        "inspect_context",
        "review_classification",
    ]
