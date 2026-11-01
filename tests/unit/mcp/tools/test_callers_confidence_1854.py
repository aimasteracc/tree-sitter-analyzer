"""#1854: per-caller confidence tier for ``nav action=callers``.

The tier is derived only from fields the resolver already writes on each caller
entry (``resolution_kind`` and ``callee_resolution``). Every value that exists
today has a pinned tier; any other value is the least-confident tier.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.mcp.tools.callers_confidence import (
    CONFIDENCE_FIELD,
    INFERRED,
    ORDER_CONFIDENCE,
    ORDER_INDEX,
    ORDERS,
    PROVEN,
    TIERS,
    UNCONFIRMED,
    caller_confidence,
    invalid_order,
    order_by_confidence,
    tier_rank,
    with_confidence,
)


def _c(**fields: Any) -> dict[str, Any]:
    return {"name": "f", "file": "a.py", "line": 1, **fields}


# -- the mapping table, one row per value the resolver writes ---------------

# callee_resolution: classify_callee_resolution() (codegraph_relation_tool.py)
# writes local / project / stdlib / unknown on a caller entry; the edge table
# can also hold external / builtin (synapse_resolver).
# resolution_kind: callers_annotated.py writes annotated_receiver (RFC-0038)
# and import_alias (#1670); a plain resolved edge carries none.
_TABLE = [
    ({"callee_resolution": "local"}, PROVEN),
    ({"callee_resolution": "project"}, PROVEN),
    ({"callee_resolution": "project", "resolution_kind": "import_alias"}, PROVEN),
    ({"callee_resolution": "local", "resolution_kind": "annotated_receiver"}, INFERRED),
    (
        {"callee_resolution": "project", "resolution_kind": "annotated_receiver"},
        INFERRED,
    ),
    ({"callee_resolution": "stdlib"}, UNCONFIRMED),
    ({"callee_resolution": "external"}, UNCONFIRMED),
    ({"callee_resolution": "builtin"}, UNCONFIRMED),
    ({"callee_resolution": "unknown"}, UNCONFIRMED),
]


@pytest.mark.parametrize(("fields", "tier"), _TABLE)
def test_every_existing_resolution_value_has_a_pinned_tier(
    fields: dict[str, Any], tier: str
) -> None:
    assert caller_confidence(_c(**fields)) == tier


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"callee_resolution": None},
        {"callee_resolution": ""},
        {"callee_resolution": "same_file"},
        {"callee_resolution": "PROJECT"},
        {"callee_resolution": 1},
        {"callee_resolution": "project", "resolution_kind": "guessed"},
        {"callee_resolution": "project", "resolution_kind": 3},
        # A weaker resolution is never upgraded by a stronger-looking kind.
        {"callee_resolution": "unknown", "resolution_kind": "import_alias"},
        {"callee_resolution": "unknown", "resolution_kind": "annotated_receiver"},
        {"resolution_kind": "import_alias"},
    ],
)
def test_any_unknown_value_is_the_least_confident_tier(fields: dict[str, Any]) -> None:
    assert caller_confidence(_c(**fields)) == UNCONFIRMED


def test_a_non_mapping_caller_is_unconfirmed() -> None:
    assert caller_confidence("main") == UNCONFIRMED  # type: ignore[arg-type]


def test_tiers_are_ordered_most_confident_first() -> None:
    assert TIERS == (PROVEN, INFERRED, UNCONFIRMED)
    assert [tier_rank(t) for t in TIERS] == [0, 1, 2]
    assert tier_rank("nonsense") == tier_rank(UNCONFIRMED)


# -- annotation and ordering -------------------------------------------------


def test_with_confidence_adds_the_field_without_mutating_the_input() -> None:
    callers = [_c(callee_resolution="project")]
    out = with_confidence(callers)
    assert out[0][CONFIDENCE_FIELD] == PROVEN
    assert CONFIDENCE_FIELD not in callers[0]
    assert out[0] is not callers[0]


def test_with_confidence_does_not_touch_the_numeric_confidence_field() -> None:
    caller = _c(
        callee_resolution="project",
        resolution_kind="annotated_receiver",
        confidence=0.8,
    )
    out = with_confidence([caller])[0]
    assert out["confidence"] == 0.8
    assert out[CONFIDENCE_FIELD] == INFERRED


def test_with_confidence_skips_non_mapping_entries() -> None:
    assert with_confidence(["x", _c(callee_resolution="local")])[0] == "x"  # type: ignore[list-item]


def test_order_is_stable_within_a_tier() -> None:
    callers = [
        _c(name="u1", callee_resolution="unknown"),
        _c(name="p1", callee_resolution="project"),
        _c(
            name="i1", callee_resolution="project", resolution_kind="annotated_receiver"
        ),
        _c(name="p2", callee_resolution="local"),
        _c(name="u2", callee_resolution="stdlib"),
    ]
    assert [c["name"] for c in order_by_confidence(callers)] == [
        "p1",
        "p2",
        "i1",
        "u1",
        "u2",
    ]
    assert [c["name"] for c in callers][0] == "u1"  # input untouched


def test_order_values_and_validation() -> None:
    assert ORDERS == (ORDER_INDEX, ORDER_CONFIDENCE)
    for value in ORDERS:
        assert invalid_order(value) is None
    error = invalid_order("random")
    assert error is not None and error["success"] is False
    assert error["error_code"] == "INVALID_ARGUMENT"
    for value in ORDERS:
        assert value in error["error"]


# -- properties --------------------------------------------------------------

_RESOLUTION = st.one_of(
    st.sampled_from(["local", "project", "stdlib", "external", "builtin", "unknown"]),
    st.text(max_size=8),
    st.none(),
    st.integers(),
)
_KIND = st.one_of(
    st.sampled_from([None, "annotated_receiver", "import_alias"]),
    st.text(max_size=8),
)
_CALLER = st.builds(
    lambda name, res, kind: {
        "name": name,
        "file": "m.py",
        "line": 1,
        "callee_resolution": res,
        **({"resolution_kind": kind} if kind is not None else {}),
    },
    st.text(min_size=1, max_size=4),
    _RESOLUTION,
    _KIND,
)


# slow_ok: pure function, but Hypothesis data generation took ~5 s locally and
# grows under the coverage tracer (same reason as the #1853 projection property).
@pytest.mark.slow_ok
@settings(max_examples=80, deadline=None, database=None)
@given(callers=st.lists(_CALLER, max_size=15))
def test_property_ordering_is_a_permutation_sorted_by_tier(
    callers: list[dict[str, Any]],
) -> None:
    ordered = order_by_confidence(callers)
    assert sorted(map(repr, ordered)) == sorted(map(repr, callers))
    ranks = [tier_rank(caller_confidence(c)) for c in ordered]
    assert ranks == sorted(ranks)
    for caller in callers:
        assert caller_confidence(caller) in TIERS
