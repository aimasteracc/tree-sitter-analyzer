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


class TestRepeatIsCheaperThanFirst:
    def test_p95_repeat_is_strictly_below_p95_first(
        self, edit_facade, edit_safe_args
    ) -> None:
        """The relationship, measured over independent cache generations.

        Each "first" sample runs against an empty cache (the cache is reset),
        so the two reservoirs are comparable: first = compute, repeat = serve.
        """
        first_ns: list[int] = []
        repeat_ns: list[int] = []
        for _ in range(_REPEATS):
            reset_answer_cache()
            first_ns.append(int(_sample_ms(edit_facade, edit_safe_args) * 1_000_000))
            repeat_ns.append(int(_sample_ms(edit_facade, edit_safe_args) * 1_000_000))

        p95_first = percentile_ns(first_ns, 95)
        p95_repeat = percentile_ns(repeat_ns, 95)
        print(
            f"measured_value: p95_first_ms={p95_first / 1e6:.3f} "
            f"p95_repeat_ms={p95_repeat / 1e6:.3f}"
        )
        assert p95_repeat < p95_first


class TestServedFromIsPinned:
    def test_first_call_records_exactly_computed(
        self, edit_facade, edit_safe_args
    ) -> None:
        result = asyncio.run(edit_facade.execute(dict(edit_safe_args)))
        assert result["provenance"]["served_from"] == "computed"

    def test_repeat_call_records_exactly_cache(
        self, edit_facade, edit_safe_args
    ) -> None:
        asyncio.run(edit_facade.execute(dict(edit_safe_args)))
        result = asyncio.run(edit_facade.execute(dict(edit_safe_args)))
        assert result["provenance"]["served_from"] == "cache"
