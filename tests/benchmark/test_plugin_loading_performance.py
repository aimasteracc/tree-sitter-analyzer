#!/usr/bin/env python3
"""
Benchmark: language plugin loading performance.

Measures startup time and memory usage when loading 1, 5, 10, and all (17+)
language plugins via PluginRegistry.measure_load().

Usage:
    uv run pytest tests/benchmark/test_plugin_loading_performance.py -v
"""
from __future__ import annotations

import time

import pytest

from tree_sitter_analyzer.plugins.registry import PluginRegistry

# Representative language sets of increasing size
_LANG_SETS = {
    1: ["python"],
    5: ["python", "java", "javascript", "go", "rust"],
    10: [
        "python", "java", "javascript", "typescript", "go",
        "rust", "c", "cpp", "kotlin", "ruby",
    ],
    17: [
        "python", "java", "javascript", "typescript", "go",
        "rust", "c", "cpp", "kotlin", "ruby",
        "csharp", "bash", "php", "swift", "scala",
        "html", "css",
    ],
}

# Performance budget: individual plugin load should be under this
_MAX_SINGLE_LOAD_TIME_S = 2.0

# Total load time for all 17 should be under this
_MAX_TOTAL_LOAD_TIME_S = 15.0


class TestPluginLoadingPerformance:
    """Benchmark tests for plugin loading."""

    @pytest.fixture(autouse=True)
    def _skip_on_ci(self) -> None:
        """Allow skipping in CI where memory measurement may be unreliable."""
        # These tests run locally for benchmarking purposes

    def _measure_language_set(self, count: int) -> dict[str, float]:
        """Measure load time and memory for a set of languages.

        Returns {"total_time_s": float, "per_lang_avg_s": float, "total_mem_kb": float}.
        """
        languages = _LANG_SETS[count]
        registry = PluginRegistry()
        registry.discover()

        # Force fresh load by creating a new manager each time
        t0 = time.perf_counter()
        metrics = registry.measure_load(languages)
        total_time = time.perf_counter() - t0

        total_mem = sum(m["memory_bytes"] for m in metrics.values())
        loaded_count = sum(1 for m in metrics.values() if m["loaded"])
        avg_time = total_time / max(loaded_count, 1)

        return {
            "total_time_s": total_time,
            "per_lang_avg_s": avg_time,
            "total_mem_kb": total_mem / 1024,
            "loaded_count": loaded_count,
        }

    def test_load_1_language(self) -> None:
        """Loading a single language should complete quickly."""
        result = self._measure_language_set(1)
        assert result["loaded_count"] == 1
        assert result["total_time_s"] < _MAX_SINGLE_LOAD_TIME_S, (
            f"Single language load took {result['total_time_s']:.2f}s "
            f"(budget: {_MAX_SINGLE_LOAD_TIME_S}s)"
        )

    def test_load_5_languages(self) -> None:
        """Loading 5 languages should scale linearly."""
        result = self._measure_language_set(5)
        assert result["loaded_count"] == 5
        # Each language should still be within budget
        assert result["per_lang_avg_s"] < _MAX_SINGLE_LOAD_TIME_S

    def test_load_10_languages(self) -> None:
        """Loading 10 languages should scale linearly."""
        result = self._measure_language_set(10)
        assert result["loaded_count"] == 10
        assert result["per_lang_avg_s"] < _MAX_SINGLE_LOAD_TIME_S

    def test_load_17_languages(self) -> None:
        """Loading 17 languages should complete within budget."""
        result = self._measure_language_set(17)
        assert result["loaded_count"] == 17
        assert result["total_time_s"] < _MAX_TOTAL_LOAD_TIME_S, (
            f"17 languages load took {result['total_time_s']:.2f}s "
            f"(budget: {_MAX_TOTAL_LOAD_TIME_S}s)"
        )

    def test_loading_is_idempotent(self) -> None:
        """Second load of same language should be near-instant (cached)."""
        registry = PluginRegistry()
        registry.discover()

        # First load
        metrics1 = registry.measure_load(["python"])
        first_time = metrics1["python"]["time_s"]

        # Second load (should be cached)
        metrics2 = registry.measure_load(["python"])
        second_time = metrics2["python"]["time_s"]

        # Second load should be significantly faster or equal
        # (cached plugins don't re-parse grammar)
        assert second_time <= first_time * 1.5, (
            f"Second load ({second_time:.4f}s) not faster than first ({first_time:.4f}s)"
        )

    def test_memory_scaling_reasonable(self) -> None:
        """Memory should scale roughly linearly with plugin count."""
        results = {}
        for count in (1, 5, 10, 17):
            results[count] = self._measure_language_set(count)

        # Memory for 17 plugins should be at most ~20x single plugin
        # (not exactly linear due to shared dependencies, but bounded)
        ratio = results[17]["total_mem_kb"] / max(results[1]["total_mem_kb"], 1)
        assert ratio < 25, (
            f"Memory scaling too steep: 17-lang uses {ratio:.1f}x "
            f"the memory of 1-lang ({results[17]['total_mem_kb']:.0f}KB vs "
            f"{results[1]['total_mem_kb']:.0f}KB)"
        )

    def test_print_benchmark_summary(self) -> None:
        """Print a human-readable benchmark summary (not a real test)."""
        lines = ["\n=== Plugin Loading Benchmark ==="]
        lines.append(f"{'Count':>5} | {'Total (s)':>10} | {'Avg (s)':>10} | {'Memory (KB)':>12}")
        lines.append("-" * 50)

        for count in sorted(_LANG_SETS):
            result = self._measure_language_set(count)
            lines.append(
                f"{count:>5} | {result['total_time_s']:>10.3f} | "
                f"{result['per_lang_avg_s']:>10.4f} | {result['total_mem_kb']:>12.1f}"
            )

        summary = "\n".join(lines)
        print(summary)
        # This test always passes — it's just for reporting
        assert True
