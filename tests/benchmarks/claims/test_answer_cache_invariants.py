#!/usr/bin/env python3
"""RFC-0027 L6.1 value invariant: a repeat certified answer is cheaper.

CLAUDE.md §11: a claim about cost is a **belief** until it is an executable
invariant. The claim here is "the same question asked twice must not cost the
same", so the invariant is a *relationship* — ``p95(repeat) < p95(first)`` —
plus an exact pin on the recorded ``served_from`` value.

**No absolute millisecond ceiling is asserted anywhere in this file.** A
sibling PR failed CI on ``5.07s > 5.0s``; a wall-clock ceiling on a shared
runner measures the runner, not the change. The relationship is
machine-independent and cannot be satisfied by a slow host.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tree_sitter_analyzer.cache.answer_cache import reset_answer_cache
from tree_sitter_analyzer.latency import percentile_ns

pytestmark = pytest.mark.claims_benchmark

_TARGET = "tree_sitter_analyzer/latency.py"
_REPEATS = 5


def _sample_ms(facade, args: dict[str, object]) -> float:
    started = time.perf_counter_ns()
    asyncio.run(facade.execute(dict(args)))
    return (time.perf_counter_ns() - started) / 1_000_000.0


@pytest.fixture
def edit_safe_args() -> dict[str, object]:
    return {"action": "safe", "file_path": _TARGET, "output_format": "json"}


@pytest.fixture
def edit_facade():
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    reset_answer_cache()
    yield build_edit_facade(".")
    reset_answer_cache()


#: Floor on ``p95(first) / p95(repeat)``. Measured on this repo: **~63-70x**
#: (grouped 3371.6 -> 54.3 ms; interleaved 3967.3 -> 58.2 ms). The floor is set
#: far below that because its job is NOT to certify a speed — it is to fail when
#: the cache stops *serving*. ``p95_repeat < p95_first`` alone passed at 1.01x
#: while the real-workflow hit rate was 0%, so a bare inequality is not a fence.
#: Raise this only with a fresh measurement recorded alongside.
_MIN_SPEEDUP_RATIO = 5.0


class TestRepeatIsCheaperThanFirst:
    def test_the_repeat_speedup_ratio_clears_its_ratchet(
        self, edit_facade, edit_safe_args
    ) -> None:
        """A ratchet on the RATIO, not a bare inequality.

        Each "first" sample runs against an empty cache, so the two reservoirs
        are comparable: first = compute, repeat = serve. No absolute millisecond
        ceiling is asserted — the ratio is machine-independent, and a slow host
        slows both halves.
        """
        first_ns: list[int] = []
        repeat_ns: list[int] = []
        for _ in range(_REPEATS):
            reset_answer_cache()
            first_ns.append(int(_sample_ms(edit_facade, edit_safe_args) * 1_000_000))
            repeat_ns.append(int(_sample_ms(edit_facade, edit_safe_args) * 1_000_000))

        p95_first = percentile_ns(first_ns, 95)
        p95_repeat = percentile_ns(repeat_ns, 95)
        ratio = p95_first / max(p95_repeat, 1)
        print(
            f"measured_value: p95_first_ms={p95_first / 1e6:.3f} "
            f"p95_repeat_ms={p95_repeat / 1e6:.3f} ratio={ratio:.1f}x"
        )
        assert ratio >= _MIN_SPEEDUP_RATIO


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
