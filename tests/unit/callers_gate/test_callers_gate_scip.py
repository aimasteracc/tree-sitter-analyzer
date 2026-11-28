"""``run --scip``: keys, environment, answer storage and the additive SCIP policy.

Without ``--scip`` every key and row is exactly what it was before the option
existed (the identity run relies on that). With it, SCIP may only add callers of
tier ``scip`` and close sites; losing ``complete`` stays a violation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate import keys, report, runner
from benchmarks.callers_gate.layout import Layout
from benchmarks.callers_gate.mcp_client import server_env
from benchmarks.callers_gate.policy import (
    Policy,
    scip_additions_only,
    scip_other_only,
    scip_sites_shrink,
)
from benchmarks.callers_gate.query import slim
from benchmarks.callers_gate.transitions import Change, classify_pair, diff_repo

TSA = {
    "file": "src/x.ts",
    "name": "x",
    "line": 3,
    "end_line": 5,
    "resolution_kind": None,
    "via": None,
    "confidence_tier": "proven",
}
SCIP = {
    **TSA,
    "name": "y",
    "line": 9,
    "resolution_kind": "scip",
    "confidence_tier": "scip",
}
SITE = {"file": "src/a.ts", "line": 4, "callee": "o.m"}
SITE2 = {"file": "src/a.ts", "line": 7, "callee": "p.m"}


def full(**fields: Any) -> dict[str, Any]:
    base = {
        "completeness": "incomplete",
        "completeness_reasons": ["NAME_ONLY_INBOUND"],
        "caller_count": 1,
        "callers": [TSA],
        "name_only_sites": [SITE, SITE2],
        "name_only_sites_total": 2,
        "next_step": "read them",
        "excluded_by_reason": {"names_other_symbol": 2},
    }
    return {**base, **fields}


def change(base: dict[str, Any], head: dict[str, Any]) -> Change:
    kinds = classify_pair({"full": base, "compact": {}}, {"full": head, "compact": {}})
    return Change("hono", ("bare", "src/a.ts", "A.m"), "m", base, head, kinds)


SCIP_POLICY = Policy(scip_evidence=True)


def test_query_key_without_scip_is_unchanged() -> None:
    # The value a run without --scip used before the option existed.
    plain = keys.query_key(targets_sha256="abc")
    assert plain == keys._digest(
        {
            "kind": "query",
            "format": 2,
            "args": keys.QUERY_ARGS,
            "forms": ["full", "compact"],
            "targets": "abc",
        }
    )
    assert keys.query_key(targets_sha256="abc", scip="d") != plain


def test_server_env_extra_and_slim(tmp_path: Path) -> None:
    env = server_env(tmp_path, tmp_path / "p", {"TSA_SCIP_INDEX": "x.scip"})
    assert env["TSA_SCIP_INDEX"] == "x.scip"
    assert "TSA_SCIP_INDEX" not in server_env(tmp_path, tmp_path / "q")
    payload = {"completeness": "complete", "callers": [], "scip": {"status": "used"}}
    assert "scip" not in slim(payload)
    assert slim(payload, keep_scip=True)["scip"] == {"status": "used"}


def test_scip_field_is_never_compared() -> None:
    a = {"full": full(), "compact": {}}
    b = {"full": {**full(), "scip": {"status": "used"}}, "compact": {}}
    assert classify_pair(a, b) == []


def test_scip_input_and_result_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        runner.scip_input(tmp_path, "hono")
    (tmp_path / "hono.scip").write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        runner.scip_input(tmp_path, "hono")
    (tmp_path / "hono.scip.manifest.json").write_text("{}", encoding="utf-8")
    found = runner.scip_input(tmp_path, "hono")
    assert found.index.name == "hono.scip" and len(found.digest) == 24
    layout = Layout(tmp_path)
    path = layout.scip_result("tree", "key", found.digest, "hono", "run1")
    assert "results-scip" in path.parts
    assert layout.result("tree", "key", "hono", "run1") != path


def test_scip_caller_additions_are_allowed() -> None:
    head = full(caller_count=2, callers=[TSA, SCIP], name_only_sites=[SITE2])
    head["name_only_sites_total"] = 1
    c = change(full(), head)
    assert scip_additions_only(c) and scip_sites_shrink(c)
    assert SCIP_POLICY.violations(c) == []
    assert Policy().violations(c)  # the default policy still forbids it


def test_removing_a_tsa_caller_is_a_violation() -> None:
    c = change(full(), full(callers=[SCIP]))
    assert not scip_additions_only(c)
    assert SCIP_POLICY.violations(c)


def test_non_scip_additions_and_wrong_counts_are_violations() -> None:
    other = {**SCIP, "confidence_tier": "proven"}
    assert SCIP_POLICY.violations(
        change(full(), full(caller_count=2, callers=[TSA, other]))
    )
    assert SCIP_POLICY.violations(
        change(full(), full(caller_count=3, callers=[TSA, SCIP]))
    )


def test_new_or_growing_sites_are_violations() -> None:
    new_site = {**SITE, "line": 99}
    c = change(
        full(), full(name_only_sites=[SITE, SITE2, new_site], name_only_sites_total=3)
    )
    assert not scip_sites_shrink(c)
    assert SCIP_POLICY.violations(c) == ["sites"]
    assert not scip_sites_shrink(change(full(), full(name_only_sites=None)))
    assert not scip_sites_shrink(
        change(full(unresolved_sites=None), full(unresolved_sites=[]))
    )
    grown = change(full(non_call_references=0), full(non_call_references=1))
    assert not scip_sites_shrink(grown)


def test_review_lists_may_appear_where_the_base_never_ran_them() -> None:
    head = full(
        non_call_reference_sites=[SITE], non_call_references=1, open_sites={"x": 1}
    )
    assert scip_sites_shrink(change(full(), head))


def test_complete_loss_stays_a_violation() -> None:
    base = full(completeness="complete", completeness_reasons=[])
    head = full(completeness_reasons=["SCIP_UNLISTED_REFERENCE"])
    out = SCIP_POLICY.violations(change(base, head))
    assert any("lost complete" in v for v in out)


def test_unknown_to_incomplete_needs_a_scip_caller() -> None:
    base = full(completeness="unknown", caller_count=0, callers=[])
    head = full(caller_count=1, callers=[SCIP])
    assert SCIP_POLICY.violations(change(base, head)) == []
    assert Policy().violations(change(base, head))
    head_tsa = full(caller_count=1, callers=[TSA])
    assert SCIP_POLICY.violations(change(base, head_tsa))


def test_other_changes_limited_to_next_step_and_scip_exclusions() -> None:
    head = full(
        next_step="new",
        excluded_by_reason={"names_other_symbol": 2, "SCIP_RESOLVED_OTHER": 1},
    )
    c = change(full(), head)
    assert c.kinds == ["other"]
    assert scip_other_only(c) and SCIP_POLICY.violations(c) == []
    bad = change(full(), full(excluded_by_reason={"names_other_symbol": 1}))
    assert not scip_other_only(bad) and SCIP_POLICY.violations(bad) == ["other"]
    verdict = change(full(), full(verdict="X"))
    assert not scip_other_only(verdict)


def test_policy_load_flag() -> None:
    assert Policy.load(None, scip_evidence=True).scip_evidence
    assert not Policy.load(None).scip_evidence


def _row(qual: str, head_full: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "bare",
        "file": "src/a.ts",
        "qual": qual,
        "name": "m",
        "full": head_full,
        "compact": {},
    }


def test_scip_summary_and_section() -> None:
    used = {
        "status": "used",
        "target": {"mapped": True},
        "sites": {"proven_target": 1},
        "added_callers": 1,
        "unlisted_references_total": 0,
        "disagreements_total": 2,
    }
    base_rows = [_row("A.m", full()), _row("B.m", full())]
    head_rows = [
        _row(
            "A.m",
            {
                **full(
                    completeness="complete",
                    completeness_reasons=[],
                    caller_count=2,
                    callers=[TSA, SCIP],
                ),
                "scip": used,
            },
        ),
        _row(
            "B.m",
            {
                **full(),
                "scip": {
                    "status": "used",
                    "target": {"mapped": False, "reason": "ambiguous"},
                },
            },
        ),
    ]
    diff = diff_repo("hono", base_rows, head_rows)
    summary = report.scip_summary(head_rows, diff)
    assert summary["status"] == {"used": 2}
    assert summary["target"] == {"mapped": 1, "ambiguous": 1}
    assert summary["added_callers"] == 1
    assert summary["rows_with_disagreements"] == 1
    assert summary["new_complete"] == [
        {"mode": "bare", "file": "src/a.ts", "qual": "A.m"}
    ]
    lines = report._scip_section([{"repo": "hono", "scip": summary}, {"repo": "zod"}])
    assert any("SCIP evidence" in line for line in lines)
    assert any("`A.m`" in line for line in lines)
    assert report._scip_section([{"repo": "x"}]) == []
