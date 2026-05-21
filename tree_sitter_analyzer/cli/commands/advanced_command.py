#!/usr/bin/env python3
"""
Advanced Command

Handles advanced analysis functionality.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..._api_result_helpers import element_to_dict
from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
    is_element_of_type,
)
from ...output_manager import output_data, output_json, output_section
from .advanced_command_helpers import calculate_file_metrics
from .base_command import BaseCommand

# TOON formatter for CLI output
try:
    from ...formatters.toon_formatter import ToonFormatter

    _toon_available = True
except ImportError:
    _toon_available = False

if TYPE_CHECKING:
    from ...models import AnalysisResult


def _build_advanced_summary_line(
    file_path: str,
    language: str,
    line_count: int,
    counts: dict[str, int],
    element_count: int,
    *,
    mode: str,
) -> str:
    """Compose the canonical headline for CLI ``--advanced`` responses.

    r37y (dogfood): CLI ``--advanced`` JSON output was missing the
    ``summary_line`` envelope key entirely. Every other tool exposes a
    one-line headline an agent can paste into a report without parsing
    the nested response. This helper mirrors the format used by MCP
    ``analyze_scale`` so agents see consistent wording across surfaces.
    """
    return (
        f"{file_path} ({language}) lines={line_count} "
        f"classes={counts['class_count']} methods={counts['method_count']} "
        f"fields={counts['field_count']} imports={counts['import_count']} "
        f"elements={element_count} mode={mode}"
    )


def _per_element_counts(elements: Sequence[object]) -> dict[str, int]:
    """Compute per-kind element aggregations for parity with MCP analyze_scale.

    S1 (round-37 dogfood): CLI ``--advanced`` previously emitted only
    ``element_count`` (total), while MCP ``analyze_scale`` emits
    ``method_count`` / ``class_count`` / ``field_count`` / ``import_count``.
    Both views are useful — neither tool should hide the other's
    aggregation. Returns four counters keyed by the canonical name MCP
    callers already expect.
    """
    counts = {
        "method_count": 0,
        "class_count": 0,
        "field_count": 0,
        "import_count": 0,
    }
    for element in elements:
        if is_element_of_type(element, ELEMENT_TYPE_FUNCTION):
            counts["method_count"] += 1
        elif is_element_of_type(element, ELEMENT_TYPE_CLASS):
            counts["class_count"] += 1
        elif is_element_of_type(element, ELEMENT_TYPE_VARIABLE):
            counts["field_count"] += 1
        elif is_element_of_type(element, ELEMENT_TYPE_IMPORT):
            counts["import_count"] += 1
    return counts


class AdvancedCommand(BaseCommand):
    """Command for advanced analysis."""

    async def execute_async(self, language: str) -> int:
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        if hasattr(self.args, "statistics") and self.args.statistics:
            self._output_statistics(analysis_result)
        else:
            self._output_full_analysis(analysis_result)

        return 0

    def _calculate_file_metrics(self, file_path: str, language: str) -> dict[str, int]:
        """
        Calculate accurate file metrics including line counts.

        Args:
            file_path: Path to the file to analyze
            language: Programming language

        Returns:
            Dictionary containing file metrics
        """
        return calculate_file_metrics(file_path, language)

    def _output_statistics(self, analysis_result: "AnalysisResult") -> None:
        """Output statistics only."""
        # S1 (round-37 dogfood): include the per-kind aggregations that MCP
        # ``analyze_scale`` already emits (method_count, class_count,
        # field_count, import_count). The two surfaces analyse the same
        # tree but only emit one half of the picture each — agents that
        # ask "how many methods does this file have" via the CLI got
        # ``method_count: None`` while MCP returned ``3``. Adding the
        # per-kind counts here closes the cross-tool gap without changing
        # the legacy ``element_count`` aggregate that older consumers read.
        counts = _per_element_counts(analysis_result.elements)
        # r37y (dogfood): canonical envelope. CLI ``--advanced --statistics``
        # was emitting only the raw metric dict — agents reading
        # ``result["summary_line"]`` or ``result["verdict"]`` got ``None``
        # while every other CLI / MCP surface populated them.
        summary_line = _build_advanced_summary_line(
            analysis_result.file_path,
            analysis_result.language,
            analysis_result.line_count,
            counts,
            len(analysis_result.elements),
            mode="stats",
        )
        agent_summary = {
            "summary_line": summary_line,
            "next_step": (
                "Drop --statistics to see element/complexity breakdown, "
                "or run `query_code` for a specific symbol."
            ),
            "verdict": "INFO",
        }
        stats = {
            "success": True,
            "file_path": analysis_result.file_path,
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "method_count": counts["method_count"],
            "class_count": counts["class_count"],
            "field_count": counts["field_count"],
            "import_count": counts["import_count"],
            "node_count": analysis_result.node_count,
            "language": analysis_result.language,
            "summary_line": summary_line,
            "verdict": "INFO",
            "agent_summary": agent_summary,
        }
        if self.args.output_format not in ("json", "toon"):
            output_section("Statistics")
        if self.args.output_format == "json":
            output_json(stats)
        elif self.args.output_format == "toon" and _toon_available:
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(stats))
        else:
            for key, value in stats.items():
                output_data(f"{key}: {value}")

    def _output_full_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output full analysis results."""
        if self.args.output_format not in ("json", "toon"):
            output_section("Advanced Analysis Results")
        complexity_scores = [
            getattr(element, "complexity_score", 1)
            for element in analysis_result.elements
            if is_element_of_type(element, ELEMENT_TYPE_FUNCTION)
        ]
        total_complexity = sum(complexity_scores) if complexity_scores else 0
        avg_complexity = (
            total_complexity / len(complexity_scores) if complexity_scores else 0
        )

        elements_payload: list[dict[str, object]] = []
        for element in analysis_result.elements:
            # Q1 (round-33 dogfood): use the canonical helper instead of
            # hand-rolling 9 keys. The helper iterates the documented
            # ``_OPTIONAL_ELEM_FIELDS`` list, so plugin-populated values
            # like ``is_async``, ``is_static``, ``is_constructor``,
            # ``is_method``, ``superclass``, ``class_type``,
            # ``module_path``, ``is_constant`` reach the JSON output
            # instead of being silently stripped.
            elem_dict = element_to_dict(element, analysis_result.elements)
            # Preserve the canonical ``type`` (lowercased class name) from
            # the helper, but also preserve the legacy element_type used
            # by older consumers — they agree for normal elements.
            elem_dict["type"] = get_element_type(element)
            # Back-compat shim: CLI historically exposed ``complexity``
            # as the element-level shortcut for ``complexity_score``.
            elem_dict["complexity"] = elem_dict.get("complexity_score")
            elements_payload.append(elem_dict)

        # S1 (round-37 dogfood): add per-kind aggregations for parity with
        # MCP ``analyze_scale`` (see _output_statistics for the same fix).
        counts = _per_element_counts(analysis_result.elements)
        # r37y (dogfood): canonical envelope — same fix as
        # ``_output_statistics`` above. The full-analysis path used to
        # emit zero envelope keys (``summary_line``/``agent_summary``/
        # ``verdict`` all None), making it impossible for agents to
        # branch on the response shape without special-casing.
        summary_line = _build_advanced_summary_line(
            analysis_result.file_path,
            analysis_result.language,
            analysis_result.line_count,
            counts,
            len(analysis_result.elements),
            mode="full",
        )
        agent_summary = {
            "summary_line": summary_line,
            "next_step": (
                "Use --statistics for counts only, or `analyze_code_structure` "
                "(MCP) for grouped element tables."
            ),
            "verdict": "INFO",
        }
        result_dict: dict[str, object] = {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "method_count": counts["method_count"],
            "class_count": counts["class_count"],
            "field_count": counts["field_count"],
            "import_count": counts["import_count"],
            "node_count": analysis_result.node_count,
            "elements": elements_payload,
            "complexity": {
                "total": total_complexity,
                "average": round(avg_complexity, 2),
                "max": max(complexity_scores) if complexity_scores else 0,
            },
            "success": analysis_result.success,
            "analysis_time": analysis_result.analysis_time,
            "summary_line": summary_line,
            "verdict": "INFO",
            "agent_summary": agent_summary,
        }
        if self.args.output_format == "json":
            output_json(result_dict)
        elif self.args.output_format == "toon" and _toon_available:
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(result_dict))
        else:
            self._output_text_analysis(analysis_result)

    def _output_text_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output analysis in text format."""
        output_data(f"File: {analysis_result.file_path}")
        output_data("Package: (default)")
        output_data(f"Lines: {analysis_result.line_count}")

        element_counts: dict[str, int] = {}
        complexity_scores: list[int] = []

        for element in analysis_result.elements:
            element_type = get_element_type(element)
            element_counts[element_type] = element_counts.get(element_type, 0) + 1

            # Collect complexity scores for methods
            if element_type == ELEMENT_TYPE_FUNCTION:
                complexity = getattr(element, "complexity_score", 1)
                complexity_scores.append(complexity)

        # Calculate accurate file metrics
        file_metrics = self._calculate_file_metrics(
            analysis_result.file_path, analysis_result.language
        )

        # Calculate complexity statistics
        total_complexity = sum(complexity_scores) if complexity_scores else 0
        avg_complexity = (
            total_complexity / len(complexity_scores) if complexity_scores else 0
        )
        max_complexity = max(complexity_scores) if complexity_scores else 0

        output_data(f"Classes: {element_counts.get(ELEMENT_TYPE_CLASS, 0)}")
        output_data(f"Methods: {element_counts.get(ELEMENT_TYPE_FUNCTION, 0)}")
        output_data(f"Fields: {element_counts.get(ELEMENT_TYPE_VARIABLE, 0)}")
        output_data(f"Imports: {element_counts.get(ELEMENT_TYPE_IMPORT, 0)}")
        output_data("Annotations: 0")

        # Add detailed metrics using accurate calculations
        output_data(f"Code Lines: {file_metrics['code_lines']}")
        output_data(f"Comment Lines: {file_metrics['comment_lines']}")
        output_data(f"Blank Lines: {file_metrics['blank_lines']}")
        output_data(f"Total Complexity: {total_complexity}")
        output_data(f"Average Complexity: {avg_complexity:.2f}")
        output_data(f"Max Complexity: {max_complexity}")
