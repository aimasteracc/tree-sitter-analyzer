"""#1923: a budget miss in the ``open_sites`` review run is never silent.

An ``unknown`` answer whose edge layer failed reruns the review gates only for
the ``open_sites`` bound. Those gates have wall-clock budgets (the non-call
reference scan, the absence freshness scan). When one ran out, the bound used to
read ``NO_SITE_LIST`` -- indistinguishable from a structural gap -- and the
compact answer silently dropped ``open_sites``. Under load, the separate compact
call could land on the other side of the budget from the full call, so the same
code gave two different compact answers.

Now the bound says ``REVIEW_UNCHECKED`` and names the gate code, the compact
answer carries it, and the verdict is still ``unknown`` (never ``complete``).
"""

from __future__ import annotations

import pytest

from tests.known_answer._compact import assert_equivalent
from tree_sitter_analyzer.mcp.tools import callers_absence, relation_freshness
from tree_sitter_analyzer.mcp.tools.callers_absence import AbsenceVerdict
from tree_sitter_analyzer.mcp.tools.callers_compact import (
    REVIEW_UNCHECKED,
    compact_callers,
    unchecked_bound,
)
from tree_sitter_analyzer.mcp.tools.callers_open_sites import NO_SITE_LIST, open_sites
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, NotChecked
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

SCOPE = ("Box.fetch", "box.py")
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
_BOX = "class Box:\n    def fetch(self):\n        return 1\n"
_USER = "def use(thing):\n    return thing.fetch()\n"


def _review(stop: str, outcome: NotChecked) -> AbsenceVerdict:
    """Gates up to ``stop`` pass; ``stop`` did not run; later gates are absent
    (``_assess_absence`` returns at the first gate that does not pass)."""
    checks = []
    for name in REVIEW_NAMES:
        if name == stop:
            checks.append((name, outcome))
            break
        checks.append((name, Checked(SCOPE)))
    return AbsenceVerdict("unknown", outcome.reason, checks=tuple(checks))


def _edge_listed() -> dict:
    return {
        "name_only_sites": [{"file": "user.py", "line": 2, "caller": "use"}],
        "name_only_sites_total": 1,
    }


def _bound(review: AbsenceVerdict) -> dict:
    bound, extra = open_sites(
        _edge_listed(),
        ["NAME_ONLY_INBOUND"],
        name_only_exact=True,
        review=lambda: review,
    )
    assert extra == {}
    return bound


# --- the bound names a transient cause --------------------------------------


@pytest.mark.parametrize(
    ("gate", "code"),
    [
        ("reference_freshness", "NON_CALL_REFERENCES_UNCHECKED"),
        ("freshness", "SOURCE_SCOPE_UNKNOWN"),
        ("target_defined", "SYMBOL_DEFINITION_UNCHECKED"),
        ("unindexed_sources", "UNINDEXED_SOURCE_UNCHECKED"),
        ("accessor", "ACCESSOR_UNCHECKED"),
    ],
)
def test_a_gate_that_ran_out_of_budget_is_named(gate: str, code: str) -> None:
    assert _bound(_review(gate, NotChecked(code))) == {
        "enumerated": False,
        "reason": REVIEW_UNCHECKED,
        "unchecked": code,
    }


def test_a_structural_skip_stays_no_site_list() -> None:
    assert _bound(_review("freshness", NotChecked("MISSING_INDEX"))) == {
        "enumerated": False,
        "reason": NO_SITE_LIST,
    }


def test_a_transient_gate_after_a_structural_failure_stays_no_site_list() -> None:
    checks = (
        ("freshness", Checked(SCOPE)),
        ("target_defined", Checked(SCOPE)),
        ("unindexed_sources", Checked(SCOPE)),
        ("reference_freshness", Checked(SCOPE)),
        ("accessor", Checked(SCOPE, ("ACCESSOR_NOT_CALL_EDGES",))),
        ("non_call_references", NotChecked("NON_CALL_REFERENCES_UNCHECKED")),
    )
    review = AbsenceVerdict("unknown", "ACCESSOR_NOT_CALL_EDGES", checks=checks)

    assert _bound(review) == {"enumerated": False, "reason": NO_SITE_LIST}


# --- the compact projection keeps it ----------------------------------------


