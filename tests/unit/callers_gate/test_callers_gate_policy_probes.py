"""Policy, compact-form and ground-truth repros from the gate review.

Each case is a synthetic base/head pair that the original gate passed although
the head answer hides a real caller (or cannot be confirmed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate import report
from benchmarks.callers_gate.oracle_truth import check_compact, check_rows
from benchmarks.callers_gate.policy import Policy, PolicyError
from benchmarks.callers_gate.transitions import classify_pair, diff_repo

C1 = {
    "file": "src/x.ts",
    "name": "x",
    "line": 3,
    "end_line": None,
    "resolution_kind": None,
    "via": None,
    "confidence_tier": "proven",
}
C2 = {**C1, "file": "src/y.ts", "name": "y", "line": 9}


def row(
    full: dict[str, Any], compact: dict[str, Any], qual: str = "A.m"
) -> dict[str, Any]:
    return {
        "mode": "bare",
        "file": "src/a.ts",
        "qual": qual,
        "name": "m",
        "full": full,
        "compact": compact,
    }


def _answer(*callers: dict[str, Any], verdict: str = "complete") -> str:
    lines = [f"callers of A.m: {len(callers)}"]
    lines += [f"{c['name']}  {c['file']}:{c['line']}  project" for c in callers]
    return "\n".join([*lines, f"verdict: {verdict}"])


def _violations(
    base: dict[str, Any], head: dict[str, Any], policy: Policy
) -> list[str]:
    diff = diff_repo("hono", [base], [head])
    return [v for c in diff.changes for v in policy.violations(c)]


def test_p1_a_compact_answer_that_loses_a_caller_is_a_violation_and_a_failure() -> None:
    full = {"completeness": "complete", "caller_count": 2, "callers": [C1, C2]}
    base = row(full, {"completeness": "complete", "answer": _answer(C1, C2)})
    head = row(full, {"completeness": "complete", "answer": _answer(C1)})
    assert classify_pair(base, head) == ["other"]
    assert _violations(base, head, Policy()) == ["other"]
    kinds = [f["kind"] for f in check_compact("hono", [head])]
    assert kinds == ["compact_callers_mismatch"]
    assert check_compact("hono", [base]) == []


def test_p2_a_compact_complete_the_full_answer_does_not_confirm_always_fails() -> None:
    full = {
        "completeness": "incomplete",
        "completeness_reasons": ["R"],
        "caller_count": 1,
        "callers": [C1],
    }
    base = row(full, {"completeness": "unknown", "answer": "x"})
    head = row(full, {"completeness": "complete", "answer": _answer(C1)})
    kinds = [f["kind"] for f in check_compact("hono", [head])]
    assert kinds == ["compact_unconfirmed_complete"]
    # regardless of the base: an identical base row fails the same way
    assert [f["kind"] for f in check_compact("hono", [head, base])] == [
        "compact_unconfirmed_complete"
    ]


def test_other_changes_can_be_allowed_explicitly() -> None:
    a = row({"completeness": "unknown", "callers": [], "next_step": "a"}, {})
    b = row({"completeness": "unknown", "callers": [], "next_step": "b"}, {})
    assert _violations(a, b, Policy()) == ["other"]
    assert _violations(a, b, Policy(allow_other_changes=True)) == []


def test_p4_allow_items_need_file_and_mode(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(
        json.dumps(
            {"allow_items": [{"repo": "hono", "qual": "A.m", "kinds": ["callers"]}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="file"):
        Policy.load(path)
    path.write_text(
        json.dumps(
            {
                "allow_items": [
                    {
                        "repo": "hono",
                        "qual": "A.m",
                        "file": "src/a.ts",
                        "mode": "qualified",
                        "kinds": ["caller_count"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = Policy.load(path)
    two = row({"completeness": "complete", "caller_count": 2, "callers": [C1, C2]}, {})
    one = row({"completeness": "complete", "caller_count": 1, "callers": [C1]}, {})
    # the item names the qualified mode: the bare row is not covered
    assert _violations(two, one, policy) == ["caller_count"]


def test_an_allow_item_without_file_and_mode_never_matches() -> None:
    loose = Policy(
        allow_items=({"repo": "hono", "qual": "A.m", "kinds": ["caller_count"]},)
    )
    two = row({"completeness": "complete", "caller_count": 2, "callers": [C1, C2]}, {})
    one = row({"completeness": "complete", "caller_count": 1, "callers": [C1]}, {})
    assert _violations(two, one, loose) == ["caller_count"]


def test_p5_a_confidence_tier_change_is_a_caller_change() -> None:
    a = row(
        {"completeness": "complete", "caller_count": 1, "callers": [C1]},
        {"completeness": "complete"},
    )
    b = row(
        {
            "completeness": "complete",
            "caller_count": 1,
            "callers": [{**C1, "confidence_tier": "inferred"}],
        },
        {"completeness": "complete"},
    )
    assert classify_pair(a, b) == ["callers"]
    assert _violations(a, b, Policy()) == ["callers"]


def test_p3_every_changed_head_complete_is_sent_to_the_oracle() -> None:
    two = row({"completeness": "complete", "caller_count": 2, "callers": [C1, C2]}, {})
    one = row({"completeness": "complete", "caller_count": 1, "callers": [C1]}, {})
    diff = diff_repo("hono", [two], [one])
    assert report.oracle_keys([diff]) == [("bare", "src/a.ts", "A.m")]
    gone = row({"completeness": "incomplete", "callers": []}, {})
    assert report.oracle_keys([diff_repo("hono", [two], [gone])]) == []


GT2 = {
    "callers": {"src/a.py::A.m": [["src/y.py", "y", 9, "self", 10]]},
    "module_callers": {},
    "defs": [{"key": "src/a.py::A.m"}],
    "open_sites": {
        "m": [["src/y.py", "y", 10], ["src/z.py", "z", 4], ["src/w.py", "<module>", 7]]
    },
}


def _py_row(
    completeness: str, callers: list[dict[str, Any]], **full: Any
) -> dict[str, Any]:
    return {
        "mode": "bare",
        "file": "src/a.py",
        "qual": "A.m",
        "name": "m",
        "full": {"completeness": completeness, "callers": callers, **full},
    }


def test_p6_an_open_site_is_not_coverage_on_a_complete_row() -> None:
    head = _py_row(
        "complete",
        [{"file": "src/x.py", "name": "x", "line": 3, "end_line": 5}],
        open_sites={"enumerated": True, "fields": ["name_only_sites"]},
        name_only_sites=[{"file": "src/y.py", "line": 10, "callee": "m"}],
    )
    result = check_rows("rich", [head], set(), gt2=GT2, labels=None)
    assert [f["kind"] for f in result["failures"]] == ["gt2_miss"]


def test_open_sites_still_cover_an_enumerated_unknown() -> None:
    head = _py_row(
        "unknown",
        [],
        open_sites={"enumerated": True, "fields": ["name_only_sites"]},
        name_only_sites=[{"file": "src/y.py", "line": 10, "callee": "m"}],
    )
    assert check_rows("rich", [head], set(), gt2=GT2, labels=None)["failures"] == []


def test_gt2_open_sites_outside_listed_callers_are_residual_on_changed_completes() -> (
    None
):
    listed = [
        {"file": "src/y.py", "name": "y", "line": 9, "end_line": 12},
        {"file": "src/w.py", "name": "<module>", "line": 7, "end_line": 7},
    ]
    head = _py_row("complete", listed)
    result = check_rows(
        "rich",
        [head],
        set(),
        gt2=GT2,
        labels=None,
        changed={("bare", "src/a.py", "A.m")},
    )
    assert result["failures"] == []
    assert [(r["file"], r["line"]) for r in result["residual"]] == [("src/z.py", 4)]
    unchanged = check_rows(
        "rich", [head], {("bare", "src/a.py", "A.m")}, gt2=GT2, labels=None
    )
    assert unchanged["residual"] == []


def test_label_coverage_comes_from_the_oracle_not_from_spans() -> None:
    labels = {"m": {"file": "src/a.ts", "calls": [["c.ts", 5]], "refs": []}}
    head = row(
        {
            "completeness": "complete",
            "callers": [{"file": "c.ts", "name": "g", "line": 1, "end_line": 20}],
        },
        {},
    )
    # without an oracle verdict the site is not covered (fail closed)
    failed = check_rows("hono", [head], set(), gt2=None, labels=labels)
    assert [f["kind"] for f in failed["failures"]] == ["label_call_miss"]
    cover = {(("bare", "src/a.ts", "A.m"), "c.ts", 5): True}
    ok = check_rows("hono", [head], set(), gt2=None, labels=labels, label_cover=cover)
    assert ok["failures"] == []


def test_1930_a_label_marked_external_fails_every_complete() -> None:
    """kotlinpoet: an override of a JDK interface (``Filer.createSourceFile``) is
    called by code outside the project; no project caller list makes it complete."""
    labels = {
        "m": {"file": "src/a.ts", "calls": [], "refs": [], "external": "javax Filer"}
    }
    complete = row({"completeness": "complete", "callers": []}, {})
    result = check_rows("kotlinpoet", [complete], set(), gt2=None, labels=labels)
    assert [f["kind"] for f in result["failures"]] == ["label_external_complete"]
    unchanged = check_rows(
        "kotlinpoet", [complete], {("bare", "src/a.ts", "A.m")}, gt2=None, labels=labels
    )
    assert unchanged["failures"] == []
    assert [p["kind"] for p in unchanged["preexisting"]] == ["label_external_complete"]
    unknown = row({"completeness": "unknown", "callers": []}, {})
    quiet = check_rows("kotlinpoet", [unknown], set(), gt2=None, labels=labels)
    assert quiet["failures"] == [] and quiet["preexisting"] == []


def test_a_partial_run_is_never_a_plain_pass() -> None:
    clean = {
        "repo": "gson",
        "violations": [],
        "truth_failures": [],
        "residual": [],
    }
    assert report.exit_code([clean]) == report.EXIT_PASS
    assert report.exit_code([clean], partial=True) == report.EXIT_REVIEW
    assert (
        report.exit_code([clean], partial=True, allow_partial=True) == report.EXIT_PASS
    )
    failing = {**clean, "violations": [{"qual": "x"}]}
    assert report.exit_code([failing], partial=True) == report.EXIT_FAIL


def test_the_budget_note_never_reads_as_a_dismissal() -> None:
    note = report.BUDGET_NOTE
    assert "still a violation" in note
    assert "load-dependent;" not in note


@pytest.mark.slow_ok  # real git repo + the oracle subprocess
def test_p3_an_allowed_caller_drop_on_a_complete_still_meets_the_grep_oracle(
    tmp_path: Path,
) -> None:
    import subprocess
    import sys

    from benchmarks.callers_gate.layout import Layout
    from benchmarks.callers_gate.runner import RepoRun

    pytest.importorskip("tree_sitter_typescript")
    root = tmp_path / "repo"
    files = {
        "package.json": json.dumps({"name": "demo"}),
        "src/a.ts": "export class A {\n  static m() { return 1; }\n}\n",
        "src/x.ts": "import { A } from './a';\n\nexport function x() { return A.m(); }\n",
        "src/y.ts": "import { A } from './a';\n"
        + "\n" * 7
        + "export function y() { return A.m(); }\n",
    }
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8", newline="\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "."], check=True, capture_output=True
    )

    def answer(*callers: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": "bare",
            "file": "src/a.ts",
            "qual": "A.m",
            "name": "m",
            "full": {
                "completeness": "complete",
                "caller_count": len(callers),
                "callers": list(callers),
            },
            "compact": {"completeness": "complete", "answer": _answer(*callers)},
        }

    run = RepoRun(
        "axios",
        index_key="k",
        base_index_key="k",
        root=root,
        base_rows=[answer(C1, C2)],
        head_rows=[answer(C1)],
    )
    out = report.judge_repo(
        Layout(tmp_path / "gate"),
        Path(sys.executable),
        run,
        Policy(allow_caller_changes=True),
        {},
        tmp_path / "work",
    )
    assert out["violations"] == []
    assert [(r["file"], r["line"]) for r in out["residual"]] == [("src/y.ts", 9)]
    assert report.exit_code([out]) == report.EXIT_REVIEW
