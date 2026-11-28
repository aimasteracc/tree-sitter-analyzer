"""#1854: confidence ordering and default collapse of unconfirmed-receiver callers.

Trust invariant: ordering and collapsing never change the completeness verdict
or its reason codes, and the listed plus the collapsed callers are exactly the
callers of the full answer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.wrong_complete.tsa_driver import index_project, write_project
from tests.known_answer._compact import (
    UNCONFIRMED_RANK,
    assert_equivalent,
    parse_compact,
    tier_rank,
)
from tree_sitter_analyzer.mcp.tools.callers_compact import compact_callers
from tree_sitter_analyzer.mcp.tools.callers_confidence import (
    CONFIDENCE_FIELD,
    INFERRED,
    PROVEN,
    UNCONFIRMED,
)
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

_FOLD = "+{n} unconfirmed-receiver candidates (include_unconfirmed=true to list)"


def _full(callers: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "success": True,
        "verdict": "INFO",
        "function": "save",
        "caller_count": len(callers),
        "callers": callers,
        "completeness": "incomplete",
        "completeness_reason": "UNRESOLVED_INBOUND",
        "completeness_reasons": ["UNRESOLVED_INBOUND"],
    }
    return {**base, **fields}


def _caller(name: str, resolution: str, kind: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "file": f"{name}.py",
        "line": 1,
        "callee_resolution": resolution,
    }
    if kind is not None:
        entry["resolution_kind"] = kind
    return entry


_MIXED = [
    _caller("opaque", "unknown"),
    _caller("typed", "project", "annotated_receiver"),
    _caller("direct", "project"),
    _caller("builtin_like", "stdlib"),
    _caller("aliased", "project", "import_alias"),
]


def test_compact_orders_by_tier_and_folds_unconfirmed_by_default() -> None:
    out = compact_callers(_full(_MIXED))
    assert out["answer"].split("\n") == [
        "callers of save: 5",
        "direct  direct.py:1  project",
        "aliased  aliased.py:1  import_alias",
        "typed  typed.py:1  annotated_receiver",
        _FOLD.format(n=2),
        "verdict: incomplete (UNRESOLVED_INBOUND); details: format=verbose",
    ]
    assert out["unconfirmed_collapsed"] == 2
    assert_equivalent(_full(_MIXED), out)


def test_include_unconfirmed_lists_every_caller_last() -> None:
    out = compact_callers(_full(_MIXED), include_unconfirmed=True)
    lines = out["answer"].split("\n")
    assert lines[-3:-1] == [
        "opaque  opaque.py:1  unknown",
        "builtin_like  builtin_like.py:1  stdlib",
    ]
    assert "unconfirmed_collapsed" not in out
    assert_equivalent(_full(_MIXED), out, include_unconfirmed=True)


def test_folding_keeps_the_verdict_and_reasons_identical() -> None:
    full = _full(_MIXED)
    folded = compact_callers(full)
    listed = compact_callers(full, include_unconfirmed=True)
    for key in ("completeness", "completeness_reasons", "verdict"):
        assert folded[key] == listed[key]
    assert folded["answer"].split("\n")[-1] == listed["answer"].split("\n")[-1]


def test_a_complete_answer_is_never_downgraded_or_upgraded_by_folding() -> None:
    full = _full(
        [_caller("direct", "project")],
        completeness="complete",
        completeness_reason=None,
        completeness_reasons=[],
    )
    out = compact_callers(full)
    assert out["completeness"] == "complete"
    # No fold: the envelope is exactly the #1853 shape (no extra field, no line).
    assert "unconfirmed_collapsed" not in out
    assert "unconfirmed-receiver" not in out["answer"]


def test_fold_line_sits_before_the_truncation_line() -> None:
    full = _full(_MIXED, caller_count=9, truncated=True)
    lines = compact_callers(full)["answer"].split("\n")
    assert lines[-3:-1] == [_FOLD.format(n=2), "+4 more (raise limit)"]
    assert_equivalent(full, compact_callers(full))


def test_all_unconfirmed_page_lists_nothing_but_counts_all() -> None:
    full = _full([_caller("a", "unknown"), _caller("b", "unknown")])
    out = compact_callers(full)
    assert out["answer"].split("\n")[1] == _FOLD.format(n=2)
    assert_equivalent(full, out)


# -- property: folding is a lossless, verdict-preserving projection ----------

_RESOLUTION = st.sampled_from(
    ["local", "project", "stdlib", "external", "builtin", "unknown", "weird", ""]
)
_KIND = st.sampled_from([None, "annotated_receiver", "import_alias", "guess"])
_ANY_CALLER = st.builds(
    lambda name, line, res, kind: {
        "name": name,
        "file": "m.py",
        "line": line,
        "callee_resolution": res,
        **({"resolution_kind": kind} if kind else {}),
    },
    st.sampled_from(["a", "b", "<module>", "C.m"]),
    st.integers(min_value=0, max_value=50),
    _RESOLUTION,
    _KIND,
)


# slow_ok: pure projection; Hypothesis data generation dominates under the
# coverage tracer (same reason as the #1853 projection property).
@pytest.mark.slow_ok
@settings(max_examples=60, deadline=None, database=None)
@given(
    callers=st.lists(_ANY_CALLER, max_size=12),
    hidden=st.integers(min_value=0, max_value=3),
    completeness=st.sampled_from(["complete", "incomplete", "unknown", None]),
    reasons=st.lists(
        st.sampled_from(["UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND", "X"]),
        max_size=4,
        unique=True,
    ),
)
def test_property_folding_never_changes_the_verdict_or_loses_a_caller(
    callers: list[dict[str, Any]],
    hidden: int,
    completeness: str | None,
    reasons: list[str],
) -> None:
    full = _full(
        callers,
        caller_count=len(callers) + hidden,
        truncated=bool(hidden),
        completeness=completeness,
        completeness_reason=reasons[0] if reasons else None,
        completeness_reasons=reasons,
    )
    folded = compact_callers(full)
    listed = compact_callers(full, include_unconfirmed=True)
    assert_equivalent(full, folded)
    assert_equivalent(full, listed, include_unconfirmed=True)
    for key in ("completeness", "completeness_reasons", "verdict"):
        assert folded[key] == listed[key]
    shape_f, shape_l = parse_compact(folded), parse_compact(listed)
    assert len(shape_f.callers) + shape_f.collapsed == len(shape_l.callers)
    assert shape_f.collapsed == sum(
        1 for c in callers if tier_rank(c) == UNCONFIRMED_RANK
    )
    # Proven callers are always listed, in their original relative order.
    proven = [c["name"] for c in callers if tier_rank(c) == 0]
    assert [row[0] for row in shape_f.callers[: len(proven)]] == proven


# -- live index: verbose tiers, order argument, facade wiring ----------------

_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/a.py": "class A:\n    def save(self):\n        return 1\n",
    "pkg/b.py": "class B:\n    def save(self):\n        return 2\n",
    "pkg/use.py": (
        "from pkg.a import A\n"
        "from pkg.b import B\n\n\n"
        "def opaque(thing):\n    return thing.save()\n\n\n"
        "def typed(b: B):\n    return b.save()\n\n\n"
        "def direct():\n    a = A()\n    return a.save()\n"
    ),
}


@pytest.fixture(scope="module")
def indexed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(tmp_path_factory.mktemp("conf1854"))
    write_project(root, _PROJECT)
    asyncio.run(index_project(root))
    return root


def _nav(root: Path, **args: Any) -> dict[str, Any]:
    return asyncio.run(
        build_nav_facade(str(root)).execute(
            {"action": "callers", "function_name": "save", "limit": 5000, **args}
        )
    )


def _tiers(answer: dict[str, Any]) -> dict[str, str]:
    return {c["name"]: c[CONFIDENCE_FIELD] for c in answer["callers"]}


def test_verbose_callers_each_carry_a_confidence_tier(indexed: Path) -> None:
    full = _nav(indexed, include_bodies=False)
    assert _tiers(full) == {
        "direct": PROVEN,
        "typed": INFERRED,
        "opaque": UNCONFIRMED,
    }


def test_verbose_default_order_is_unchanged_and_order_confidence_sorts(
    indexed: Path,
) -> None:
    default = _nav(indexed, include_bodies=False)
    explicit = _nav(indexed, include_bodies=False, order="index")
    ranked = _nav(indexed, include_bodies=False, order="confidence")
    assert default["callers"] == explicit["callers"]
    assert [c["name"] for c in ranked["callers"]] == ["direct", "typed", "opaque"]
    # Ordering is presentation only: the verdict and every count are identical.
    for key in (
        "completeness",
        "completeness_reasons",
        "completeness_checks",
        "caller_count",
        "unresolved_inbound",
        "name_only_inbound",
    ):
        assert ranked[key] == default[key], key
    assert sorted(map(repr, ranked["callers"])) == sorted(map(repr, default["callers"]))


def test_order_confidence_is_applied_before_the_limit_cut(indexed: Path) -> None:
    capped = _nav(indexed, include_bodies=False, order="confidence", limit=1)
    assert [c["name"] for c in capped["callers"]] == ["direct"]
    assert capped["caller_count"] == 3 and capped["truncated"] is True
    uncapped = _nav(indexed, include_bodies=False)
    assert capped["completeness"] == uncapped["completeness"]
    assert capped["completeness_reasons"] == uncapped["completeness_reasons"]


def test_facade_rejects_an_unknown_order(indexed: Path) -> None:
    out = _nav(indexed, order="random")
    assert out["success"] is False
    assert out["error_code"] == "INVALID_ARGUMENT"


def test_facade_compact_folds_and_drills_down(indexed: Path) -> None:
    full = _nav(indexed, include_bodies=False, order="confidence")
    folded = _nav(indexed, format="compact")
    listed = _nav(indexed, format="compact", include_unconfirmed=True)
    assert_equivalent(full, folded)
    assert_equivalent(full, listed, include_unconfirmed=True)
    assert folded["unconfirmed_collapsed"] == 1
    assert "opaque" not in folded["answer"]
    assert "opaque  pkg/use.py" in listed["answer"]
    assert folded["completeness"] == full["completeness"] == "incomplete"
    assert folded["completeness_reasons"] == full["completeness_reasons"]


def test_facade_rejects_a_non_boolean_include_unconfirmed(indexed: Path) -> None:
    out = _nav(indexed, format="compact", include_unconfirmed="yes")
    assert out["success"] is False
    assert out["error_code"] == "INVALID_ARGUMENT"


def test_codegraph_callers_tool_rejects_an_unknown_order(indexed: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(str(indexed))
    with pytest.raises(ValueError, match="order"):
        asyncio.run(tool.execute({"function_name": "save", "order": "random"}))