def _answer(bound: dict) -> dict:
    return {
        "function": "Box.fetch",
        "verdict": "NOT_FOUND",
        "completeness": "unknown",
        "completeness_reasons": ["NAME_ONLY_INBOUND"],
        "caller_count": 0,
        "callers": [],
        **_edge_listed(),
        "open_sites": bound,
    }


def test_compact_carries_an_unchecked_bound_instead_of_dropping_it() -> None:
    bound = {
        "enumerated": False,
        "reason": REVIEW_UNCHECKED,
        "unchecked": "NON_CALL_REFERENCES_UNCHECKED",
    }

    compact = compact_callers(_answer(bound))

    assert compact["open_sites"] == bound
    assert compact["answer"].split("\n") == [
        "callers of Box.fetch: 0",
        "open: unchecked (NON_CALL_REFERENCES_UNCHECKED); re-ask or format=verbose",
        "verdict: unknown (NAME_ONLY_INBOUND); details: format=verbose",
    ]
    assert compact["completeness"] == "unknown"


def test_compact_still_omits_a_structural_non_bound() -> None:
    compact = compact_callers(_answer({"enumerated": False, "reason": NO_SITE_LIST}))

    assert "open_sites" not in compact
    assert "open:" not in compact["answer"]


def test_an_unchecked_bound_never_reaches_a_complete_answer() -> None:
    bound = {"enumerated": False, "reason": REVIEW_UNCHECKED, "unchecked": "X"}
    answer = {**_answer(bound), "completeness": "complete", "completeness_reasons": []}

    compact = compact_callers(answer)

    assert compact["completeness"] == "complete"  # the full answer's own verdict
    assert "open_sites" not in compact  # a bound only ever rides on unknown
    assert unchecked_bound({"open_sites": {"enumerated": True, "total": 1}}) is None
    assert unchecked_bound({"open_sites": "junk"}) is None


# --- end to end: force the budget miss on the bound's review run -------------


async def _index(root) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    files = {
        "main.py": "def helper():\n    return 1\n\n\ndef main():\n    return helper()\n",
        "box.py": _BOX,
        "user.py": _USER,
    }
    for rel_path, text in files.items():
        (root / rel_path).write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _ask(root: str, fmt: str) -> dict:
    """The same route the callers gate takes: ``nav action=callers format=...``."""
    return await build_nav_facade(root).execute(
        {
            "action": "callers",
            "function_name": "Box.fetch",
            "file_path": "box.py",
            "include_bodies": False,
            "format": fmt,
        }
    )


@pytest.mark.asyncio
async def test_forced_budget_miss_is_named_in_full_and_compact(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = await _index(tmp_path)
    quiet_full = await _ask(root, "verbose")
    quiet_compact = await _ask(root, "compact")
    assert quiet_full["open_sites"]["enumerated"] is True
    assert quiet_compact["open_sites"] == {"total": 1, "enumerated": True}

    # The non-call reference scan runs out of time on every call from here on.
    monkeypatch.setattr(callers_absence, "scan_budget_seconds", lambda files: -1.0)
    full = await _ask(root, "verbose")
    compact = await _ask(root, "compact")

    expected = {
        "enumerated": False,
        "reason": REVIEW_UNCHECKED,
        "unchecked": "NON_CALL_REFERENCES_UNCHECKED",
    }
    # The verdict and reasons are untouched: the edge layer decided them.
    for answer in (full, compact):
        assert answer["completeness"] == "unknown"
        assert answer["completeness_reasons"] == quiet_full["completeness_reasons"]
        assert answer["open_sites"] == expected
    assert (
        "open: unchecked (NON_CALL_REFERENCES_UNCHECKED); re-ask or format=verbose"
        in compact["answer"]
    )
    # The independent test-side parser agrees: compact is the full answer's projection.
    assert_equivalent(full, compact_callers(full))
    assert_equivalent(full, compact)


@pytest.mark.asyncio
async def test_forced_freshness_budget_miss_is_named(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = await _index(tmp_path)
    monkeypatch.setattr(relation_freshness, "_ABSENCE_SCAN_DEADLINE_SECONDS", -1.0)

    compact = await _ask(root, "compact")

    assert compact["completeness"] == "unknown"
    assert compact["open_sites"] == {
        "enumerated": False,
        "reason": REVIEW_UNCHECKED,
        "unchecked": "SOURCE_SCOPE_UNKNOWN",
    }
