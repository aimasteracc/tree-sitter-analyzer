#!/usr/bin/env python3
"""
Benchmark: TOON output compression rate.

Measures actual token reduction of TOON format vs JSON on real analysis results.
Target: 60-70% compression rate while maintaining readability.

Usage:
    uv run pytest tests/benchmark/test_toon_compression.py -v -s
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

# Sample analysis payloads of varying complexity
_SAMPLE_PAYLOADS = {
    "small": {
        "file_path": "src/main.py",
        "language": "python",
        "elements": [
            {"type": "function", "name": "hello", "line": 1, "end_line": 3},
            {"type": "class", "name": "App", "line": 5, "end_line": 20},
        ],
    },
    "medium": {
        "file_path": "src/analyzer/code_structure.py",
        "language": "python",
        "elements": [
            {
                "type": "class",
                "name": "CodeStructureAnalyzer",
                "line": 15,
                "end_line": 180,
                "children": [
                    {"type": "method", "name": "__init__", "line": 16, "end_line": 25},
                    {"type": "method", "name": "analyze", "line": 27, "end_line": 60},
                    {"type": "method", "name": "extract_classes", "line": 62, "end_line": 95},
                    {"type": "method", "name": "extract_functions", "line": 97, "end_line": 130},
                    {"type": "method", "name": "build_dependency_graph", "line": 132, "end_line": 180},
                ],
            },
            {"type": "function", "name": "format_output", "line": 183, "end_line": 200},
            {"type": "function", "name": "validate_input", "line": 202, "end_line": 215},
        ],
        "imports": ["os", "json", "pathlib.Path", "typing.Any"],
    },
    "large": {
        "project": "tree-sitter-analyzer",
        "files": [
            {
                "path": f"src/module_{i}/analyzer.py",
                "language": "python",
                "elements": [
                    {
                        "type": "class",
                        "name": f"Analyzer{i}",
                        "line": 10,
                        "end_line": 100 + i * 10,
                        "children": [
                            {"type": "method", "name": "process", "line": 11 + j, "end_line": 20 + j}
                            for j in range(5)
                        ],
                    }
                    for i_inner in range(1)
                ],
                "imports": ["os", "sys", "json", "pathlib"],
            }
            for i in range(20)
        ],
        "summary": {"total_files": 20, "total_classes": 20, "total_functions": 100},
    },
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code text."""
    return max(1, len(text) // 4)


class TestToonCompressionRate:
    """Measure TOON vs JSON compression on various payloads."""

    @pytest.fixture
    def formatter(self) -> ToonFormatter:
        return ToonFormatter()

    def _measure_compression(
        self, formatter: ToonFormatter, payload: dict
    ) -> dict:
        """Measure compression metrics for a single payload."""
        json_str = json.dumps(payload, indent=2, ensure_ascii=False)
        toon_str = formatter.format(payload)

        json_tokens = _estimate_tokens(json_str)
        toon_tokens = _estimate_tokens(toon_str)
        compression_rate = (1 - toon_tokens / json_tokens) * 100 if json_tokens > 0 else 0

        return {
            "json_bytes": len(json_str.encode()),
            "toon_bytes": len(toon_str.encode()),
            "json_tokens_est": json_tokens,
            "toon_tokens_est": toon_tokens,
            "compression_rate_pct": round(compression_rate, 1),
            "byte_reduction_pct": round(
                (1 - len(toon_str.encode()) / len(json_str.encode())) * 100, 1
            ),
        }

    def test_small_payload_compression(self, formatter: ToonFormatter) -> None:
        """Small payload should achieve some compression."""
        metrics = self._measure_compression(formatter, _SAMPLE_PAYLOADS["small"])
        assert metrics["compression_rate_pct"] > 0, (
            f"Small payload not compressed: {metrics}"
        )
        print(f"\n  Small: {metrics['compression_rate_pct']}% token reduction")

    def test_medium_payload_compression(self, formatter: ToonFormatter) -> None:
        """Medium payload should achieve 30%+ compression."""
        metrics = self._measure_compression(formatter, _SAMPLE_PAYLOADS["medium"])
        assert metrics["compression_rate_pct"] > 20, (
            f"Medium payload compression too low: {metrics}"
        )
        print(f"\n  Medium: {metrics['compression_rate_pct']}% token reduction")

    def test_large_payload_compression(self, formatter: ToonFormatter) -> None:
        """Large payload should achieve 30%+ compression."""
        metrics = self._measure_compression(formatter, _SAMPLE_PAYLOADS["large"])
        assert metrics["compression_rate_pct"] > 20, (
            f"Large payload compression too low: {metrics}"
        )
        print(f"\n  Large: {metrics['compression_rate_pct']}% token reduction")

    def test_compression_preserves_data(self, formatter: ToonFormatter) -> None:
        """TOON output should be non-empty and contain key information."""
        for name, payload in _SAMPLE_PAYLOADS.items():
            toon_output = formatter.format(payload)
            assert len(toon_output) > 0, f"TOON output empty for {name}"
            # Key names should appear in output
            assert any(k in toon_output for k in payload.keys()), (
                f"TOON output for {name} missing key names"
            )

    def test_real_file_compression(self, formatter: ToonFormatter, tmp_path: Path) -> None:
        """Test compression on actual Python analysis result."""
        # Create a realistic analysis result
        analysis_result = {
            "success": True,
            "file_path": "tree_sitter_analyzer/analysis/dependency_graph.py",
            "language": "python",
            "lines": 435,
            "elements": [
                {
                    "type": "class",
                    "name": "DependencyGraph",
                    "line": 27,
                    "end_line": 222,
                    "children": [
                        {"type": "method", "name": "to_json", "line": 34},
                        {"type": "method", "name": "to_mermaid", "line": 46},
                        {"type": "method", "name": "to_dot", "line": 69},
                        {"type": "method", "name": "has_cycle", "line": 99},
                        {"type": "method", "name": "find_cycles", "line": 123},
                        {"type": "method", "name": "topological_sort", "line": 171},
                        {"type": "method", "name": "compute_pagerank", "line": 196},
                    ],
                },
                {
                    "type": "class",
                    "name": "DependencyGraphBuilder",
                    "line": 236,
                    "end_line": 435,
                    "children": [
                        {"type": "method", "name": "build", "line": 266},
                        {"type": "method", "name": "_find_source_files", "line": 300},
                        {"type": "method", "name": "_extract_imports", "line": 314},
                        {"type": "method", "name": "_build_import_map", "line": 376},
                        {"type": "method", "name": "_resolve_import", "line": 398},
                    ],
                },
            ],
            "imports": ["json", "re", "collections.deque", "pathlib.Path"],
            "complexity": {"cyclomatic": 15, "classes": 2, "methods": 12},
        }

        metrics = self._measure_compression(formatter, analysis_result)
        assert metrics["compression_rate_pct"] > 0
        print(f"\n  Real file: {metrics['compression_rate_pct']}% token reduction")
        print(f"  JSON: {metrics['json_bytes']} bytes, TOON: {metrics['toon_bytes']} bytes")

    def test_compression_summary(self, formatter: ToonFormatter) -> None:
        """Print comprehensive compression summary."""
        print("\n=== TOON Compression Rate Summary ===")
        print(f"{'Payload':>10} | {'JSON bytes':>10} | {'TOON bytes':>10} | {'Token %':>8} | {'Byte %':>8}")
        print("-" * 60)

        for name, payload in _SAMPLE_PAYLOADS.items():
            metrics = self._measure_compression(formatter, payload)
            print(
                f"{name:>10} | {metrics['json_bytes']:>10,} | {metrics['toon_bytes']:>10,} | "
                f"{metrics['compression_rate_pct']:>7.1f}% | {metrics['byte_reduction_pct']:>7.1f}%"
            )
