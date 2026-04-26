"""Finding Correlation Tool — MCP Tool.

Runs ALL auto-discovered analyzers on a file and correlates their findings
to identify compound hotspots. Supports suppression filtering via inline
comments (# tsa: disable <rule>).
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from ...analysis.finding_correlation import (
    CorrelationResult,
    FindingCorrelator,
)
from ...analysis.finding_suppression import (
    build_suppression_set,
    parse_suppressions,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

ANALYSIS_PACKAGE = "tree_sitter_analyzer.analysis"
_ANALYSIS_METHOD_NAMES = ["analyze_file", "analyze", "detect_file", "detect"]

# Modules that are not file-level analyzers (utility/framework modules).
_EXCLUDED_MODULES: frozenset[str] = frozenset({
    "__init__", "base", "finding_correlation", "finding_suppression",
    "error_recovery", "dependency_graph",
    "coupling_metrics", "design_patterns", "refactoring_suggestions",
    "project_brain", "health_score", "ci_report", "code_clones",
    "semantic_impact", "test_coverage", "api_discovery",
    "java_patterns", "causal_chain",
})


def _discover_analyzers() -> list[tuple[str, str, str]]:
    """Auto-discover all file-level analyzers via pkgutil.

    Returns list of (module_name, class_name, method_name).
    """
    import tree_sitter_analyzer.analysis as pkg

    analyzers: list[tuple[str, str, str]] = []

    for _importer, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_") or modname in _EXCLUDED_MODULES:
            continue

        try:
            mod = importlib.import_module(f"{ANALYSIS_PACKAGE}.{modname}")
        except Exception:
            continue

        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if not isinstance(obj, type) or attr_name.startswith("_"):
                continue

            for method in _ANALYSIS_METHOD_NAMES:
                if hasattr(obj, method):
                    analyzers.append((modname, attr_name, method))
                    break

    return analyzers


class FindingCorrelationTool(BaseMCPTool):
    """MCP tool for cross-analyzer finding correlation."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "finding_correlation",
            "description": (
                "Correlate findings from ALL auto-discovered analyzers to identify "
                "compound hotspots. Supports inline suppression filtering "
                "(# tsa: disable <rule> comments). "
                "\n\n"
                "Runs all available analyzers on a file, then groups findings "
                "by code location. Locations flagged by 2+ analyzers are "
                "reported as hotspots. Hotspots with 3+ analyzers are critical."
                "\n\n"
                "USE THIS WHEN:\n"
                "- You want to prioritize which code locations to fix first\n"
                "- You need a summary of all quality issues in a file\n"
                "- You want to see which code is problematic across multiple dimensions\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to analyze.",
                    },
                    "min_analyzers": {
                        "type": "integer",
                        "description": "Minimum number of analyzers to qualify as hotspot (default: 2)",
                        "default": 2,
                    },
                    "apply_suppressions": {
                        "type": "boolean",
                        "description": "Apply inline suppression filtering (# tsa: disable comments). Default: true.",
                        "default": True,
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        min_analyzers = arguments.get("min_analyzers", 2)
        apply_suppressions = arguments.get("apply_suppressions", True)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {"error": "file_path must be provided", "format": output_format}

        resolved = self.resolve_and_validate_file_path(file_path)
        result = self._run_correlation(resolved, apply_suppressions)

        # Filter hotspots by min_analyzers.
        filtered = CorrelationResult(
            hotspots=[h for h in result.hotspots if h.analyzer_count >= min_analyzers],
            total_findings=result.total_findings,
            total_files=result.total_files,
            analyzers_used=result.analyzers_used,
        )

        if output_format == "json":
            return filtered.to_dict()
        return self._format_toon(filtered, resolved)

    def _run_correlation(
        self, file_path: str, apply_suppressions: bool = True
    ) -> CorrelationResult:
        """Run all auto-discovered analyzers and correlate findings."""
        correlator = FindingCorrelator()

        # Build suppression set if requested.
        sup_set: set[tuple[str, int]] | None = set()
        if apply_suppressions:
            sup_result = parse_suppressions(file_path)
            sup_set = build_suppression_set(sup_result)

        for modname, class_name, method_name in _discover_analyzers():
            try:
                mod = importlib.import_module(
                    f"{ANALYSIS_PACKAGE}.{modname}"
                )
                analyzer_cls = getattr(mod, class_name)
            except (ImportError, AttributeError):
                continue

            try:
                analyzer = analyzer_cls()
            except Exception:
                continue

            try:
                method = getattr(analyzer, method_name)
                analysis_result = method(file_path)
                if analysis_result is not None:
                    correlator.add_findings(modname, analysis_result, file_path)
            except Exception:
                continue

        result = correlator.correlate()

        if apply_suppressions and sup_set is not None:
            result = self._apply_suppression_filter(result, sup_set)

        return result

    @staticmethod
    def _apply_suppression_filter(
        result: CorrelationResult,
        sup_set: set[tuple[str, int]] | None,
    ) -> CorrelationResult:
        """Remove suppressed findings from hotspots."""
        filtered_hotspots = []
        total_remaining = 0

        for hotspot in result.hotspots:
            remaining_findings = [
                f for f in hotspot.findings
                if not (
                    sup_set is None
                    or (f.finding_type, f.line) in sup_set
                )
            ]
            if remaining_findings:
                total_remaining += len(remaining_findings)
                hotspot.findings = remaining_findings
                filtered_hotspots.append(hotspot)

        return CorrelationResult(
            hotspots=filtered_hotspots,
            total_findings=total_remaining,
            total_files=result.total_files,
            analyzers_used=result.analyzers_used,
        )

    def _format_toon(self, result: CorrelationResult, file_path: str) -> dict[str, Any]:
        lines: list[str] = []
        fname = Path(file_path).name
        lines.append(f"Finding Correlation: {fname}")
        lines.append(f"Analyzers: {len(result.analyzers_used)} | Total findings: {result.total_findings}")
        lines.append("")

        if not result.hotspots:
            lines.append("No compound hotspots found. No location was flagged by 2+ analyzers.")
        else:
            lines.append(f"Hotspots: {len(result.hotspots)}")
            lines.append(f"  Critical (3+ analyzers): {len(result.critical_hotspots)}")
            lines.append(f"  Warning (2 analyzers): {len(result.warning_hotspots)}")
            lines.append("")

            for h in result.hotspots:
                severity_marker = ">>>" if h.analyzer_count >= 3 else "  >"
                lines.append(
                    f"{severity_marker} L{h.line}-{h.end_line} "
                    f"[{h.analyzer_count} analyzers, {h.max_severity.value}] "
                    f"score={h.priority_score} {h.pattern.value}"
                )
                for name in h.analyzer_names:
                    lines.append(f"    - {name}")
                lines.append("")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "hotspot_count": len(result.hotspots),
            "critical_count": len(result.critical_hotspots),
            "analyzers_used": result.analyzers_used,
            "total_findings": result.total_findings,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        min_a = arguments.get("min_analyzers", 2)
        if not isinstance(min_a, int) or min_a < 1:
            raise ValueError("min_analyzers must be a positive integer")
        return True
