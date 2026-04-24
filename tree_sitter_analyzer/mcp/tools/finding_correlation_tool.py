"""Finding Correlation Tool — MCP Tool.

Runs multiple analyzers on a file and correlates their findings to identify
compound hotspots: code locations flagged by several independent analyzers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.finding_correlation import (
    CorrelationResult,
    FindingCorrelator,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# Analyzers that produce findings with severity + line number.
# Each entry: (analyzer_name, import_path, class_name, method)
_ANALYZER_SPECS: list[tuple[str, str, str, str]] = [
    ("dead_store", "...analysis.dead_store", "DeadStoreAnalyzer", "analyze_file"),
    ("boolean_complexity", "...analysis.boolean_complexity", "BooleanComplexityAnalyzer", "analyze_file"),
    ("cognitive_complexity", "...analysis.cognitive_complexity", "CognitiveComplexityAnalyzer", "analyze_file"),
    ("function_size", "...analysis.function_size", "FunctionSizeAnalyzer", "analyze_file"),
    ("nesting_depth", "...analysis.nesting_depth", "NestingDepthAnalyzer", "analyze_file"),
    ("error_handling", "...analysis.error_handling", "ErrorHandlingAnalyzer", "analyze_file"),
    ("security_scan", "...analysis.security_scan", "SecurityScanner", "scan_file"),
    ("dead_code_path", "...analysis.dead_code_path", "DeadCodePathAnalyzer", "analyze_file"),
    ("comment_quality", "...analysis.comment_quality", "CommentQualityAnalyzer", "analyze_file"),
    ("naming_convention", "...analysis.naming_convention", "NamingConventionAnalyzer", "analyze_file"),
]


def _load_analyzer(module_path: str, class_name: str) -> Any | None:
    """Dynamically load an analyzer class."""
    import importlib

    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)()
    except (ImportError, AttributeError) as e:
        logger.debug("Could not load analyzer %s.%s: %s", module_path, class_name, e)
        return None


class FindingCorrelationTool(BaseMCPTool):
    """MCP tool for cross-analyzer finding correlation."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "finding_correlation",
            "description": (
                "Correlate findings from multiple analyzers to identify "
                "compound hotspots. "
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
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {"error": "file_path must be provided", "format": output_format}

        resolved = self.resolve_and_validate_file_path(file_path)
        result = self._run_correlation(resolved)

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

    def _run_correlation(self, file_path: str) -> CorrelationResult:
        """Run all analyzers and correlate findings."""
        correlator = FindingCorrelator()

        for name, module_path, class_name, method_name in _ANALYZER_SPECS:
            full_module = module_path.replace("...analysis", "tree_sitter_analyzer.analysis")
            analyzer = _load_analyzer(full_module, class_name)
            if analyzer is None:
                continue

            try:
                method = getattr(analyzer, method_name)
                result = method(file_path)
                if result is not None:
                    correlator.add_findings(name, result, file_path)
            except Exception as e:
                logger.debug("Analyzer %s failed on %s: %s", name, file_path, e)
                continue

        return correlator.correlate()

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
