"""PR-4 unit rules: ``open_sites`` enumeration and registration entries."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.callers_absence import AbsenceVerdict
from tree_sitter_analyzer.mcp.tools.callers_compact import compact_callers, site_refs
from tree_sitter_analyzer.mcp.tools.callers_confidence import (
    REGISTRATION,
    caller_confidence,
    order_by_confidence,
)
from tree_sitter_analyzer.mcp.tools.callers_name_only import name_only_lines_exact
from tree_sitter_analyzer.mcp.tools.callers_open_sites import (
    NO_SITE_LIST,
    TRUNCATED,
    open_sites,
)
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, NotChecked
from tree_sitter_analyzer.mcp.tools.callers_registrations import target_registrations

SCOPE = ("f", "a.py")
REVIEW_NAMES = (
    "freshness",
    "target_defined",
    "unindexed_sources",
    "reference_freshness",
    "accessor",
    "non_call_references",
    "registering_decorator",
    "supertype_dispatch",
)


def _passing(**overrides) -> AbsenceVerdict:
    checks = tuple((name, overrides.get(name, Checked(SCOPE))) for name in REVIEW_NAMES)
    return AbsenceVerdict("complete", checks=checks)


def _site(file: str, line: int) -> dict:
    return {"file": file, "line": line, "caller": "use"}


def _edge_result(**fields) -> dict:
    return {"unresolved_inbound_sites": None, **fields}


def _bound(result, reasons, *, exact=True, review=None):
    return open_sites(
        result, reasons, name_only_exact=exact, review=lambda: review or _passing()
    )


# --- edge layer -----------------------------------------------------------


def test_listed_sites_with_passing_review_are_enumerated() -> None:
    result = _edge_result(
        name_only_sites=[_site("u.py", 2), _site("u.py", 9)],
        name_only_sites_total=2,
        unresolved_inbound_sites=[_site("u.py", 2)],
        unresolved_inbound_sites_total=1,
    )

    bound, extra = _bound(result, ["UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND"])

    # u.py:2 sits in both lists; it is one site.
    assert bound == {
        "total": 2,
        "enumerated": True,
        "fields": ["unresolved_inbound_sites", "name_only_sites"],
    }
    assert extra == {}


def test_truncated_list_is_not_enumerated() -> None:
    result = _edge_result(name_only_sites=[_site("u.py", 2)], name_only_sites_total=21)

    bound, _ = _bound(result, ["NAME_ONLY_INBOUND"])

    assert bound == {"enumerated": False, "reason": TRUNCATED}


def test_approximate_name_only_lines_are_not_enumerated() -> None:
    result = _edge_result(name_only_sites=[_site("u.py", 1)], name_only_sites_total=1)

    bound, _ = _bound(result, ["NAME_ONLY_INBOUND"], exact=False)

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def test_edge_reason_without_a_site_list_is_not_enumerated() -> None:
    for reason in (
        "UNATTRIBUTED_CALL_SITES",
        "EMPTY_EVIDENCE_BASE",
        "UNRESOLVED_INBOUND_UNCHECKED",
    ):
        bound, _ = _bound(_edge_result(), [reason])
        assert bound == {"enumerated": False, "reason": NO_SITE_LIST}, reason


def test_unreadable_site_list_is_not_enumerated() -> None:
    bound, _ = _bound(_edge_result(), ["UNRESOLVED_INBOUND"])

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def test_review_is_not_run_when_an_edge_list_fails() -> None:
    calls = []
    result = _edge_result(name_only_sites=[], name_only_sites_total=30)

    open_sites(
        result,
        ["NAME_ONLY_INBOUND"],
        name_only_exact=True,
        review=lambda: calls.append(1),
    )

    assert calls == []


# --- review layer ---------------------------------------------------------


def _edge_listed() -> dict:
    return _edge_result(name_only_sites=[_site("u.py", 2)], name_only_sites_total=1)


def test_review_gate_that_did_not_run_blocks_enumeration() -> None:
    review = _passing(accessor=NotChecked("ACCESSOR_UNCHECKED"))

    bound, _ = _bound(_edge_listed(), ["NAME_ONLY_INBOUND"], review=review)

    # #1923: a gate that could not run on this call is named, not NO_SITE_LIST.
    assert bound == {
        "enumerated": False,
        "reason": "REVIEW_UNCHECKED",
        "unchecked": "ACCESSOR_UNCHECKED",
    }


def test_missing_review_verdict_blocks_enumeration() -> None:
    bound, _ = open_sites(
        _edge_listed(), ["NAME_ONLY_INBOUND"], name_only_exact=True, review=lambda: None
    )

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def test_accessor_blocks_enumeration() -> None:
    review = _passing(accessor=Checked(SCOPE, ("ACCESSOR_NOT_CALL_EDGES",)))

    bound, _ = _bound(_edge_listed(), ["NAME_ONLY_INBOUND"], review=review)

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def test_decorator_blocks_enumeration() -> None:
    review = _passing(registering_decorator=Checked(SCOPE, ("DECORATOR_MAY_REGISTER",)))

    bound, _ = _bound(_edge_listed(), ["NAME_ONLY_INBOUND"], review=review)

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def _non_call_review(sites, total, decorator=None, supertype=None) -> AbsenceVerdict:
    checks = tuple(
        (
            name,
            Checked(SCOPE, ("NON_CALL_REFERENCES",))
            if name == "non_call_references"
            else Checked(SCOPE),
        )
        for name in REVIEW_NAMES[:-2]
    )
    return AbsenceVerdict(
        "unknown",
        "NON_CALL_REFERENCES",
        fields={"non_call_reference_sites": sites, "non_call_references": total},
        checks=checks,
        trailing=(
            ("registering_decorator", decorator or Checked(SCOPE)),
            ("supertype_dispatch", supertype or Checked(SCOPE)),
        ),
    )


def test_non_call_sites_join_the_bound_when_every_later_gate_passes() -> None:
    review = _non_call_review([{"file": "k.py", "line": 6}], 1)

    bound, extra = _bound(_edge_listed(), ["NAME_ONLY_INBOUND"], review=review)

    assert bound == {
        "total": 2,
        "enumerated": True,
        "fields": ["name_only_sites", "non_call_reference_sites"],
    }
    assert extra == {
        "non_call_reference_sites": [{"file": "k.py", "line": 6}],
        "non_call_references": 1,
    }


def test_capped_non_call_sites_are_truncated() -> None:
    sites = [{"file": "k.py", "line": n} for n in range(5)]

    bound, extra = _bound(
        _edge_listed(), ["NAME_ONLY_INBOUND"], review=_non_call_review(sites, 9)
    )

    assert bound == {"enumerated": False, "reason": TRUNCATED}
    assert extra == {}


def test_non_call_with_a_failing_later_gate_is_not_enumerated() -> None:
    review = _non_call_review(
        [{"file": "k.py", "line": 6}], 1, Checked(SCOPE, ("DECORATOR_MAY_REGISTER",))
    )

    bound, _ = _bound({}, ["NON_CALL_REFERENCES"], review=review)

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def test_non_call_with_an_unreadable_later_gate_is_not_enumerated() -> None:
    review = _non_call_review(
        [{"file": "k.py", "line": 6}], 1, NotChecked("DECORATOR_MAY_REGISTER")
    )

    bound, _ = _bound({}, ["NON_CALL_REFERENCES"], review=review)

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


def test_no_blocking_site_at_all_is_not_enumerated() -> None:
    bound, _ = _bound({}, ["SYMBOL_NOT_DEFINED"], review=_passing())

    assert bound == {"enumerated": False, "reason": NO_SITE_LIST}


# --- name-only exactness --------------------------------------------------


def test_name_only_lines_exact_requires_a_call_line_in_every_caller() -> None:
    callers = [{"file": "u.py", "line": 1, "end_line": 3}]

    assert name_only_lines_exact(callers, {"u.py": frozenset({2})}) is True
    assert name_only_lines_exact(callers, {"u.py": frozenset({9})}) is False
    assert name_only_lines_exact(callers, None) is False
    assert name_only_lines_exact([], None) is True


# --- compact projection ---------------------------------------------------


def _unknown_answer(bound: dict, sites: int) -> dict:
    return {
        "function": "Box.fetch",
        "completeness": "unknown",
        "completeness_reasons": ["NAME_ONLY_INBOUND"],
        "caller_count": 0,
        "callers": [],
        "name_only_sites": [_site("u.py", n) for n in range(1, sites + 1)],
        "open_sites": bound,
    }


def test_compact_names_up_to_ten_open_sites() -> None:
    answer = _unknown_answer(
        {"total": 12, "enumerated": True, "fields": ["name_only_sites"]}, 12
    )

    compact = compact_callers(answer)

    assert compact["open_sites"] == {"total": 12, "enumerated": True}
    line = next(x for x in compact["answer"].splitlines() if x.startswith("open:"))
    assert line.startswith("open: 12 sites (exhaustive)  u.py:1; u.py:2")
    assert line.endswith("u.py:10; +2 more (format=verbose)")


def test_compact_omits_a_non_enumerated_bound() -> None:
    answer = _unknown_answer({"enumerated": False, "reason": TRUNCATED}, 3)

    compact = compact_callers(answer)

    assert "open_sites" not in compact
    assert site_refs(answer) == []
    assert "open:" not in compact["answer"]


# --- registration tier ----------------------------------------------------


def test_registration_tier_sits_between_proven_and_inferred() -> None:
    proven = {"callee_resolution": "local"}
    registration = {"callee_resolution": "local", "resolution_kind": "registration"}
    inferred = {"callee_resolution": "local", "resolution_kind": "annotated_receiver"}

    assert caller_confidence(registration) == REGISTRATION
    ordered = order_by_confidence([inferred, registration, proven])
    assert ordered == [proven, registration, inferred]


def test_registration_only_for_the_single_unconditional_definition(tmp_path) -> None:
    source = (
        "import functools\n"
        "from app import app\n\n\n"
        "@app.get('/a')\n"
        "@functools.wraps(len)\n"
        "def a():\n"
        "    return 1\n\n\n"
        "if True:\n"
        "    @app.get('/b')\n"
        "    def b():\n"
        "        return 1\n\n\n"
        "class C:\n"
        "    @app.get('/c')\n"
        "    def m(self):\n"
        "        return 1\n"
    )
    (tmp_path / "r.py").write_text(source, encoding="utf-8")
    root = str(tmp_path)

    (entry,) = target_registrations(root, [("r.py", 7, "python")], "a", "r.py")
    assert (entry["via"], entry["line"]) == ("@app.get('/a')", 5)
    assert target_registrations(root, [("r.py", 13, "python")], "b", "r.py") == []
    assert target_registrations(root, [("r.py", 18, "python")], "C.m", "r.py")
    assert target_registrations(root, [("r.py", 18, "python")], "D.m", "r.py") == []
    assert target_registrations(root, [("r.py", 18, "python")], "m", "other.py") == []
    two = [("r.py", 7, "python"), ("r.py", 18, "python")]
    assert target_registrations(root, two, "a", "r.py") == []
    assert target_registrations(root, [("r.py", 7, "java")], "a", "r.py") == []
    assert target_registrations(root, [("missing.py", 7, "python")], "a", None) == []
