#!/usr/bin/env python3
"""
Advanced Command

Handles advanced analysis functionality.
"""

from typing import TYPE_CHECKING

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
        stats = {
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "node_count": analysis_result.node_count,
            "language": analysis_result.language,
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

        result_dict = {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "node_count": analysis_result.node_count,
            "elements": [
                {
                    "name": getattr(element, "name", str(element)),
                    "type": get_element_type(element),
                    "start_line": getattr(element, "start_line", 0),
                    "end_line": getattr(element, "end_line", 0),
                    "visibility": getattr(element, "visibility", None),
                    "modifiers": getattr(element, "modifiers", []),
                    "parameters": getattr(element, "parameters", []),
                    "return_type": getattr(element, "return_type", None),
                    "complexity": getattr(element, "complexity_score", None),
                }
                for element in analysis_result.elements
            ],
            "complexity": {
                "total": total_complexity,
                "average": round(avg_complexity, 2),
                "max": max(complexity_scores) if complexity_scores else 0,
            },
            "success": analysis_result.success,
            "analysis_time": analysis_result.analysis_time,
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
