#!/usr/bin/env python3
"""RFC-0027 L6.1 value invariant: a repeat certified answer is cheaper.

CLAUDE.md §11: a claim about cost is a **belief** until it is an executable
invariant. The claim here is that the same question asked twice must not
recompute the answer, so the invariant is an exact pin on the recorded
``served_from`` value.

The cache key and source-tree fingerprint are intentionally included in the
measured facade path, so wall-clock ratios are not a stable contract on shared
CI runners. The deterministic provenance field is the behavior this test needs
to protect.
"""

from __future__ import annotations

import asyncio

import pytest

from tree_sitter_analyzer.cache.answer_cache import reset_answer_cache

pytestmark = pytest.mark.claims_benchmark

_TARGET = "tree_sitter_analyzer/latency.py"


@pytest.fixture
def edit_safe_args() -> dict[str, object]:
    return {"action": "safe", "file_path": _TARGET, "output_format": "json"}


@pytest.fixture
def edit_facade():
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    reset_answer_cache()
    yield build_edit_facade(".")
    reset_answer_cache()


class TestRepeatIsServedFromCache:
    def test_repeat_is_served_from_cache(self, edit_facade, edit_safe_args) -> None:
        """The repeat must hit the cache; wall-clock ratios are runner-dependent."""
        reset_answer_cache()
        first = asyncio.run(edit_facade.execute(dict(edit_safe_args)))
        repeat = asyncio.run(edit_facade.execute(dict(edit_safe_args)))

        assert first["provenance"]["served_from"] == "computed"
        assert repeat["provenance"]["served_from"] == "cache"


class TestTheInterleavedWorkflowActuallyHits:
    """The case a grouped-repeat harness cannot see (review P1-3).

    ``edit action=safe`` + ``health action=file`` is the pair this project's own
    skills prescribe per edit. A route-scoped component in the eviction prelude
    made them evict each other, so the real-workflow hit rate was **0%** while
    the grouped benchmark reported a 62x speedup. These assert ``served_from``
    directly, so the failure mode is visible as data rather than as a timing.
    """

    @pytest.fixture
    def pair(self):
        from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade
        from tree_sitter_analyzer.mcp.tools.health_facade import build_health_facade

        reset_answer_cache()
        yield (
            (build_edit_facade("."), {"action": "safe", "file_path": _TARGET}),
            (build_health_facade("."), {"action": "file", "file_path": _TARGET}),
        )
        reset_answer_cache()

    @staticmethod
    def _served(facade, args):
        result = asyncio.run(facade.execute({**args, "output_format": "json"}))
        return (result.get("provenance") or {}).get("served_from")

    def test_alternating_the_prescribed_pair_serves_every_repeat_from_cache(
        self, pair
    ) -> None:
        (edit, edit_args), (health, health_args) = pair
        observed = []
        for _ in range(3):
            observed.append(self._served(edit, edit_args))
            observed.append(self._served(health, health_args))
        print(f"measured_value: interleaved_served_from={observed}")
        assert observed == [
            "computed",
            "computed",
            "cache",
            "cache",
            "cache",
            "cache",
        ]


