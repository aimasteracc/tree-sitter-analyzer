"""Transition classifier and policy evaluation of the callers gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate.policy import Policy, PolicyError
from benchmarks.callers_gate.transitions import RowSetMismatch, classify_pair, diff_repo


def row(
    completeness: str = "incomplete",
    reasons: list[str] | None = None,
    callers: list[dict[str, Any]] | None = None,
    qual: str = "A.f",
    sites: list[dict[str, Any]] | None = None,
    compact: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    callers = (
        callers
        if callers is not None
        else [{"file": "a.py", "name": "g", "line": 3, "end_line": 9}]
    )
    full = {
        "completeness": completeness,
        "completeness_reasons": reasons
        if reasons is not None
        else ["NAME_ONLY_INBOUND"],
        "caller_count": len(callers),
        "callers": callers,
        "non_call_reference_sites": sites or [],
        **extra,
    }
    return {
        "mode": "bare",
        "file": "a.py",
        "qual": qual,
        "name": qual,
        "full": full,
        "compact": {
            "completeness": compact or completeness,
            "open_sites": None,
            "answer": "x",
        },
        "seconds": 1.0,
    }


def test_identical_rows_have_no_change_even_when_timings_differ() -> None:
    a, b = row(), row()
    b["seconds"] = 99.0
    assert classify_pair(a, b) == []


def test_new_complete_with_dropped_blocker_sites() -> None:
    a = row(
        "incomplete",
        ["NON_CALL_REFERENCES"],
        sites=[{"file": "a.py", "line": 806, "callee": "f"}],
    )
    b = row("complete", [])
    assert classify_pair(a, b) == ["verdict", "reasons", "sites"]


def test_caller_count_and_caller_list_changes_are_separate_kinds() -> None:
    more = row(
        callers=[
            {"file": "a.py", "name": "g", "line": 3, "end_line": 9},
            {"file": "b.py", "name": "h", "line": 1, "end_line": 2},
        ]
    )
    assert classify_pair(row(), more) == ["caller_count"]
    moved = row(callers=[{"file": "a.py", "name": "g", "line": 4, "end_line": 9}])
    assert classify_pair(row(), moved) == ["callers"]


def test_caller_order_alone_is_not_a_change() -> None:
    two = [
        {"file": "a.py", "name": "g", "line": 3, "end_line": 9},
        {"file": "b.py", "name": "h", "line": 1, "end_line": 2},
    ]
    a, b = row(callers=two), row(callers=list(reversed(two)))
    a["compact"]["answer"] = "head\ng a.py:3\nh b.py:1"
    b["compact"]["answer"] = "head\nh b.py:1\ng a.py:3"
    assert classify_pair(a, b) == []


def test_compact_disagreement_new_on_head_and_query_errors() -> None:
    assert classify_pair(
        row("complete", []), row("complete", [], compact="unknown")
    ) == ["compact"]
    bad = row()
    bad["full"]["__error__"] = "isError"
    assert classify_pair(row(), bad) == ["error"]


def test_other_payload_changes_are_reported_as_other() -> None:
    assert classify_pair(row(next_step="a"), row(next_step="b")) == ["other"]


def test_diff_repo_counts_transitions_and_refuses_partial_sets() -> None:
    base = [row("incomplete", qual="A.f"), row("complete", [], qual="A.g")]
    head = [row("complete", [], qual="A.f"), row("complete", [], qual="A.g")]
    d = diff_repo("r", base, head)
    assert d.transitions == {"incomplete->complete": 1, "complete->complete": 1}
    assert d.identical == 1
    assert [c.key[2] for c in d.changes] == ["A.f"]
    assert d.changes[0].new_complete
    with pytest.raises(RowSetMismatch, match="different targets"):
        diff_repo("r", base, head[:1])
    with pytest.raises(RowSetMismatch, match="duplicate"):
        diff_repo("r", base + base[:1], head + head[:1])


def _change(a: dict[str, Any], b: dict[str, Any]):  # type: ignore[no-untyped-def]
    return diff_repo("gson", [a], [b]).changes[0]


def test_default_policy_allows_new_completes_and_reason_changes() -> None:
    policy = Policy()
    assert (
        policy.violations(
            _change(
                row(
                    "incomplete",
                    ["NON_CALL_REFERENCES"],
                    sites=[{"file": "a.py", "line": 1, "callee": "f"}],
                ),
                row("complete", []),
            )
        )
        == []
    )
    assert (
        policy.violations(
            _change(
                row("unknown", ["NON_CALL_REFERENCES"]),
                row("unknown", ["OVERRIDE_DISPATCH"]),
            )
        )
        == []
    )


def test_default_policy_flags_lost_complete_other_transitions_and_caller_changes() -> (
    None
):
    policy = Policy()
    assert policy.violations(_change(row("complete", []), row("incomplete"))) == [
        "lost complete complete->incomplete"
    ]
    assert policy.violations(_change(row("unknown"), row("incomplete"))) == [
        "transition unknown->incomplete"
    ]
    more = row(
        callers=[
            {"file": "a.py", "name": "g", "line": 3, "end_line": 9},
            {"file": "b.py", "name": "h", "line": 1, "end_line": 2},
        ]
    )
    assert policy.violations(_change(row(), more)) == ["caller_count"]


def test_site_change_without_a_verdict_or_reason_change_is_flagged() -> None:
    a = row(sites=[{"file": "a.py", "line": 1, "callee": "f"}])
    assert Policy().violations(_change(a, row())) == ["sites"]
    assert Policy(allow_site_changes=True).violations(_change(a, row())) == []


def test_policy_file_flags_and_items(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "allow_transitions": ["*->complete", "unknown->incomplete"],
                "allow_items": [
                    {"repo": "gson", "qual": "A.f", "kinds": ["caller_count"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    policy = Policy.load(path)
    assert policy.violations(_change(row("unknown"), row("incomplete"))) == []
    more = row(
        callers=[
            {"file": "a.py", "name": "g", "line": 3, "end_line": 9},
            {"file": "b.py", "name": "h", "line": 1, "end_line": 2},
        ]
    )
    assert policy.violations(_change(row(), more)) == []
    assert (
        Policy.load(None, ["complete->incomplete"]).violations(
            _change(row("complete", []), row("incomplete"))
        )
        == []
    )


def test_policy_refuses_malformed_files_and_unallowable_kinds(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicyError, match="unreadable"):
        Policy.load(path)
    path.write_text(json.dumps({"allow_transition": []}), encoding="utf-8")
    with pytest.raises(PolicyError, match="unknown policy keys"):
        Policy.load(path)
    path.write_text(
        json.dumps({"allow_items": [{"repo": "r", "qual": "q", "kinds": ["error"]}]}),
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="can never be allowed"):
        Policy.load(path)
    with pytest.raises(PolicyError, match="A->B"):
        Policy.load(None, ["complete"])
    bad = row()
    bad["full"]["__error__"] = "boom"
    assert Policy(allow_caller_changes=True, allow_site_changes=True).violations(
        _change(row(), bad)
    ) == ["error"]


def test_delta_lists_removed_and_added_callers_and_sites() -> None:
    a = row(
        "incomplete",
        ["NON_CALL_REFERENCES"],
        sites=[{"file": "a.py", "line": 806, "callee": None}],
    )
    b = row(
        "incomplete",
        ["NON_CALL_REFERENCES"],
        callers=[
            {"file": "a.py", "name": "g", "line": 3, "end_line": 9},
            {"file": "c.py", "name": "k", "line": 5, "end_line": 6},
        ],
    )
    change = diff_repo("gson", [a], [b]).changes[0]
    delta = change.delta()
    assert delta["non_call_reference_sites"] == {"-": [("a.py", 806)], "+": []}
    assert delta["callers"]["-"] == []
    assert delta["callers"]["+"] == [("c.py", "k", 5, 6, None, None)]
