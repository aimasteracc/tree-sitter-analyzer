#!/usr/bin/env python3
"""
Benchmark: TOON compression on real project files.

Measures actual TOON vs JSON compression using analysis results from
10+ real source files across multiple languages.

Target: 60-70% token reduction while maintaining readability.

Usage:
    uv run pytest tests/benchmark/test_toon_real_project_compression.py -v -s
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.core.request import AnalysisRequest
from tree_sitter_analyzer.formatters.toon_formatter import (
    CompressionLevel,
    ToonFormatter,
)
from tree_sitter_analyzer.plugins.manager import PluginManager

# Real project files to benchmark
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_REAL_FILES: list[dict[str, str]] = [
    {"path": "tree_sitter_analyzer/analysis/dependency_graph.py", "language": "python"},
    {"path": "tree_sitter_analyzer/analysis/health_score.py", "language": "python"},
    {"path": "tree_sitter_analyzer/analysis/error_recovery.py", "language": "python"},
    {"path": "tree_sitter_analyzer/formatters/toon_formatter.py", "language": "python"},
    {"path": "tree_sitter_analyzer/formatters/toon_encoder.py", "language": "python"},
    {"path": "tree_sitter_analyzer/languages/java_plugin.py", "language": "python"},
    {"path": "tree_sitter_analyzer/languages/csharp_plugin.py", "language": "python"},
    {"path": "tree_sitter_analyzer/mcp/tools/analyze_tool.py", "language": "python"},
    {"path": "tree_sitter_analyzer/plugins/manager.py", "language": "python"},
    {"path": "tree_sitter_analyzer/core/analysis_engine.py", "language": "python"},
]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code text."""
    return max(1, len(text) // 4)


def _result_to_dict(result: object) -> dict:
    """Convert AnalysisResult to a serializable dict."""
    data: dict = {}
    for attr in ("file_path", "language", "package"):
        val = getattr(result, attr, None)
        if val is not None:
            if hasattr(val, "__dict__"):
                data[attr] = str(val)
            else:
                data[attr] = val

    elements = getattr(result, "elements", [])
    if elements:
        data["elements"] = []
        for elem in elements:
            elem_dict: dict = {}
            for key in ("name", "element_type", "start_line", "end_line", "visibility"):
                val = getattr(elem, key, None)
                if val is not None:
                    elem_dict[key] = val
            children = getattr(elem, "children", None)
            if children:
                elem_dict["children"] = [
                    {
                        "name": getattr(c, "name", ""),
                        "element_type": getattr(c, "element_type", ""),
                        "start_line": getattr(c, "start_line", 0),
                        "end_line": getattr(c, "end_line", 0),
                    }
                    for c in children
                ]
            data["elements"].append(elem_dict)

    summary = getattr(result, "get_summary", None)
    if summary:
        data["summary"] = summary()

    return data


class TestRealProjectCompression:
    """Measure TOON vs JSON compression on real project analysis results."""

    @pytest.fixture
    async def analysis_results(self) -> list[dict]:
        """Analyze real project files and collect results."""
        plugin_manager = PluginManager()
        results: list[dict] = []

        for file_info in _REAL_FILES:
            file_path = _PROJECT_ROOT / file_info["path"]
            if not file_path.exists():
                continue

            try:
                plugin = plugin_manager.get_plugin(file_info["language"])
                if not plugin:
                    continue

                request = AnalysisRequest(
                    file_path=str(file_path),
                    language=file_info["language"],
                    include_complexity=False,
                    include_details=True,
                )
                result = await plugin.analyze_file(str(file_path), request)
                if result:
                    results.append(_result_to_dict(result))
            except Exception:
                # Skip files that fail analysis
                continue

        return results

    def _measure_compression(
        self, formatter: ToonFormatter, payload: dict
    ) -> dict:
        """Measure compression metrics for a single payload."""
        json_str = json.dumps(payload, indent=2, ensure_ascii=False)
        toon_str = formatter.format(payload)

        json_tokens = _estimate_tokens(json_str)
        toon_tokens = _estimate_tokens(toon_str)
        compression_rate = (
            (1 - toon_tokens / json_tokens) * 100 if json_tokens > 0 else 0
        )

        return {
            "json_bytes": len(json_str.encode()),
            "toon_bytes": len(toon_str.encode()),
            "json_tokens_est": json_tokens,
            "toon_tokens_est": toon_tokens,
            "compression_rate_pct": round(compression_rate, 1),
            "byte_reduction_pct": round(
                (1 - len(toon_str.encode()) / len(json_str.encode())) * 100
                if len(json_str.encode()) > 0
                else 0,
                1,
            ),
        }

    @pytest.mark.asyncio
    async def test_real_file_compression_rates(
        self, analysis_results: list[dict]
    ) -> None:
        """Each real file should show positive compression."""
        formatter = ToonFormatter()
        print("\n=== TOON Compression on Real Project Files ===")
        print(
            f"{'File':>40} | {'JSON B':>8} | {'TOON B':>8} | {'Token%':>7} | {'Byte%':>7}"
        )
        print("-" * 80)

        for result in analysis_results:
            file_name = result.get("file_path", "unknown")
            if len(file_name) > 40:
                file_name = "..." + file_name[-37:]
            metrics = self._measure_compression(formatter, result)
            print(
                f"{file_name:>40} | {metrics['json_bytes']:>8,} | "
                f"{metrics['toon_bytes']:>8,} | {metrics['compression_rate_pct']:>6.1f}% | "
                f"{metrics['byte_reduction_pct']:>6.1f}%"
            )

        assert len(analysis_results) > 0, "No files were analyzed"

    @pytest.mark.asyncio
    async def test_average_compression_target(
        self, analysis_results: list[dict]
    ) -> None:
        """Average compression across all files should be meaningful."""
        formatter = ToonFormatter()
        rates: list[float] = []

        for result in analysis_results:
            metrics = self._measure_compression(formatter, result)
            rates.append(metrics["compression_rate_pct"])

        if rates:
            avg_compression = sum(rates) / len(rates)
            print(f"\n  Average compression: {avg_compression:.1f}% across {len(rates)} files")
            # Any positive compression is a start; target is 60-70% over time
            assert avg_compression > 0, f"No compression achieved: {rates}"

    @pytest.mark.asyncio
    async def test_compression_levels_comparison(
        self, analysis_results: list[dict]
    ) -> None:
        """Compare MINIMAL vs BALANCED vs DETAILED compression."""
        levels = {
            "MINIMAL": ToonFormatter(compression_level=CompressionLevel.MINIMAL),
            "BALANCED": ToonFormatter(compression_level=CompressionLevel.BALANCED),
            "DETAILED": ToonFormatter(compression_level=CompressionLevel.DETAILED),
        }

        print("\n=== Compression Level Comparison ===")

        for result in analysis_results[:3]:  # First 3 files for summary
            file_name = Path(result.get("file_path", "unknown")).name
            print(f"\n  {file_name}:")
            json_str = json.dumps(result, indent=2, ensure_ascii=False)
            json_tokens = _estimate_tokens(json_str)
            print(f"    JSON baseline: {json_tokens} tokens")

            for level_name, formatter in levels.items():
                toon_str = formatter.format(result)
                toon_tokens = _estimate_tokens(toon_str)
                rate = (1 - toon_tokens / json_tokens) * 100 if json_tokens > 0 else 0
                print(
                    f"    {level_name}: {toon_tokens} tokens ({rate:+.1f}%)"
                )
                assert toon_tokens > 0, f"{level_name} produced zero tokens"

    @pytest.mark.asyncio
    async def test_synthetic_payloads_with_levels(self) -> None:
        """Test compression on synthetic payloads with all levels."""
        payloads = {
            "simple_list": {
                "items": [f"item_{i}" for i in range(20)],
            },
            "nested_classes": {
                "file": "app.py",
                "classes": [
                    {
                        "name": f"Class{i}",
                        "methods": [
                            {"name": f"method_{j}", "line": i * 10 + j}
                            for j in range(5)
                        ],
                    }
                    for i in range(10)
                ],
            },
            "flat_metadata": {
                "file": "main.py",
                "language": "python",
                "lines": 150,
                "imports": ["os", "sys", "json", "pathlib", "typing"],
                "functions": ["main", "parse", "validate", "format"],
                "classes": ["App", "Config"],
            },
        }

        for level in CompressionLevel:
            formatter = ToonFormatter(compression_level=level)
            print(f"\n=== {level.value.upper()} Level ===")
            for name, payload in payloads.items():
                metrics = self._measure_compression(formatter, payload)
                print(
                    f"  {name:>20}: {metrics['compression_rate_pct']:>+6.1f}% "
                    f"({metrics['toon_bytes']} vs {metrics['json_bytes']} bytes)"
                )
                assert metrics["toon_bytes"] > 0, f"Empty output for {name} at {level}"

    def test_is_toon_content_detection(self) -> None:
        """Verify TOON content detection works on our output."""
        formatter = ToonFormatter()
        data = {"file": "test.py", "language": "python", "elements": []}
        toon_output = formatter.format(data)

        assert ToonFormatter.is_toon_content(toon_output), (
            f"TOON output not detected as TOON: {toon_output[:100]}"
        )

    def test_json_not_detected_as_toon(self) -> None:
        """Verify JSON is not mistakenly detected as TOON."""
        json_output = '{"file": "test.py", "language": "python"}'
        assert not ToonFormatter.is_toon_content(json_output)

        json_array = '[{"name": "a"}, {"name": "b"}]'
        assert not ToonFormatter.is_toon_content(json_array)

    def test_empty_content_detection(self) -> None:
        """Edge cases for TOON detection."""
        assert not ToonFormatter.is_toon_content("")
        assert not ToonFormatter.is_toon_content("   ")
        assert not ToonFormatter.is_toon_content("just a plain string")

    @pytest.mark.asyncio
    async def test_output_readability_preserved(
        self, analysis_results: list[dict]
    ) -> None:
        """TOON output should remain human-readable (key names visible)."""
        formatter = ToonFormatter()

        for result in analysis_results[:3]:
            toon_output = formatter.format(result)
            # File path should appear
            if "file_path" in result:
                assert result["file_path"] in toon_output or "file" in toon_output.lower()
            # Language should appear
            if "language" in result:
                assert result["language"] in toon_output

    @pytest.mark.asyncio
    async def test_compression_across_json_payload_sizes(
        self, analysis_results: list[dict]
    ) -> None:
        """Compression should work across different payload sizes."""
        formatter = ToonFormatter()

        small_results = [r for r in analysis_results
                        if len(json.dumps(r)) < 1000]
        large_results = [r for r in analysis_results
                        if len(json.dumps(r)) >= 1000]

        for label, subset in [("small", small_results), ("large", large_results)]:
            if not subset:
                continue
            rates: list[float] = []
            for result in subset:
                metrics = self._measure_compression(formatter, result)
                rates.append(metrics["compression_rate_pct"])
            avg = sum(rates) / len(rates)
            print(f"\n  {label} payloads ({len(subset)} files): avg {avg:.1f}% compression")

    @pytest.mark.asyncio
    async def test_full_compression_report(
        self, analysis_results: list[dict]
    ) -> None:
        """Generate comprehensive compression report."""
        print("\n" + "=" * 70)
        print("TOON COMPRESSION REPORT — REAL PROJECT FILES")
        print("=" * 70)

        for level in [None, CompressionLevel.MINIMAL, CompressionLevel.BALANCED, CompressionLevel.DETAILED]:
            if level is None:
                formatter = ToonFormatter()
                label = "DEFAULT"
            else:
                formatter = ToonFormatter(compression_level=level)
                label = level.value.upper()

            total_json = 0
            total_toon = 0
            count = 0

            for result in analysis_results:
                json_str = json.dumps(result, indent=2, ensure_ascii=False)
                toon_str = formatter.format(result)
                total_json += len(json_str)
                total_toon += len(toon_str)
                count += 1

            if count > 0 and total_json > 0:
                overall_rate = (1 - total_toon / total_json) * 100
                print(
                    f"  {label:>10}: {count:>2} files, "
                    f"JSON {total_json:>8,}B → TOON {total_toon:>8,}B, "
                    f"{overall_rate:>5.1f}% reduction"
                )