class TestProvenanceIsCostNeutralInTheToonVsJsonComparison:
    """`provenance` must not consume #1322's TOON-vs-JSON headroom.

    #1322 made the default TOON envelope disjoint and left `edit action=safe`
    with a margin of only tens of bytes over plain JSON — thinner than this
    block (~470 B). The concern was that adding it would flip
    `test_facade_toon_wire_not_larger_than_json` red.

    It cannot, and this pins *why* rather than pinning a byte count: the block is
    attached at the **top level of both formats**, identically, so it adds the
    same constant to each side and cancels exactly out of the difference. If a
    future change ever puts it inside `toon_content` (i.e. pays for it twice on
    the TOON path only), this goes red — which is the real hazard.
    """

    @staticmethod
    def _wire(obj):
        """Exactly what ``tool_registration._json_dumps`` puts on the MCP wire.

        ``indent=2``, not compact: measuring with compact ``json.dumps`` makes
        JSON look ~500 B cheaper than it is and reverses the sign of the
        comparison on some targets. Getting this wrong is how a cost claim ends
        up describing a serialisation nobody ships.
        """
        import json

        return len(json.dumps(obj, indent=2, ensure_ascii=False))

    @classmethod
    def _sizes(cls, response):
        whole = cls._wire(response)
        without = cls._wire({k: v for k, v in response.items() if k != "provenance"})
        return whole, without

    def test_provenance_does_not_change_the_toon_minus_json_delta(
        self, edit_facade
    ) -> None:
        base = {"action": "safe", "file_path": _TARGET}
        json_resp = asyncio.run(edit_facade.execute({**base, "output_format": "json"}))
        reset_answer_cache()
        toon_resp = asyncio.run(edit_facade.execute({**base, "output_format": "toon"}))

        json_with, json_without = self._sizes(json_resp)
        toon_with, toon_without = self._sizes(toon_resp)
        delta_with = toon_with - json_with
        delta_without = toon_without - json_without
        print(
            f"measured_value: toon_minus_json_with_provenance={delta_with} "
            f"without={delta_without} provenance_bytes={toon_with - toon_without}"
        )
        assert delta_with == delta_without

    def test_provenance_costs_the_same_on_both_formats(self, edit_facade) -> None:
        base = {"action": "safe", "file_path": _TARGET}
        json_resp = asyncio.run(edit_facade.execute({**base, "output_format": "json"}))
        reset_answer_cache()
        toon_resp = asyncio.run(edit_facade.execute({**base, "output_format": "toon"}))
        json_cost = self._sizes(json_resp)[0] - self._sizes(json_resp)[1]
        toon_cost = self._sizes(toon_resp)[0] - self._sizes(toon_resp)[1]
        assert json_cost == toon_cost


class TestProvenanceDoesNotBreakCompaction:
    """The visibility block rides the compact control surface — it must not
    make compaction pointless.

    CLAUDE.md §11 rule 1: adding a field to ``TOON_CONTROL_SURFACE`` is a cost
    claim, so it needs an executable invariant. The relationship asserted is the
    documented ``compact < default`` one, measured on the **facade** path (where
    ``provenance`` exists) rather than on the inner tool (where it does not, so
    the existing cost invariants cannot see this change at all).

    No byte ceiling is asserted: the payload size tracks the target file's
    dependents and test list, which are not this test's business.
    """

    def test_compact_toon_stays_strictly_smaller_than_default_toon(
        self, edit_facade
    ) -> None:
        import json

        base = {"action": "safe", "file_path": _TARGET}
        default = asyncio.run(edit_facade.execute({**base, "output_format": "toon"}))
        reset_answer_cache()
        compact = asyncio.run(
            edit_facade.execute({**base, "output_format": "toon", "compact_only": True})
        )
        assert "provenance" in default
        assert "provenance" in compact
        default_bytes = len(json.dumps(default))
        compact_bytes = len(json.dumps(compact))
        print(
            f"measured_value: default_toon_bytes={default_bytes} "
            f"compact_toon_bytes={compact_bytes}"
        )
        assert compact_bytes < default_bytes


@pytest.fixture
def isolated_facade(tmp_path):
    """A facade on an isolated project, for the provenance pins only.

    The two tests below assert a cache HIT, so they must not run against the
    live repo root: the generation stamp covers the whole tree, so anything else
    writing into the repo between the two calls correctly invalidates the entry
    and the pin would go red for a reason unrelated to the cache. The p95
    measurement above deliberately keeps the real repo — that is where the 3.4 s
    it is measuring comes from.
    """
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    (tmp_path / "target.py").write_text(
        "def thing():\n    return 1\n", encoding="utf-8"
    )
    reset_answer_cache()
    yield build_edit_facade(str(tmp_path))
    reset_answer_cache()


class TestServedFromIsPinned:
    @staticmethod
    def _ask(facade):
        return asyncio.run(
            facade.execute(
                {"action": "safe", "file_path": "target.py", "output_format": "json"}
            )
        )

    def test_first_call_records_exactly_computed(self, isolated_facade) -> None:
        assert self._ask(isolated_facade)["provenance"]["served_from"] == "computed"

    def test_repeat_call_records_exactly_cache(self, isolated_facade) -> None:
        self._ask(isolated_facade)
        assert self._ask(isolated_facade)["provenance"]["served_from"] == "cache"
