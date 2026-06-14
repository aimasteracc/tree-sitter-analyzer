#!/usr/bin/env python3
"""
Advanced Command

Handles advanced analysis functionality.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

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


def _collect_complexity_metrics(elements: Sequence[object]) -> dict[str, float]:
    """Aggregate function-level complexity stats from ``elements``.

    Returns ``{"total": int, "average": float, "max": int}``.
    Non-function elements are ignored; missing ``complexity_score`` defaults
    to 1 (a single-statement function has cyclomatic complexity 1).
    """
    scores = [
        getattr(element, "complexity_score", 1)
        for element in elements
        if is_element_of_type(element, ELEMENT_TYPE_FUNCTION)
    ]
    total = sum(scores) if scores else 0
    return {
        "total": total,
        "average": round(total / len(scores), 2) if scores else 0.0,
        "max": max(scores) if scores else 0,
    }


def _build_elements_payload(
    elements: Sequence[object],
) -> list[dict[str, object]]:
    """Convert AST elements to JSON-payload dicts via ``element_to_dict``.

    Q1 (round-33 dogfood): uses the canonical helper instead of hand-rolling
    9 keys. The helper iterates the documented ``_OPTIONAL_ELEM_FIELDS`` list,
    so plugin-populated values like ``is_async`` / ``is_static`` /
    ``is_constructor`` / ``is_method`` / ``superclass`` / ``class_type`` /
    ``module_path`` / ``is_constant`` reach the JSON output instead of
    being silently stripped. Adds the legacy ``type`` + ``complexity`` aliases.
    """
    payload: list[dict[str, object]] = []
    elements_list = list(elements)
    for element in elements_list:
        elem_dict = element_to_dict(element, elements_list)
        elem_dict["type"] = get_element_type(element)
        elem_dict["complexity"] = elem_dict.get("complexity_score")
        payload.append(elem_dict)
    return payload


def _full_analysis_dict(
    analysis_result: "AnalysisResult",
    elements_payload: list[dict[str, object]],
    counts: dict[str, int],
    complexity: dict[str, float],
) -> dict[str, object]:
    """Assemble the canonical full-analysis envelope.

    S1 (round-37 dogfood): per-kind aggregations match MCP ``analyze_scale``.
    r37y (dogfood): emit ``summary_line`` + ``agent_summary`` + ``verdict``
    so agents can branch on shape without special-casing CLI vs MCP.
    """
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
    return {
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
        "complexity": complexity,
        "success": analysis_result.success,
        "analysis_time": analysis_result.analysis_time,
        "summary_line": summary_line,
        "verdict": "INFO",
        "agent_summary": agent_summary,
    }


class AdvancedCommand(BaseCommand):
    """Command for advanced analysis."""

    def __init__(self, args: Any) -> None:
        super().__init__(args)
        self._json_error_envelope_enabled = True

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
        """Output full analysis results.

        r37f0 (dogfood): 87→~25 lines. ``_collect_complexity_metrics`` does
        the function-level complexity aggregation; ``_build_elements_payload``
        converts AST elements via the canonical helper; ``_full_analysis_dict``
        assembles the envelope (preserves r37y agent_summary contract).
        """
        if self.args.output_format not in ("json", "toon"):
            output_section("Advanced Analysis Results")

        complexity = _collect_complexity_metrics(analysis_result.elements)
        elements_payload = _build_elements_payload(analysis_result.elements)
        counts = _per_element_counts(analysis_result.elements)
        result_dict = _full_analysis_dict(
            analysis_result, elements_payload, counts, complexity
        )

        if self.args.output_format == "json":
            output_json(result_dict)
            return
        if self.args.output_format == "toon" and _toon_available:
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(result_dict))
            return
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
