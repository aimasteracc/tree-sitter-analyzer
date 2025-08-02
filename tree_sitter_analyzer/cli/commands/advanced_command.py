#!/usr/bin/env python3
"""
Advanced Command

Handles advanced analysis functionality.
"""

from typing import TYPE_CHECKING

from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

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

    def _output_statistics(self, analysis_result: "AnalysisResult") -> None:
        """Output statistics only."""
        stats = {
            "line_count": analysis_result.line_count,
            "element_count": len(analysis_result.elements),
            "node_count": analysis_result.node_count,
            "language": analysis_result.language,
        }
        output_section("Statistics")
        if self.args.output_format == "json":
            output_json(stats)
        else:
            for key, value in stats.items():
                output_data(f"{key}: {value}")

    def _output_full_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output full analysis results."""
        output_section("Advanced Analysis Results")
        if self.args.output_format == "json":
            result_dict = {
                "file_path": analysis_result.file_path,
                "language": analysis_result.language,
                "line_count": analysis_result.line_count,
                "element_count": len(analysis_result.elements),
                "node_count": analysis_result.node_count,
                "elements": [
                    {
                        "name": getattr(element, "name", str(element)),
                        "type": getattr(element, "__class__", type(element)).__name__,
                        "start_line": getattr(element, "start_line", 0),
                        "end_line": getattr(element, "end_line", 0),
                    }
                    for element in analysis_result.elements
                ],
                "success": analysis_result.success,
                "analysis_time": analysis_result.analysis_time,
            }
            output_json(result_dict)
        else:
            self._output_text_analysis(analysis_result)

    def _output_text_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output analysis in text format."""
        output_data(f"File: {analysis_result.file_path}")
        output_data("Package: (default)")
        output_data(f"Lines: {analysis_result.line_count}")

        element_counts: dict[str, int] = {}
        for element in analysis_result.elements:
            element_type = getattr(element, "__class__", type(element)).__name__
            element_counts[element_type] = element_counts.get(element_type, 0) + 1

        output_data(f"Classes: {element_counts.get('Class', 0)}")
        output_data(f"Methods: {element_counts.get('Function', 0)}")
        output_data(f"Fields: {element_counts.get('Variable', 0)}")
        output_data(f"Imports: {element_counts.get('Import', 0)}")
        output_data("Annotations: 0")
